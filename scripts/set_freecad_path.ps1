param(
  [string]$FreeCADBin = "D:\\freecad\\bin"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path (Join-Path $FreeCADBin "FreeCAD.exe"))) {
  throw "未找到 FreeCAD.exe：$FreeCADBin"
}

$env:Path = "$FreeCADBin;$env:Path"
Write-Host "[INFO] 已为当前 PowerShell 会话加入 PATH：$FreeCADBin"
Write-Host "[INFO] 验证：where FreeCAD ; where ccx"

