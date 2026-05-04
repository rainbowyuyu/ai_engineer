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
- Python **3.10+**（推荐 3.11/3.12；依赖版本见 `backend/requirements.txt`）
- FreeCAD/CalculiX：确保 `D:\\freecad\\bin\\ccx.exe` 存在（或设置 `CCX_PATH`）
- **CAD → 主 INP（代码路径）**：默认 **`CAD_IGES_BACKEND=auto`** ——优先 **OCC 剖分 + `StlAPI_Writer` → meshio** 生成**已焊接共边**的 **`from_cad_gmsh.inp`（S3）**（避免按面拼节点导致 CCX 病态/假死）；失败时再回退 **`gmsh`**。其余同前述（**`CAD_IGES_BACKEND`**、**`OCC_*`** / **`GMSH_*`** 等）。
- **CAD 生成的 INP 与 BESO 智能体**：BESO 只识别 **壳/实体单元**（如 **`S3`、`S4`、`C3D4`、`C3D8`**、`CPS4` 等）。**梁（`B31*`）、刚体（`R3D*`）等不在支持范围**。`from_cad_gmsh.inp` 落盘前经 **`inp_beso_compat`** 校验。OCC 路径产出为 **壳三角网格（S3）**；若必须**实体体网格**，请 **`CAD_IGES_BACKEND=gmsh`** 或在 CAD 中准备封闭体后再用 Gmsh。大文件上传见 **`MAX_UPLOAD_BYTES`**（默认 256MB）。

当前锁定的主要后端版本：**FastAPI 0.115.14**、**Uvicorn 0.32.1**、**Pydantic 2.10.6**、**Starlette 0.46.x**（由 FastAPI 引入）、**websockets 14.2**、**python-multipart 0.0.20**。

### 1) 安装后端依赖

在项目根目录（**务必使用 venv 内的 Python**，避免系统全局包里的 **Pydantic 1.x** 与 FastAPI 0.115 不兼容）：

```powershell
python -m venv .\.venv_web
.\.venv_web\Scripts\python -m pip install -U pip
.\.venv_web\Scripts\python -m pip install -r .\backend\requirements.txt
```

安装后自检（Pydantic 主版本号应为 **2**）：

```powershell
.\.venv_web\Scripts\python -c "import fastapi, pydantic, uvicorn; print('fastapi', fastapi.__version__, 'pydantic', pydantic.VERSION, 'uvicorn', uvicorn.__version__)"
```

### 2) 启动后端（同时提供 UI）

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv_web\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

打开网页时，**请与上面 `--host` 使用同一主机名**（推荐都用 `127.0.0.1`，或都用 `localhost`），不要混用，否则浏览器会把 `http://localhost:8000` 与 `http://127.0.0.1:8000` 当成两个源，从而触发 CORS。

- 推荐：`http://127.0.0.1:8000/ui/`

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
- **上传 IGES 后提示找不到 Gmsh 或转换失败**：确认已安装 Gmsh 且 `GMSH`/`PATH` 配置正确；查看网页气泡或接口返回的 `detail`/`error`；复杂模型可先在本机 Gmsh GUI 验证能否生成体网格。

