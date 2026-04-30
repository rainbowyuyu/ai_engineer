from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


ALLOWED_EXTS = {".inp", ".vtk", ".obj", ".igs", ".iges"}
_DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024  # 256MB（Gmsh 生成的大 INP 常超过 50MB）


def max_upload_bytes() -> int:
    raw = (os.environ.get("MAX_UPLOAD_BYTES") or "").strip()
    if raw:
        try:
            return max(1024 * 1024, int(raw))
        except ValueError:
            pass
    return _DEFAULT_MAX_UPLOAD_BYTES


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    path: Path
    name: str
    ext: str


def uploads_root(workspace_root: Path) -> Path:
    return (workspace_root / "runs" / "_uploads").resolve()


def store_upload(workspace_root: Path, filename: str, content: bytes) -> StoredFile:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"unsupported extension: {ext}")
    cap = max_upload_bytes()
    if len(content) > cap:
        raise ValueError(f"file too large（>{cap // (1024 * 1024)}MB），可用环境变量 MAX_UPLOAD_BYTES 提高上限")

    file_id = uuid.uuid4().hex
    root = uploads_root(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    d = root / file_id
    d.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)
    p = (d / safe_name).resolve()
    p.write_bytes(content)
    return StoredFile(file_id=file_id, path=p, name=safe_name, ext=ext)


def resolve_file(workspace_root: Path, file_id: str) -> StoredFile:
    d = (uploads_root(workspace_root) / file_id).resolve()
    if not d.exists() or not d.is_dir():
        raise FileNotFoundError(file_id)
    # pick the first file
    files = [p for p in d.iterdir() if p.is_file()]
    if not files:
        raise FileNotFoundError(file_id)
    p = files[0].resolve()
    ext = p.suffix.lower()
    return StoredFile(file_id=file_id, path=p, name=p.name, ext=ext)


def preview_inp(path: Path, max_lines: int = 200) -> Dict[str, Any]:
    text_lines: List[str] = []
    elsets: List[str] = []
    element_types: Dict[str, int] = {}

    elset_pat = re.compile(r"^\*ELSET\s*,\s*ELSET\s*=\s*([^,\s]+)", re.IGNORECASE)
    elem_pat = re.compile(r"^\*ELEMENT\s*,\s*TYPE\s*=\s*([^,\s]+)", re.IGNORECASE)

    current_type: str | None = None

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i < max_lines:
                text_lines.append(line.rstrip("\n"))
            s = line.strip()
            m1 = elset_pat.match(s)
            if m1:
                elsets.append(m1.group(1))
            m2 = elem_pat.match(s)
            if m2:
                current_type = m2.group(1)
                element_types.setdefault(current_type, 0)
            elif current_type and s and not s.startswith("*"):
                # count element definition lines under current *ELEMENT block
                element_types[current_type] = element_types.get(current_type, 0) + 1

            if i > 20000 and len(elsets) > 200:
                break

    return {
        "lines": text_lines,
        "elsets": sorted(set(elsets)),
        "element_types": element_types,
    }

