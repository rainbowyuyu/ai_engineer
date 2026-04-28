# 更新日志

本文档记录 BESO Agent Web 前端与相关后端的显著变更。

---

## [未发布] 2026-04-29

### 3D 预览（`frontend_static/flow_main.viewer.js`）

- **减轻刷新抽搐**：首次加载后自动适配相机，后续迭代不再每帧重算视角；模型中心变化使用 **lerp 插值** 平滑过渡。
- **防抖与去重**：`loadMesh` 对同一 URL 限频（约 2 秒内不重复全量加载）；短间隔多次调用合并为一次拉取。
- **`resize` 优化**：仅在容器宽高变化时调用 `setSize`，减少画布无意义重绘。
- **图片指标区**：`upsertImage` 仅在 URL 变化或超过约 3.5 秒才刷新 `img.src`，减轻轮询导致的闪烁。
- **内存**：替换网格时对旧材质执行 `dispose()`。
- **旋转开关**：新增 `setAutoRotate` / `getAutoRotate`，由头部按钮控制是否对网格应用自动绕 Y 轴旋转。

### 3D 预览 UI（`frontend_static/index.html` + `frontend_static/flow_main.css`）

- 在「3D 预览」标题栏增加 **旋转开/关** 按钮（`#spinToggleBtn`），玻璃质感、hover 微动效，文案在「旋转中 / 已暂停」间切换。

### 任务与流程隔离（`frontend_static/flow_main.js`）

- **`resetTaskRuntimeView()`**：切换任务时关闭 WebSocket、停止轮询与摘要刷新，清空代码流队列、日志、图片计数、mesh 就绪态及右侧 UI 容器，避免 **任务 A 的产物串到任务 B**。
- **`activeTaskKey`**：在打开任务与「开始新流程」时维护，用于判断是否切换任务上下文。
- **图片卡片作用域**：`upsertImage` / `hydrateDefaultImages` 仅在 `#imgGrid` 内查找 `[data-img]`，避免全局 DOM 误匹配。

### CORS 与 Job API（`backend/app.py`）

- **`GET /api/jobs/{job_id}`**：当 job 不存在时返回 **404** 与明确 `detail`，避免未捕获 `KeyError` 导致 500。
- **前端默认同源**（`frontend_static/flow_main.js` + `index.html`）：`normalizedBaseUrl()` 在输入为空时使用 `window.location.origin`，避免 `localhost` 页面请求 `127.0.0.1` 触发跨域；`baseUrl` 输入框默认留空并提示使用当前页地址。

### 日志摘要悬浮窗（`frontend_static/flow_main.js` + `flow_main.viewer.js` + `flow_main.css`）

- **实时日志**：WebSocket 日志、轮询快照、`buildSummary` 与打开任务时合并/刷新摘要；与步骤 4 的 `#logSummary` 同步。
- **Portal**：`#logFloatDock` 挂载到 `document.body`，固定定位、高层级，不受指标面板裁剪/动画影响。
- **拖拽**：顶部栏与最小化胶囊可拖；指针移动在 `window` 上监听；边界钳制在视口内；位置可写入 `sessionStorage`。
- **最小化与误触**：拖动最小化按钮时抑制随后的 `click` 展开；展开/收起状态可持久化。
- **可见性**：仅在 **流程页 + 步骤 3 + 已有 `jobId`** 时显示悬浮窗，主页不显示。
- **样式**：悬浮窗与旋转按钮等样式集中在 **`flow_main.css`**（因 `index.html` 内大量样式曾被包在 HTML 注释中未生效，需在 CSS 中维护）。

### 主页任务栏与上传（`frontend_static/flow_main.css` + `flow_main.layout.js` + `flow_main.tasks.js` + `index.html` + `flow_main.js`）

- **任务栏折叠**：收起为约 `42×42` 的 **`≡`** 小块，点击可再次展开；折叠按钮文案在 `◀` / `≡` 间切换（`setSidebarCollapsed`）。
- **任务重命名**：每条任务提供「重命名」，通过 `prompt` 输入后调用 `POST /api/tasks/upsert` 更新 `title`。
- **上传预览**：已上传区域增加 **`×`** 按钮，清除当前 `file_id`、文件名、扫描目录预览与展示卡片。

### 布局与步骤（`frontend_static/flow_main.layout.js`）

- `layout.setStep` 与 `state.currentStep` 在包装函数中同步，供日志悬浮窗可见性等逻辑使用。

### 说明

- 若工作区中仍有其他已修改但未纳入本次提交的文件（例如 `beso/beso_lib.py`、`backend/tools/beso.py` 等），请按需单独提交或合并到下一版变更说明中。

---

## 格式说明

- 日期采用仓库协作时的本地约定（如 `2026-04-29`）。
- 未打 Git 标签的版本可标为 `[未发布]`，发布时改为版本号并打 tag。
