param(
    [string]$FreeCADCmd = $env:FREECAD_CMD,
    [string]$GmshCmd = $env:GMSH_CMD,
    [string]$CalculixCmd = $env:CALCULIX_CMD,
    [switch]$SetUserEnvironment
)

$ErrorActionPreference = 'Stop'

function Resolve-Executable([string]$Configured, [string[]]$Names) {
    if ($Configured -and (Test-Path -LiteralPath $Configured -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $Configured).Path
    }
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

$resolved = @{
    freecad = Resolve-Executable $FreeCADCmd @('FreeCADCmd.exe', 'FreeCAD')
    gmsh = Resolve-Executable $GmshCmd @('gmsh.exe', 'gmsh')
    calculix = Resolve-Executable $CalculixCmd @('ccx.exe', 'calculix.exe', 'ccx')
}

foreach ($kind in @('freecad', 'gmsh', 'calculix')) {
    if ($resolved[$kind]) {
        Write-Host ("{0}: {1}" -f $kind, $resolved[$kind])
        if ($SetUserEnvironment) {
            $envName = @{ freecad='FREECAD_CMD'; gmsh='GMSH_CMD'; calculix='CALCULIX_CMD' }[$kind]
            [Environment]::SetEnvironmentVariable($envName, $resolved[$kind], 'User')
        }
    } else {
        Write-Host ("{0}: MISSING" -f $kind) -ForegroundColor Yellow
    }
}

$qwen = [bool](($env:QWEN_API_KEY -as [string]).Trim())
Write-Host ("QWEN_API_KEY: {0}" -f ($(if ($qwen) { 'configured' } else { 'MISSING' })))
$physicsReady = ($resolved.Values | Where-Object { -not $_ }).Count -eq 0
$liveReady = $physicsReady -and $qwen
Write-Host ("ready_for_physics: {0}" -f $physicsReady)
Write-Host ("ready_for_live: {0}" -f $liveReady)
if (-not $liveReady) { exit 2 }
