## BESO 智能体网页（本机版）

这个网页应用在本机运行：输入中文需求 →（可选）调用 Qwen 解析参数 → 后端自动运行 `beso_main.py`（调用 `ccx`）→ 实时推送日志与 `.vtk` 到网页进行可视化。

### 重要安全提示

- **不要把 API Key 写进代码/仓库**：请只通过环境变量设置 `QWEN_API_KEY`。
- 你之前在聊天里暴露过 key，建议你在控制台**立即轮换**该 key。

### 目录结构

- `backend/`：FastAPI 后端（Job 管理、WebSocket 推送、运行 BESO）
- `frontend_static/`：无需 npm 的静态前端（直接由后端 `/ui/` 提供）
- `runs/<job_id>/`：每次运行的独立输出目录（日志、vtk、inp、png）

### 运行前置

- Windows
- Python 3.11+
- FreeCAD/CalculiX：确保 `D:\\freecad\\bin\\ccx.exe` 存在（或设置 `CCX_PATH`）

### 1) 安装后端依赖

在项目根目录：

```powershell
python -m venv .\.venv_web
.\.venv_web\Scripts\python -m pip install -r .\backend\requirements.txt
```

### 2) 启动后端（同时提供 UI）

```powershell
.\.venv_web\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

打开网页：

- `http://127.0.0.1:8000/ui/`

### 3) 配置 Qwen（可选）

如果你希望让 Qwen 从自然语言里自动抽取参数，在启动后端前设置环境变量：

```powershell
$env:QWEN_API_KEY = "你的key"
$env:QWEN_MODEL = "qwen-plus"   # 可选
$env:QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 可选
```

> MVP 当前即使不配 Qwen，也会用默认参数运行。

### 4) 运行一个任务（网页）

在网页中点击“创建并运行”，默认会跑：

- `examples/example1/Plane_mesh.inp`
- `mass_goal_ratio=0.4`
- `filter=2`
- `save_every=10`

运行过程中：

- 左侧实时滚动日志
- 右侧尝试实时渲染最新 `.vtk`
- “最新 VTK”链接可直接下载，用 ParaView 打开（兜底）

### 常见问题

- **端口 8000 被占用**：关闭占用进程或换端口。
- **VTK 渲染失败**：不同 VTK 类型/体量下，浏览器渲染可能失败；直接下载 `.vtk` 用 ParaView 查看即可。

