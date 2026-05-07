# SPDX-License-Identifier: LGPL-2.1-or-later
"""
由 FreeCADCmd / 同目录 python.exe 执行：将 CAD（IGES/STEP）导出为 STEP（用于与 OBJ 预览链路一致）。

环境变量 ``FC_EXPORT_STEP_CONFIG`` 指向 JSON（扩展名建议 ``.fcexpstp``）。
字段：
- cad_path: 输入 .igs/.iges/.stp/.step
- out_step: 输出 .step
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_CONFIG_EXT = ".fcexpstp"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _config_path() -> Path:
    env = (os.environ.get("FC_EXPORT_STEP_CONFIG") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()
        _die(f"FC_EXPORT_STEP_CONFIG 指向的文件不存在: {env}", 2)
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_file() and p.suffix.lower() == _CONFIG_EXT:
            return p.resolve()
    _die(
        f"用法: FreeCADCmd.exe freecad_export_step_runner.py <config{_CONFIG_EXT}>\n"
        f"或设置 FC_EXPORT_STEP_CONFIG。",
        2,
    )


def main() -> int:
    try:
        import FreeCAD  # type: ignore
        import Import  # type: ignore
        import Part  # type: ignore
    except ImportError:
        _die("未导入 FreeCAD。请使用 FreeCADCmd 执行本脚本。", 2)

    cfg_path = _config_path()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cad = Path(cfg["cad_path"]).resolve()
    out_step = Path(cfg["out_step"]).resolve()
    if not cad.is_file():
        _die(f"CAD 不存在: {cad}")
    out_step.parent.mkdir(parents=True, exist_ok=True)

    doc = FreeCAD.newDocument("ExportStep")
    try:
        Import.insert(str(cad), doc.Name)
        doc.recompute()
        objs = []
        for o in doc.Objects:
            sh = getattr(o, "Shape", None)
            if sh is not None and not sh.isNull():
                objs.append(o)
        if not objs:
            _die("文档中未找到可导出的 Shape。")
        Part.export(objs, str(out_step))
    finally:
        FreeCAD.closeDocument(doc.Name)

    print(f"[OK] {cad.name} -> {out_step.name} ({out_step.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
