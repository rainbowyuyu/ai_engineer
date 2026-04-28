param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$MacroDir = (Join-Path $env:APPDATA "FreeCAD\Macro"),
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Info([string]$msg) { Write-Host "[INFO] $msg" }
function Warn([string]$msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail([string]$msg) { throw $msg }

$besoDir = Join-Path $RepoRoot "beso"
if (-not (Test-Path $besoDir)) {
  Fail "未找到 beso 源码目录：$besoDir"
}

$files = @(
  "beso_fc_gui.py",
  "beso_main.py",
  "beso_conf.py",
  "beso_lib.py",
  "beso_filters.py",
  "beso_plots.py",
  "beso_separate.py"
)

Info "RepoRoot = $RepoRoot"
Info "besoDir  = $besoDir"
Info "MacroDir = $MacroDir"

if (-not (Test-Path $MacroDir)) {
  Warn "FreeCAD Macro 目录不存在，先创建：$MacroDir"
  New-Item -ItemType Directory -Path $MacroDir | Out-Null
}

foreach ($f in $files) {
  $src = Join-Path $besoDir $f
  if (-not (Test-Path $src)) { Fail "缺少文件：$src" }
}

foreach ($f in $files) {
  $src = Join-Path $besoDir $f
  $dst = Join-Path $MacroDir $f
  if ((Test-Path $dst) -and (-not $Force)) {
    Info "已存在，跳过（可加 -Force 覆盖）：$dst"
    continue
  }
  Copy-Item -Force $src $dst
  Info "已复制：$f"
}

Info "完成。请在 FreeCAD 中通过 Macro 管理器运行 beso_fc_gui.py"

