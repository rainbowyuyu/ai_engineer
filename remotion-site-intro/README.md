# AI Engineer 站点介绍片（Remotion）

按 **remotion-best-practices**：时间轴动画仅用 `interpolate` / `spring` / `useCurrentFrame` / `Sequence`，未使用 CSS `@keyframes`、CSS `transition` 或 Tailwind 动画类。色板对齐 `frontend_static` 品牌色（`#2563eb` / `#10b981` / 浅灰底）。

## 时长与章节（分镜）

- **总时长**：约 **5 分钟**（**9000** 帧 @ **30fps**，**1920×1080**），composition id：`SiteIntro`。
- **章节**（`src/compositions/siteIntro/constants.ts` 中 `CHAPTER_DURATIONS`；章节之间 **200f** 叠化，上层整屏淡入盖住下层）：

| 章节 | 内容 | 时长（帧） |
|------|------|------------|
| Ch0 | 开场钩子 | 300 |
| Ch1 | 主页工作台 + 子流程条 | 1500 |
| Ch2 | 智能体与模式 + 对话逐条 | 1200 |
| Ch3 | 设计域（OC4）步骤 + 截图位 | 1800 |
| Ch4 | 构型优化编排 + 伪终端日志 | 1500 |
| Ch5 | 示例教程脚本 + 清单动画 | 2100 |
| Ch6 | 双 CTA 收尾 | 600 |

## 安装与预览

若本机未装全局 Node，可在**仓库根目录**先安装项目内 Node（与 `.venv` 并列的 `.node/`）：

```powershell
cd ..
.\scripts\install_project_node.ps1
.\scripts\use_project_node.ps1
cd remotion-site-intro
```

PyCharm 说明见：`docs/pycharm-local-node.md`。

```bash
cd remotion-site-intro
npm install
npm run dev
```

浏览器打开 Remotion Studio（默认 **http://localhost:3333**）后选择 **`SiteIntro`**。改端口可编辑 `remotion.config.ts` 的 `Config.setStudioPort(...)` 与 `package.json` 里 `dev` 脚本的 `--port`。

**5 分钟预览若卡顿**：在 Studio 中降低预览分辨率；长片建议用 `still` 抽检关键帧（见下）。

## 导出 MP4

```bash
npm run render
```

输出默认：`out/site-intro.mp4`（需可写 `out/`）。5 分钟成片体积与编码参数取决于 Remotion/FFmpeg 默认设置；可按需在 `npx remotion render` 中增加 `--codec h264`、`--crf` 等（见 [Remotion CLI](https://www.remotion.dev/docs/cli)）。

## Still 抽检（推荐）

对长片用单帧导出检查叠化与文字清晰度：

```bash
npx remotion still src/index.ts SiteIntro --frame=0 --output=out/ch0.jpg
npx remotion still src/index.ts SiteIntro --frame=300 --output=out/ch1-start.jpg
npx remotion still src/index.ts SiteIntro --frame=4500 --output=out/mid.jpg
npx remotion still src/index.ts SiteIntro --frame=8999 --output=out/end.jpg
```

## 字体与音轨

- **字体**：`@remotion/google-fonts` — **Noto Sans SC**（`chinese-simplified`）+ **Inter**，在 `FontGate` 中 `waitUntilDone` 后 `continueRender`。
- **音轨占位**：已依赖 `@remotion/media`。在 `src/compositions/SiteIntro.tsx` 将 `ENABLE_BGM` 设为 `true`，并把 `public/onboarding/bgm.mp3` 放入仓库即可启用；音量曲线用 `interpolate` 做首尾淡入淡出。

## `public/onboarding` 截图清单

替换占位 PNG 可显著提升质感（建议 **1920×1080** 或 **2×**）：

| 文件 | 用途 |
|------|------|
| `ch01-landing.png` | Ch1 主页工作台画中画 / 全宽背景 |
| `ch03-design-domain.png` | Ch3 设计域中央画面 |
| `bgm.mp3` | （可选）背景音乐 |

说明见：`public/onboarding/README.txt`。

片中 **Ch1**、**Ch3** 使用 `Img` + `staticFile()`；无替换时仍为仓库内 **1×1 占位 PNG**，可完整播放。

## 代码结构

- `src/compositions/SiteIntro.tsx`：背景 + `Sequence` 串联各章 + 可选 `Audio`。
- `src/compositions/siteIntro/constants.ts`：色板、章节帧长、`SEQUENCE_FROM` / `SEQUENCE_DURATION`、`stackLayerOpacity`。
- `src/compositions/siteIntro/chapters/*.tsx`：各章画面。
- `src/compositions/siteIntro/components/*.tsx`：`ChromeBrowser`、`ChatBubble`、`StepRail`、`Checklist` 等。
- `src/compositions/siteIntro/scripts.ts`：固定对话与清单文案。

## 进一步「还原真实网页」

1. 运行产品前端，截取主页 / 设计域 / 编排 / 任务列表等，覆盖 `public/onboarding/` 下文件名。
2. 如需更多画中画，可在对应章节增加 `Img` + `staticFile()`，并避免用 CSS 动画类驱动时间轴。
