# 当前 PowerShell 会话内优先使用仓库 .node/（便于终端手动跑 npm，无需改系统 PATH）
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$nd = Join-Path $root ".node"
if (-not (Test-Path (Join-Path $nd "node.exe"))) {
    Write-Error "未找到 $nd\node.exe。请先运行: .\scripts\install_project_node.ps1"
    exit 1
}
$env:PATH = "$nd;" + $env:PATH
Write-Host "已前置 PATH: $nd"
Write-Host "node: $(& (Join-Path $nd 'node.exe') -v)"
Write-Host "npm:  $(& (Join-Path $nd 'npm.cmd') -v)"
