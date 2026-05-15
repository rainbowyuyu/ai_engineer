# AI Engineer（本机构型优化与仿真编排）

在本机运行的 Web 应用：中文需求与多轮对话 →（可选）通义千问解析参数或调用工具 → 后端调度 **CalculiX（ccx）+ BESO** → WebSocket 推送日志与 **VTK** 供浏览器预览；并支持 **IGES/STEP 扫描目录**、**OC4 半潜式设计域**、**CAD Explorer** 等扩展流程。

## 重要安全提示

- **不要把 API Key 写进代码或提交到仓库**：仅通过环境变量或 UI「设置」写入进程内配置（`QWEN_API_KEY` 等）。
- 若曾在聊天中暴露过密钥，请在云控制台**立即轮换**。

## 功能概览

| 能力 | 说明 |
|------|------|
| **拓扑优化任务** | `POST /api/chat` 创建 Job；`POST /api/jobs/{id}/start` 启动；`GET /ws/jobs/{id}` 订阅日志与产物事件。支持 `inp_path`、`file_id` 或 **`scan_dir` 扫描目录**（多文件合并/生成代码见 `backend/generator`）。 |
| **自然语言参数** | 配置 `QWEN_API_KEY` 时，`backend.agent.decide_params` 可从用户描述中抽取 `mass_goal_ratio`、`filter_radius`、`optimization_base`（`failure_index` / `stiffness`）、`save_every` 等；未配置时使用内置默认。 |
| **通用助手** | `POST /api/assistant/chat`、流式 `/api/assistant/chat/stream`；**工具模式** `tools_enabled=true`（及 `/api/assistant/chat/stream-tools`）：`cad_convert`、`open_results_viewer`、`list_scan_dir`、`cad_skill_help`、`cad_skill_step`、`open_cad_explorer` 等。支持深度思考、联网摘要（DuckDuckGo Instant Answer，仅供参考）。 |
| **文件与 CAD** | `POST /api/files/upload`（体量上限见 **`MAX_UPLOAD_BYTES`**，默认 256MB）；IGES 目录异步转换 `POST /api/cad/convert-iges`；工作区内格式转换 `POST /api/tools/cad-convert`（FreeCAD）。 |
| **网格预览** | `POST /api/preview/inp-mesh-vtk`：将主网格 INP 转为 VTK Legacy ASCII（FreeCAD FEM），供前端三维预览（单文件约 80MB 上限）。 |
| **OC4 设计域** | 前缀 **`/api/oc4/design-domain`**：上传会话、几何构建、OBJ 预览、网格、载荷划分、与设计域智能体流式对话等（详见 `backend/routes/oc4_design_domain_api.py`；方法论上下文见 `backend/oc4_methodology_chen2026.py`）。 |
| **CAD Explorer** | 静态站点 **`/cad-explorer/`**（优先 `third_party/text-to-cad/cad_skill/explorer/dist`，可用环境变量 **`CAD_EXPLORER_DIST`** 覆盖；未构建时为占位页）。动态目录 **`GET /api/cad-explorer/catalog`** 需本机安装 **Node** 并存在 `export-catalog.mjs`。 |
| **任务持久化** | `runs/_tasks/` 下 JSON 存储侧栏任务与对话线程；`GET/POST /api/tasks` 等。 |
| **本机打开文件夹** | `POST /api/open-explorer-folder`：在桌面与浏览器同机时打开资源管理器（仅 **`WORKSPACE_ROOT`** 内路径）。 |

## 目录结构（摘要）

- `backend/`：FastAPI 应用（`app.py`）、Job 管理、WebSocket、BESO 子进程、OC4 与设计域服务、工具脚本封装。
- `frontend_static/`：无构建步骤的静态前端（`/ui/`）；主流程脚本以 `flow_main*.js` 模块为主。
- `beso/`：BESO 核心脚本与示例配置（生成任务会参考 `backend/generator` 与仓库内示例）。
- `runs/<job_id>/`：单次优化运行的输出（日志、VTK、INP、图表等）。
- `runs/_tasks/`：前端任务列表与助手线程等轻量状态。
- `runs/_cad_convert/`：IGES 异步转换任务状态。
- `runs/_design_domain/`：OC4 设计域会话产物（与 `BESO_VSCODE_IFRAME_BASE_URL` 侧车说明一致）。
- `third_party/text-to-cad/`：内嵌 **text-to-cad / cad_skill**（STEP 生成、CAD Explorer 源码与构建产物）。
- `examples/`：示例 INP、扫描目录与管线脚本参考。

