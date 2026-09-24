$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$demoScript = Join-Path $PSScriptRoot 'scripts\share_demo.py'
if (-not (Test-Path -LiteralPath $projectPython)) {
    Write-Host 'The shared demo is not installed.'
    exit 0
}
& $projectPython $demoScript --stop
if ($LASTEXITCODE -ne 0) { throw 'Could not request a demo shutdown.' }
$demoDeadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $demoDeadline) {
    $demoStatus = & $projectPython $demoScript --status | ConvertFrom-Json
    if (-not $demoStatus.running) {
        Write-Host 'The shared demo is stopped. Saved content and login remain available for the next start.'
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Shutdown is still in progress. Run this command again to check; no unrelated process has been stopped.'
