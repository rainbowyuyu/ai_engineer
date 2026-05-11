"""
调用仓库内嵌的 text-to-cad「cad」技能（``third_party/text-to-cad/cad_skill``）的 ``scripts/step`` 等 CLI。

需要 **build123d**（及 OCP）。解释器顺序：``TEXT_TO_CAD_PYTHON``（显式）→ 仓库 ``<WORKSPACE_ROOT>/.venv`` →
同级 ``text-to-cad/.venv`` → ``sys.executable``；取首个 ``import build123d`` 成功的路径。
缺依赖时安装：``pip install -r backend/requirements-text-to-cad.txt``（见仓库根说明）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def cad_skill_root(workspace_root: Path) -> Path:
    return (workspace_root / "third_party" / "text-to-cad" / "cad_skill").resolve()


def _python_imports_build123d(py: str) -> bool:
    try:
        r = subprocess.run(
            [py, "-c", "import build123d"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def _python_version_line(py: str) -> str:
    try:
        r = subprocess.run(
            [py, "-c", "import sys; print(sys.version.split()[0], sys.executable)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout or "").strip()
    except Exception:
        pass
    return ""


def _candidate_text_to_cad_pythons(workspace_root: Path) -> list[str]:
    out: list[str] = []
    env = (os.environ.get("TEXT_TO_CAD_PYTHON") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            out.append(str(p.resolve()))
    root = workspace_root.resolve()
    # 仓库内 .venv（优先于跑后端的 sys.executable，避免误用未装全依赖的系统 Python）
    for rel in (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / ".venv" / "bin" / "python3",
    ):
        if rel.is_file():
            out.append(str(rel.resolve()))
    # 常见：与 beso_ai 同级的 text-to-cad 仓库自带 .venv
    for rel in (
        root.parent / "text-to-cad" / ".venv" / "Scripts" / "python.exe",
        root.parent / "text-to-cad" / ".venv" / "bin" / "python",
        root.parent / "text-to-cad" / ".venv" / "bin" / "python3",
    ):
        if rel.is_file():
            out.append(str(rel.resolve()))
    exe = Path(sys.executable)
    out.append(str(exe.resolve()))
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def text_to_cad_python(workspace_root: Path | None = None) -> str:
    """返回第一个已安装 build123d 的解释器路径。"""
    ws = (workspace_root or Path(__file__).resolve().parents[2]).resolve()
    for py in _candidate_text_to_cad_pythons(ws):
        if _python_imports_build123d(py):
            return py
    # 无一可用时仍返回显式配置或当前解释器（便于把 ImportError  stderr 带回上层）
    env = (os.environ.get("TEXT_TO_CAD_PYTHON") or "").strip()
    if env and Path(env).is_file():
        return str(Path(env).resolve())
    return sys.executable


def text_to_cad_python_hint(workspace_root: Path) -> str:
    """当 cad_skill_step 失败时附加到摘要的简短指引。"""
    tried = _candidate_text_to_cad_pythons(workspace_root)
    return (
        "未检测到可用 build123d。请在项目 .venv 执行：\n"
        "  pip install -r backend/requirements-text-to-cad.txt\n"
        "或在 .env 设置 TEXT_TO_CAD_PYTHON=（已装 build123d 的 python.exe）。\n"
        "若已设置 TEXT_TO_CAD_PYTHON 仍失败，请确认该解释器与仓库 .venv 一致，或删除该变量以优先使用 <WORKSPACE_ROOT>/.venv。\n"
        "已尝试的解释器：" + ", ".join(tried[:4]) + ("…" if len(tried) > 4 else "")
    )


def run_step_on_generator(
    workspace_root: Path,
    generator_py: Path,
    *,
    output_step: Path | None = None,
    timeout_s: int = 600,
) -> tuple[bool, str, dict[str, str | bool]]:
    """
    在 ``workspace_root`` 为 cwd、``PYTHONPATH`` 含 ``cad_skill`` 的条件下执行:
    ``<python> -m scripts.step <generator> [-o out]``（与 text-to-cad 对 REPO_ROOT= cwd 的约定一致）。

    ``generator_py`` 须落在 ``workspace_root`` 之下。
    """
    root = workspace_root.resolve()
    skill = cad_skill_root(root)
    if not (skill / "scripts" / "step" / "__main__.py").is_file():
        return False, "未找到内嵌 cad_skill（third_party/text-to-cad/cad_skill）", {}
    gen = generator_py.resolve()
    try:
        rel_gen = gen.relative_to(root)
    except ValueError:
        return False, "generator_py 必须位于工作区 workspace_root 内", {}

    if not gen.is_file():
        return False, f"生成器脚本不存在: {gen}", {}

    py_exe = text_to_cad_python(root)
    # cad_skill generation CLI 要求 --output 与部分路径参数使用 POSIX '/'（见 common.generation._resolve_cli_output_path）
    cmd: list[str] = [py_exe, "-m", "scripts.step", rel_gen.as_posix()]
    if output_step is not None:
        out = output_step.resolve()
        try:
            rel_out = out.relative_to(root)
        except ValueError:
            return False, "output_step 必须位于工作区 workspace_root 内", {}
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["-o", rel_out.as_posix()])

    env = os.environ.copy()
    prev_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(skill) + (os.pathsep + prev_pp if prev_pp else "")
    # common.catalog / metadata / render 在 import 时用 Path.cwd() 作为 REPO_ROOT、CAD_ROOT。
    # 若 cwd 仅为 cad_skill，则 CAD 发现范围不包含仓库内 third_party/.../STEP 等路径，后续 GLB/拓扑
    # 等步骤可能因「找不到 CAD STEP ref」失败。cwd 使用 workspace_root，PYTHONPATH 仍指向 cad_skill 以加载 scripts.*。
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"scripts/step 超时（>{timeout_s}s）", {}
    except Exception as e:
        return False, str(e), {}

    out_txt = (proc.stdout or "")[-12_000:]
    err_txt = (proc.stderr or "")[-12_000:]
    merged = (out_txt + "\n" + err_txt).strip()
    ok = proc.returncode == 0
    extra: dict[str, str | bool] = {
        "returncode": proc.returncode,
        "stdout_tail": out_txt[-4000:],
        "stderr_tail": err_txt[-4000:],
    }
    if ok:
        # 默认与生成器同名的 .step 与 .py 同目录
        guess = gen.with_suffix(".step")
        if guess.is_file():
            extra["step_path"] = str(guess)
        if output_step is not None and output_step.resolve().is_file():
            extra["step_path"] = str(output_step.resolve())
    summary = "STEP 生成成功" if ok else f"scripts/step 失败 (exit {proc.returncode})"
    if merged:
        summary += ":\n" + merged[-2000:]
    ver_line = _python_version_line(py_exe)
    extra["python_used"] = py_exe
    if ver_line:
        extra["python_version"] = ver_line
    if not ok:
        low = merged.lower()
        probe = f"[解释器] {py_exe}"
        if ver_line:
            probe += f"\n[版本] {ver_line}"
        summary = probe + "\n\n" + summary
        if "build123d" in low or "modulenotfounderror" in low or "no module named" in low:
            summary += "\n\n" + text_to_cad_python_hint(root)
        else:
            summary += (
                "\n\n[排错] 请确认上述解释器已执行 "
                "`pip install -r backend/requirements-text-to-cad.txt`；"
                "或在 .env 设置 TEXT_TO_CAD_PYTHON 指向正确环境。"
            )
    return ok, summary, extra


def cad_skill_help_text(workspace_root: Path, *, max_chars: int = 14_000) -> str:
    skill = cad_skill_root(workspace_root)
    p = skill / "SKILL.md"
    if not p.is_file():
        return "未找到 SKILL.md；请检查 third_party/text-to-cad/cad_skill 是否已嵌入。"
    body = p.read_text(encoding="utf-8", errors="replace")
    step_dir = workspace_root / "third_party" / "text-to-cad" / "STEP"
    examples = []
    if step_dir.is_dir():
        for f in sorted(step_dir.glob("*.py")):
            try:
                rel = f.resolve().relative_to(workspace_root.resolve())
            except ValueError:
                rel = f
            examples.append(str(rel).replace("\\", "/"))
    head = (
        "[内嵌路径] cad_skill 根目录: "
        + str(skill).replace("\\", "/")
        + "\n[STEP 依赖] pip install -r backend/requirements-text-to-cad.txt（优先 <仓库>/.venv；或 TEXT_TO_CAD_PYTHON / 同级 text-to-cad/.venv）"
        + "\n[示例生成器 .py] "
        + (", ".join(examples) if examples else "（无）")
        + "\n\n---\n\n"
    )
    out = head + body
    if len(out) > max_chars:
        out = out[:max_chars] + "\n\n…(截断，完整见 third_party/text-to-cad/cad_skill/SKILL.md)…"
    return out


__all__ = [
    "cad_skill_root",
    "cad_skill_help_text",
    "run_step_on_generator",
    "text_to_cad_python",
    "text_to_cad_python_hint",
]