## 运行环境

- **OS**：当前团队以 **Windows** 为主开发与验证；`open-explorer-folder` 等在 macOS/Linux 上会尝试 `open` / `xdg-open`。
- **Python**：**3.10+**（推荐 3.11/3.12）。**须使用虚拟环境**，避免系统全局 **Pydantic 1.x** 与 FastAPI 0.115 不兼容。
- **CalculiX**：默认期望 `D:\freecad\bin\ccx.exe`，或通过 **`CCX_PATH`** 指向 `ccx` / `ccx.exe`。
- **FreeCAD（CAD → INP、INP→VTK 预览）**：需能调用 **FreeCADCmd**；设置 **`FREECAD_CMD`** 指向 `FreeCADCmd.exe`（或已加入 `PATH`）。部分脚本另支持 **`FREECAD_PYTHON`** 指向 FreeCAD 自带的 `python.exe`。体网格或大模型可能较慢，可调 **`FREECAD_MESH_TIMEOUT_S`** / **`GMSH_TIMEOUT_S`**（见 `backend/tools/freecad_iges_to_inp.py`）。
- **可选**：**Node.js**（CAD Explorer 动态 catalog）；**通义千问**（参数解析与助手）；**build123d**（`cad_skill_step`，见 `backend/requirements-text-to-cad.txt`）。

### CAD 生成的 INP 与 BESO

- IGES/STEP → 主网格 INP 的**当前实现**为 **FreeCAD FEM + Gmsh**，输出文件名为 **`from_cad_gmsh.inp`**（常量 `OUTPUT_INP_NAME`）。落盘前会经 **`inp_beso_compat`** 做单元类型等校验。
- BESO 侧主要面向 **壳 / 实体单元**（如 **S3、S4、C3D4、C3D8、CPS4** 等）。**梁（B31*）、刚体（R3D*）等不在支持范围**；若网格类型不兼容，会在转换或任务阶段报错提示。

### 依赖版本（锁定摘录）

以 `backend/requirements.txt` 为准，例如：**FastAPI 0.115.14**、**Uvicorn 0.32.1**、**Pydantic 2.10.6**、**websockets 14.2**、**python-multipart 0.0.20**、**gmsh**、**meshio**、**cadquery-ocp** 等。  
**pythonocc-core** 在 Windows PyPI 上常无轮子，已拆到可选文件 **`backend/requirements-occ.txt`**（一般 CAD→INP Web 路径可不装）。

## 环境变量（常用）

| 变量 | 作用 |
|------|------|
| `WORKSPACE_ROOT` | 工作区根路径（扫描目录、上传、打开文件夹等均限制在此之下）。默认可为仓库根。 |
| `CCX_PATH` | CalculiX 可执行文件路径。 |
| `FREECAD_CMD` | FreeCADCmd 可执行文件路径（CAD 转换、部分网格预览）。 |
| `FREECAD_PYTHON` | FreeCAD 自带 Python（部分工具链脚本）。 |
| `FREECAD_MESH_TIMEOUT_S` / `GMSH_TIMEOUT_S` | 网格阶段超时（秒）。 |
| `QWEN_API_KEY` / `QWEN_BASE_URL` / `QWEN_MODEL` | 通义千问 OpenAI 兼容接口（默认模型 `qwen-plus`）。 |
| `MAX_UPLOAD_BYTES` | 上传单文件大小上限（默认 256MB）。 |
| `CAD_EXPLORER_DIST` | CAD Explorer 静态资源目录，覆盖内置 `explorer/dist`。 |
| `BESO_VSCODE_IFRAME_BASE_URL` | 可选：Open VS Code Web 侧车 iframe 基址（见 `GET /api/config/editor`）。 |
| `PYTHONPATH` | 启动 uvicorn 时建议设为**仓库根**，以便 `import backend`。 |
| `PORT` / `UVICORN_RELOAD` | `python -m backend.app` 时使用端口与热重载。 |

