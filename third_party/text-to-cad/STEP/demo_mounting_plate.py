"""矩形安装板 + 顶面中心圆球：四孔 M3 通孔；+X 侧面中心通孔（沿 -X 贯穿）。

约定：毫米；XY 为板面，+Z 为板厚方向；原点位于板底面中心。圆球与顶面相切并布尔合并为一体。
侧面孔位于 YZ 平面 x = +length/2 一侧的几何中心，孔轴平行于 X，便于 harness 演示侧向特征。
"""

from __future__ import annotations

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Box,
    Circle,
    GridLocations,
    Hole,
    Locations,
    Mode,
    Plane,
    Sphere,
    extrude,
)


def gen_step():
    length = 100.0
    width = 60.0
    thickness = 10.0
    hole_radius = 3.4 / 2.0  # M3 普通间隙孔（与 CAD skill 默认一致）
    hole_grid_x = 70.0
    hole_grid_y = 36.0
    sphere_radius = 12.0

    with BuildPart() as plate:
        Box(
            length,
            width,
            thickness,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.ADD,
        )
        with GridLocations(hole_grid_x, hole_grid_y, 2, 2):
            Hole(radius=hole_radius)
        # 顶面中心：球心高度 = 板顶 + 半径，球与顶面相切
        with Locations((0, 0, thickness + sphere_radius)):
            Sphere(radius=sphere_radius, mode=Mode.ADD)
        # 过球心（全局 Z 轴、XY 原点）的中心通孔，贯穿球体与板
        center_hole_radius = 2.5  # 直径 5 mm，可按需要改
        with Locations((0, 0, 0)):
            Hole(radius=center_hole_radius)
        # +X 侧面中心通孔（YZ 面 x = length/2 处，沿 -X 贯穿板宽）
        side_hole_radius = 3.0
        with BuildSketch(Plane.YZ.offset(length / 2)) as _sk:
            Circle(radius=side_hole_radius)
        extrude(amount=-(length + 20.0), mode=Mode.SUBTRACT)

    return plate.part
