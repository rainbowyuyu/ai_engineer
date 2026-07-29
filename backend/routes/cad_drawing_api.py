"""CAD drawing pack API — workspace path / upload → multi-view drawing sheet."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.tools.cad_drawing_pack import build_cad_drawing_pack

router = APIRouter(tags=["cad-drawing"])


class DrawingPackIn(BaseModel):
    path: str | None = Field(default=None, description="工作区内路径，可带 @ 前缀")
    file_id: str | None = Field(default=None, description="上传文件 id（runs/_uploads/<id>/）")
    title: str | None = None
    engine: Literal["auto", "freecad", "mesh"] = Field(
        default="auto",
        description="auto=优先 FreeCAD 线框；freecad=强制 FreeCAD；mesh=仅网格着色",
    )
    sheet_size: Literal["A3", "A1", "A0"] = Field(
        default="A3",
        description="图幅（横幅）：A3 默认；A1/A0 更接近总布置打印幅面",
    )
    layout: Literal["ga", "quad"] = Field(
        default="ga",
        description="ga=总布置式（大俯视）；quad=经典四等分",
    )

    @model_validator(mode="after")
    def _need_path_or_file(self) -> DrawingPackIn:
        if not (self.path and str(self.path).strip()) and not (self.file_id and str(self.file_id).strip()):
            raise ValueError("须提供 path 或 file_id")
        return self


@router.post("/drawing-pack")
def cad_drawing_pack(body: DrawingPackIn) -> dict[str, Any]:
    try:
        return build_cad_drawing_pack(
            body.path,
            file_id=body.file_id,
            title=body.title,
            engine=body.engine,
            sheet_size=body.sheet_size,
            layout=body.layout,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工程图生成失败: {e}") from e
