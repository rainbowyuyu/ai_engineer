param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$inpDir = Join-Path $RepoRoot "examples\\example1"
$besoDir = Join-Path $RepoRoot "beso"
$inp = Join-Path $inpDir "Plane_mesh.inp"

if (-not (Test-Path $inp)) { throw "未找到 inp：$inp" }

Push-Location $inpDir
try {
  python (Join-Path $besoDir "beso_main.py") $inp
} finally {
  Pop-Location
}