后端启动时会从**仓库根**或 `WORKSPACE_ROOT` 下的 **`.env`** 加载上述变量（**不覆盖**已在环境中的值）。

## 安装与启动

### 1）创建虚拟环境并安装依赖

在仓库根目录执行（路径按你的习惯调整）：

```powershell
python -m venv .\.venv_web
.\.venv_web\Scripts\python -m pip install -U pip
.\.venv_web\Scripts\python -m pip install -r .\backend\requirements.txt
```

安装后确认 Pydantic 主版本为 **2**：

```powershell
.\.venv_web\Scripts\python -c "import fastapi, pydantic, uvicorn; print('fastapi', fastapi.__version__, 'pydantic', pydantic.VERSION, 'uvicorn', uvicorn.__version__)"
```

可选：

```powershell
.\.venv_web\Scripts\python -m pip install -r .\backend\requirements-text-to-cad.txt
```

### 2）启动后端（同时托管 `/ui/` 与 `/cad-explorer/`）

```powershell
cd D:\python_project\beso_ai
$env:PYTHONPATH = (Get-Location).Path
.\.venv_web\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

浏览器访问时请与 **`--host` 保持一致**（建议全程 `127.0.0.1`），避免 `localhost` 与 `127.0.0.1` 混用导致跨源与 WebSocket 异常。

- 主界面：**`http://127.0.0.1:8000/ui/`**
- 健康检查：`GET http://127.0.0.1:8000/health`
- OpenAPI 文档：FastAPI 自动文档（默认 **`/docs`**）

### 3）配置通义千问（可选）

```powershell
$env:QWEN_API_KEY = "你的key"
$env:QWEN_MODEL = "qwen-plus"   # 可选
$env:QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 可选
```

也可在网页「设置」中保存 API Key（进程内，不落盘为明文文件需自行保证机器安全）。**未配置 Qwen** 时，仍可用默认参数发起部分流程；**助手对话与工具模式**在缺少密钥时会返回 503 类提示。

## 使用说明（网页）

1. 指定 **`scan_dir`**（工作区内绝对路径）或上传文件后使用返回的 **`file_id`** / 建议的扫描目录。若目录内仅有 IGES 而无主 INP，可按提示触发 **FreeCAD+Gmsh** 生成 **`from_cad_gmsh.inp`**（需 **`FREECAD_CMD`**）。
2. 填写或口述 **质量目标**、**滤波半径**、**优化目标**（破坏指标 / 刚度）等后「创建并运行」。
3. 运行中：左侧日志、右侧 VTK 实时预览（失败时可从「最新 VTK」下载，用 **ParaView** 打开）。
4. **OC4 设计域**、**设计台 / CAD Explorer** 等入口以当前 `frontend_static` 界面为准。

## 常见问题

- **端口占用**：更换 `--port` 或释放占用进程。
- **VTK 在浏览器中渲染失败**：与模型规模、VTK 子集有关；下载 `.vtk` 用 ParaView 查看即可。
- **提示找不到 FreeCADCmd**：设置 **`FREECAD_CMD`** 并确认路径存在、版本与 Gmsh 插件正常。
- **CalculiX 未找到**：设置 **`CCX_PATH`**。
- **上传失败 / 413**：调大 **`MAX_UPLOAD_BYTES`** 或压缩输入。
- **CAD Explorer 列表为空或报 catalog 错误**：安装 Node，确认 **`/api/cad-explorer/status`** 中 `node_on_path` 与 `export_catalog_script_exists` 为真；必要时在 `third_party/text-to-cad/cad_skill/explorer` 下按该子项目 README 构建 `dist`。

## 相关文档

- 仓库内 BESO 说明：`beso/README.md`
- CAD 技能（STEP-first / build123d）：`.cursor/skills/cad/SKILL.md` 与 `third_party/text-to-cad/cad_skill/SKILL.md`
