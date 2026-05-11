from __future__ import annotations

import json as json_lib
import os
from typing import Any, Dict, List, Optional

import requests
from urllib3.util import Timeout as Urllib3Timeout

from backend.qwen_runtime_config import get_qwen_config

_http_session: Optional[requests.Session] = None


def _shared_http_session() -> requests.Session:
    """进程内复用 TCP/TLS，减轻首条对话冷启动。"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
    return _http_session


# DashScope 首包、SSE 相邻 chunk 间隔常较长；read 过短会报 Read timed out（勿与 connect 混淆）。
_DEFAULT_CONNECT_S = 45.0
_DEFAULT_READ_S = 480.0
_MIN_READ_S = 120.0
_MIN_CONNECT_S = 10.0


def _default_http_timeout(override_read_s: Optional[float] = None) -> Urllib3Timeout:
    """
    使用 ``urllib3.util.Timeout(connect=..., read=...)`` 传给 ``requests``，避免 (connect, read) 元组歧义。
    环境变量：QWEN_HTTP_READ_TIMEOUT_S（默认 480，且不低于 120）、QWEN_HTTP_CONNECT_TIMEOUT_S（默认 45）。
    兼容旧名：QWEN_HTTP_TIMEOUT_S 仅作为读超时（同样不低于 120）。
    """
    read_raw = (
        os.environ.get("QWEN_HTTP_READ_TIMEOUT_S", "").strip()
        or os.environ.get("QWEN_HTTP_TIMEOUT_S", "").strip()
    )
    connect_raw = os.environ.get("QWEN_HTTP_CONNECT_TIMEOUT_S", "").strip()
    try:
        read_s = float(read_raw) if read_raw else _DEFAULT_READ_S
    except ValueError:
        read_s = _DEFAULT_READ_S
    read_s = max(_MIN_READ_S, read_s)
    try:
        connect_s = float(connect_raw) if connect_raw else _DEFAULT_CONNECT_S
    except ValueError:
        connect_s = _DEFAULT_CONNECT_S
    connect_s = max(_MIN_CONNECT_S, connect_s)
    if override_read_s is not None:
        read_s = max(_MIN_READ_S, float(override_read_s))
    return Urllib3Timeout(connect=connect_s, read=read_s)


def assistant_chat_http_read_timeout_s() -> float:
    """
    ``POST /api/assistant/chat`` 与 ``/stream`` 专用上游 **读** 超时（秒）。

    侧栏多轮对话 + 较长系统提示时，DashScope 首包常明显慢于普通短补全；若仍 503 超时请再调大
    ``QWEN_ASSISTANT_CHAT_READ_TIMEOUT_S``（默认 900），或检查代理/``QWEN_BASE_URL``。
    """
    raw = (os.environ.get("QWEN_ASSISTANT_CHAT_READ_TIMEOUT_S") or "").strip()
    if raw:
        try:
            return max(_MIN_READ_S, float(raw))
        except ValueError:
            pass
    return 900.0


def _format_upstream_http_error(resp: requests.Response | None, exc: BaseException) -> str:
    """把 DashScope / OpenAI 兼容接口的错误体压缩成可读中文提示。"""
    if resp is None:
        return str(exc)
    code = getattr(resp, "status_code", "?")
    try:
        j = resp.json()
    except Exception:
        raw = (resp.text or "").strip()
        return f"上游返回 HTTP {code}：{raw[:500] or str(exc)}"
    err = j.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("code") or err.get("type")
        if msg:
            return f"上游返回 HTTP {code}：{msg}"
    if isinstance(err, str) and err.strip():
        return f"上游返回 HTTP {code}：{err.strip()}"
    msg = j.get("message")
    if isinstance(msg, str) and msg.strip():
        return f"上游返回 HTTP {code}：{msg.strip()}"
    raw = json_lib.dumps(j, ensure_ascii=False)[:500]
    return f"上游返回 HTTP {code}：{raw or str(exc)}"


def _is_upstream_stream_body_cut_short(exc: BaseException) -> bool:
    """iter_lines / stream 读取时上游或中间层提前关连接（IncompleteRead、premature 等）。"""
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        return True
    msg = str(exc).lower()
    if "premature" in msg or "incomplete read" in msg or "connection broken" in msg:
        return True
    mod = getattr(type(exc), "__module__", "") or ""
    name = getattr(type(exc), "__name__", "")
    if "urllib3" in mod and name in ("ProtocolError", "IncompleteRead", "InvalidChunkLength"):
        return True
    return False


def _raise_for_chat_transport(url: str, exc: BaseException) -> None:
    """统一转为 RuntimeError，由 API 层映射为 503 + detail，避免笼统 502。"""
    if isinstance(exc, requests.HTTPError):
        raise RuntimeError(_format_upstream_http_error(exc.response, exc)) from exc
    if isinstance(exc, requests.Timeout):
        raise RuntimeError(
            "连接或读取大模型服务超时。请检查网络、代理与 QWEN_BASE_URL；"
            "侧栏整包对话可增大 QWEN_ASSISTANT_CHAT_READ_TIMEOUT_S（默认 900 秒）；"
            "其它 Qwen 请求可增大 QWEN_HTTP_READ_TIMEOUT_S（默认 480 秒）。"
        ) from exc
    if isinstance(exc, requests.ConnectionError):
        raise RuntimeError(
            f"无法连接大模型服务（{url[:72]}…）。请检查网络、防火墙、VPN 以及 QWEN_BASE_URL 是否可达。"
        ) from exc
    if _is_upstream_stream_body_cut_short(exc):
        raise RuntimeError(
            "上游流式响应被提前关闭（常见于反向代理超时、网络抖动或浏览器中止流式请求）。"
            "侧栏助手默认使用整包非流式；若在设置中开启「优先 SSE 流式」后仍频繁出现，请关闭该选项或检查代理与 QWEN_BASE_URL。"
        ) from exc
    if isinstance(exc, requests.RequestException):
        raise RuntimeError(f"请求大模型服务失败：{exc}") from exc
    raise RuntimeError(str(exc)) from exc


class QwenClient:
    """
    Minimal Qwen client (OpenAI-compatible endpoint).
    Default base_url matches DashScope compatible mode. Override via env.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ):
        runtime = get_qwen_config()
        self.api_key = api_key or runtime.api_key or os.environ.get("QWEN_API_KEY")
        self.base_url = (
            base_url
            or runtime.base_url
            or os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        )
        self.model = model or runtime.model or os.environ.get("QWEN_MODEL", "qwen-plus")
        # 流式时 read 为「相邻两次从 socket 读到数据」的最大间隔，需留足余量
        self._http_timeout: Urllib3Timeout = _default_http_timeout(timeout_s)

    def warmup(self) -> Dict[str, Any]:
        """
        短超时极小请求：预热 DNS/TLS/连接池，降低首条 chat/stream 超时概率。
        故意使用较短 read（不走 _default_http_timeout 的 120s 下限），仅用于 ping。
        """
        if not self.api_key:
            return {"ok": False, "skipped": "no_api_key"}
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        t_short = Urllib3Timeout(connect=20.0, read=50.0)
        try:
            r = _shared_http_session().post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "."}],
                    "max_tokens": 1,
                    "temperature": 0,
                },
                timeout=t_short,
            )
            r.raise_for_status()
            return {"ok": True, "model": self.model}
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError, requests.RequestException) as e:
            return {"ok": False, "error": str(e)[:240]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:240]}

    def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.2) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("QWEN_API_KEY is not set (use environment variable)")
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        try:
            r = _shared_http_session().post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": temperature},
                timeout=self._http_timeout,
            )
            r.raise_for_status()
            return r.json()
        except RuntimeError:
            raise
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError, requests.RequestException) as e:
            _raise_for_chat_transport(url, e)
        except ValueError as e:
            raise RuntimeError(f"上游响应不是合法 JSON：{e}") from e

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.6,
    ):
        """OpenAI-compatible SSE stream; yields raw ``str`` lines (``data: {...}`` or ``data: [DONE]``)."""
        if not self.api_key:
            raise RuntimeError("QWEN_API_KEY is not set (use environment variable)")
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        try:
            with _shared_http_session().post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                },
                stream=True,
                timeout=self._http_timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if line is None:
                        continue
                    s = str(line).strip()
                    if not s:
                        continue
                    yield s + "\n"
        except RuntimeError:
            raise
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError, requests.RequestException) as e:
            _raise_for_chat_transport(url, e)

