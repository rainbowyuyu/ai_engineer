param(
  [string]$FreeCADBin = "D:\\freecad\\bin",
  [string]$MacroDir = (Join-Path $env:APPDATA "FreeCAD\\Macro")
)

$ErrorActionPreference = "Continue"

function Section([string]$t) { Write-Host "`n=== $t ===" }

Section "FreeCADBin"
if (Test-Path $FreeCADBin) { "FreeCADBin: $FreeCADBin" } else { "FreeCADBin: NOT FOUND ($FreeCADBin)" }

Section "PATH 检查"
try {
  $ccx = (Get-Command ccx -ErrorAction Stop).Source
  "ccx: $ccx"
} catch { "ccx: NOT FOUND in PATH" }

try {
  $fc = (Get-Command FreeCAD -ErrorAction Stop).Source
  "FreeCAD: $fc"
} catch { "FreeCAD: NOT FOUND in PATH" }

Section "给当前 PowerShell 会话临时配置 PATH（不写入系统）"
if (Test-Path (Join-Path $FreeCADBin "FreeCAD.exe")) {
  "可执行：`$env:Path = `"$FreeCADBin;`$env:Path`""
} else {
  "未检测到 FreeCAD.exe，跳过 PATH 临时配置提示"
}

Section "常见 FreeCAD 安装位置探测"
$candidates = @(
  "$env:ProgramFiles\\FreeCAD*\\bin\\FreeCAD.exe",
  "$env:ProgramFiles\\FreeCAD*\\FreeCAD.exe",
  "$env:ProgramFiles\\FreeCAD\\bin\\FreeCAD.exe",
  "$env:ProgramFiles\\FreeCAD\\FreeCAD.exe",
  "$env:ProgramFiles(x86)\\FreeCAD*\\bin\\FreeCAD.exe",
  "$env:LocalAppData\\Programs\\FreeCAD*\\bin\\FreeCAD.exe",
  (Join-Path $FreeCADBin "FreeCAD.exe")
)
$hits = @()
foreach ($p in $candidates) { $hits += Get-ChildItem -ErrorAction SilentlyContinue $p }
if ($hits.Count -eq 0) {
  "未发现 FreeCAD.exe（如果你用的是便携版/自解压版，请手工定位 FreeCAD.exe）"
} else {
  $hits | Select-Object -ExpandProperty FullName | Sort-Object -Unique
}

Section "FreeCAD 宏目录"
if (Test-Path $MacroDir) { "MacroDir: $MacroDir" } else { "MacroDir: MISSING ($MacroDir) - 启动一次 FreeCAD 后通常会生成" }

