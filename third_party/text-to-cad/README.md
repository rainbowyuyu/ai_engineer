# text-to-cad（嵌入 beso_ai）

本目录从 `d:\python_project\text-to-cad` 同步，供侧栏助手（Qwen 工具循环）与本地脚本使用。

- **`cad_skill/`**：Cursor「cad」技能本体（`SKILL.md`、`references/`、`scripts/step|inspect|render|dxf`、`explorer/` 的 dist 与 package.json；**不含** `explorer/node_modules`，若需本地 Explorer 开发可在该目录执行 `npm install`）。
- **`STEP/`**：示例 build123d 生成器与参考 STEP。

## Qwen / 后端运行 STEP 生成

`scripts/step` 依赖 **build123d**（OCP 可与主项目的 `cadquery-ocp` 共存）。

**推荐（装在同一 .venv）：** 在仓库根执行：

```text
.\.venv\Scripts\python -m pip install -r backend\requirements-text-to-cad.txt
```

**或** 指定 text-to-cad 仓库自带虚拟环境（后端会自动探测同级目录 `text-to-cad/.venv`）：

```text
set TEXT_TO_CAD_PYTHON=d:\python_project\text-to-cad\.venv\Scripts\python.exe
```

侧栏工具 **`cad_skill_step`** 会按顺序探测解释器，使用**第一个** `import build123d` 成功的路径：`TEXT_TO_CAD_PYTHON`（若设置）→ **仓库根 `.venv`** → 同级 `text-to-cad/.venv` → 运行后端的 `sys.executable`。若设置了 `TEXT_TO_CAD_PYTHON` 仍报 `scripts/step` 失败，请核对该解释器是否装全依赖，或删除变量以优先使用仓库 `.venv`。

## Web：CAD 设计台

启动后端后，在浏览器打开：

`/ui/cad_design_studio.html`

（或从主页顶栏 **「CAD 设计台」** 进入新标签页。）左侧为内嵌 **CAD Explorer**（`/cad-explorer/`），右侧可直接调用 **Qwen**（`POST /api/assistant/chat`，勾选「启用工具」以使用 cad_skill / open_cad_explorer 等）。

若左侧出现 **404** 或 JSON `Not Found`：① 在主页设置中确认 **API 基址** 与后端一致（设计台会读 `localStorage` 的 `beso.settings.baseUrl`，也可在 URL 加 `?api=http://127.0.0.1:8000`）；② 访问 **`/api/cad-explorer/status`** 查看 `primary_exists` 是否为 true；③ 若 dist 未随仓库同步，设置 **`CAD_EXPLORER_DIST`** 或按占位页说明生成 **`explorer/dist`**。

若已生成 STEP 仍提示 **File does not exist**：需使用含「动态 catalog + `liveCatalogReady`」的前端构建；在 `third_party/text-to-cad/cad_skill/explorer` 执行 **`npm install` 与 `npm run build`** 后重启后端，并确认 **`/api/cad-explorer/catalog`** 可访问（依赖本机 **Node**）。

## 与上游同步（可选）

在仓库根执行（自行调整源路径）：

```powershell
robocopy D:\python_project\text-to-cad\.agents\skills\cad .\third_party\text-to-cad\cad_skill /MIR /XD node_modules .git __pycache__ .venv
robocopy D:\python_project\text-to-cad\STEP .\third_party\text-to-cad\STEP /E
```
