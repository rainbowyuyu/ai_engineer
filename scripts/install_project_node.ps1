# 将 Node.js 官方 Windows x64 zip 解压到仓库根目录 .node/（与 .venv 并列，不入库）
# 用法（PowerShell）:  cd 仓库根目录;  .\scripts\install_project_node.ps1
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$verFile = Join-Path $root ".node-version"
if (-not (Test-Path $verFile)) {
    throw "缺少 .node-version: $verFile"
}
$version = (Get-Content $verFile -Raw).Trim()
if (-not $version) { throw ".node-version 为空" }

$dest = Join-Path $root ".node"
$zipName = "node-v$version-win-x64.zip"
$url = "https://nodejs.org/dist/v$version/$zipName"
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "beso-node-$version"

if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
$zipPath = Join-Path $tmp $zipName

Write-Host "下载: $url"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing

Write-Host "解压到临时目录..."
Expand-Archive -LiteralPath $zipPath -DestinationPath $tmp -Force
$inner = Join-Path $tmp "node-v$version-win-x64"
if (-not (Test-Path $inner)) {
    throw "解压后未找到目录: $inner"
}

if (Test-Path $dest) {
    Write-Host "已存在 .node，先删除旧版..."
    Remove-Item $dest -Recurse -Force
}
New-Item -ItemType Directory -Path $dest | Out-Null

Write-Host "复制到 $dest"
Copy-Item -Path (Join-Path $inner "*") -Destination $dest -Recurse -Force

Remove-Item $tmp -Recurse -Force

$nodeExe = Join-Path $dest "node.exe"
if (-not (Test-Path $nodeExe)) { throw "未找到 node.exe" }
& $nodeExe -v
$npmCmd = Join-Path $dest "npm.cmd"
if (Test-Path $npmCmd) { & $npmCmd -v }
Write-Host "完成。PyCharm 中将 Node 解释器指向: $nodeExe"
