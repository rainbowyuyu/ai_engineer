# PyCharm 使用项目本地 Node（`.node/`）

本仓库将 **Node 运行时** 放在根目录 **`.node/`**（与 Python 虚拟环境 **`.venv/`** 并列），不提交到 Git，适合团队统一版本、又不必改系统全局 Node。

**说明**：npm 运行配置需 **PyCharm Professional**（或自带 Node 插件的 JetBrains IDE）；Community 若无 Node/npm 支持，请用终端执行 `scripts/use_project_node.ps1` 后再跑 npm。

## 1. 安装到 `.node/`

在仓库根目录打开 **PowerShell**（或 PyCharm 内置终端）：

```powershell
.\scripts\install_project_node.ps1
```

版本号由根目录 **`.node-version`** 决定（与 `install_project_node.ps1` 读取一致）。

## 2. PyCharm 配置 Node 解释器

1. **File → Settings**（macOS：**PyCharm → Settings**）。
2. **Languages & Frameworks → Node.js**。
3. **Node interpreter**：选 **Add… → Add Local…**，浏览到：

   `\<仓库根>\.node\node.exe`

4. 若出现 **Package manager**：选同目录下的 **npm**（一般为自动识别 `npm.cmd`）。

应用后，在 **remotion-site-intro** 目录的 `package.json` 上右键 → **Show npm Scripts**，即可用 PyCharm 运行 `dev` / `render` 等（前提是已对该子项目执行过 `npm install`）。

## 2.1 已提交的 Run/Debug 配置（推荐）

仓库已包含 **`.idea/runConfigurations/`** 下三个 npm 配置，**Node 解释器已写死为** `$PROJECT_DIR$/.node/node.exe`（请先执行上一节的 `install_project_node.ps1` 生成 `.node/`）：

| 名称 | 作用 |
|------|------|
| **remotion: npm install** | 在 `remotion-site-intro` 执行 `npm install` |
| **remotion: npm run dev** | 启动 Remotion Studio（`npm run dev`） |
| **remotion: npm run render** | 导出 `out/site-intro.mp4` |

使用：**Run → Edit Configurations…** 或工具栏运行配置下拉框中选中上述名称，点击运行。若首次打开提示找不到解释器，检查 **`.node\node.exe`** 是否存在；若 PyCharm 升级后 XML 字段不兼容，在配置里手动将 Node 指到 `.node\node.exe` 即可。

## 3. 仅终端临时使用（不改 PyCharm）

```powershell
. .\scripts\use_project_node.ps1
cd remotion-site-intro
npm install
npm run dev
```

## 4. 与 `.venv` 的关系

| 目录      | 用途        | PyCharm 配置位置 |
|-----------|-------------|------------------|
| `.venv/`  | Python 解释器、pip | **Project → Python Interpreter** |
| `.node/`  | Node / npm  | **Languages & Frameworks → Node.js** |

二者互不覆盖；Remotion 子项目只依赖 **Node 这一条配置** 即可。
