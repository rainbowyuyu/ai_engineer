## 你现在的工作区里已经准备好的东西

- **`beso/`**：上游 `calculix/beso` 源码已下载到本地。
- **`scripts/install_beso_to_freecad_macro.ps1`**：把必须的 `beso_*.py` 一键复制到 FreeCAD 的宏目录（MacroDir）。
- **`examples/example1/freecad_input.FCStd`**：官方 Example 1 的 FreeCAD 工程文件。
- **`examples/example1/Plane_mesh.inp`**：官方 Example 1 的 `.inp`（可用于验证 `ccx` / 或在 GUI 里直接选）。

## Todo 1：安装/配置 FreeCAD + CalculiX（ccx）

### 1) 安装 FreeCAD（0.18+，建议新版本稳定版）

- 安装后**至少启动一次 FreeCAD**，这样 `%APPDATA%\\FreeCAD\\Macro` 才会出现（宏目录）。

### 2) 在 FreeCAD 里确认 FEM → CalculiX 能跑通“普通静力分析”

- 打开 FreeCAD → 切到 **FEM Workbench**。
- `File -> Open` 打开本项目的 `examples/example1/freecad_input.FCStd`。
- 找到该工程里的分析（Analysis container）并运行求解（线弹性静力）。
- 如果能正常求解并得到结果，说明 FreeCAD 侧的 `ccx` 已经可用。

### 3) 如果 FreeCAD 里提示找不到/无法运行 ccx

你需要安装 CalculiX（`ccx.exe`）并在 FreeCAD 的 FEM 首选项里配置它，或者把它加入 PATH。

- 命令行快速自检（PowerShell）：

```powershell
where ccx
```

输出能看到 `ccx.exe` 路径即表示 PATH 可用。

## Todo 2：把 beso 复制到 FreeCAD 宏目录

在 PowerShell 里，进入工作区根目录运行：

```powershell
.\scripts\install_beso_to_freecad_macro.ps1
```

如果你之前手工放过旧版宏文件，想覆盖，改用：

```powershell
.\scripts\install_beso_to_freecad_macro.ps1 -Force
```

## Todo 3：在 FreeCAD 中用 GUI（Example 4）跑通一次优化

官方 Wiki 对应页面是 [Example 4: GUI in FreeCAD](https://github.com/calculix/beso/wiki/Example-4:-GUI-in-FreeCAD)。

### 1) 运行宏

- FreeCAD → `Macro` 菜单 → 打开宏管理器
- 选择并运行 **`beso_fc_gui.py`**

### 2) 在 GUI 里按顺序操作

1. **Select analysis file**：选择 `.inp` 文件
   - 你可以直接选本项目自带的：`examples/example1/Plane_mesh.inp`
   - 注意：Wiki 要求路径不要包含空格
2. 如果是壳单元域：选择 thickness 对象（Example 1 里通常需要）
3. **Filter range**：先填 `2`（Wiki 推荐从单元尺寸约 2 倍起步）
4. **Mass goal ratio**：先填 `0.4`
5. 点击 **Generate configuration file and run optimization**

运行完成后，会在 `.inp` 所在目录输出 `.log`、结果 `.inp`（不同 state 的网格）以及 `.vtk` 等文件。

## Todo 4：查看结果

- **FreeCAD**：把结果 `.inp` 拖回 FreeCAD 查看剩余网格。
- **ParaView（推荐）**：打开 `.vtk`，用 **Threshold** 过滤隐藏被移除元素（Wiki 有示意图）。

## 常见报错与快速处理

- **`NameError: name 'sys' is not defined`**：上游 `beso_fc_gui.py` 某些版本可能缺 `import sys`。若你遇到，告诉我报错截图/栈，我会在你本地宏文件里补齐。
- **`No module named matplotlib`**：说明 FreeCAD 自带的 Python 环境缺 `matplotlib`。这时有两条路：
  - 让 FreeCAD 的 Python 装上 `matplotlib`（取决于 FreeCAD 打包方式）
  - 或改为在系统 Python 中跑优化（FreeCAD 只做前后处理）

