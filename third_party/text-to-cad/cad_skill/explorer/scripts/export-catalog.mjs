/**
 * 供 beso_ai 等宿主通过 Node 子进程输出当前工作区的 CAD Explorer catalog JSON，
 * 解决生产构建烘焙清单不包含构建后新生成 STEP 的问题。
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { scanCadDirectory } from "../lib/cadDirectoryScanner.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = process.env.EXPLORER_WORKSPACE_ROOT;
if (!workspaceRoot || !String(workspaceRoot).trim()) {
  console.error("export-catalog: set EXPLORER_WORKSPACE_ROOT to the workspace root directory.");
  process.exit(1);
}

const catalog = scanCadDirectory({ repoRoot: path.resolve(workspaceRoot) });
process.stdout.write(`${JSON.stringify(catalog)}\n`);
