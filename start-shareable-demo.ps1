$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$demoScript = Join-Path $PSScriptRoot 'scripts\share_demo.py'
$demoState = Join-Path $PSScriptRoot 'backend\.local\shared-demo'

if (-not (Test-Path -LiteralPath $projectPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required.' }
}

$demoStatus = & $projectPython $demoScript --status | ConvertFrom-Json
if (-not $demoStatus.running) {
    Write-Host 'Preparing the temporary HTTPS demonstration...'
    & $projectPython -m pip install --disable-pip-version-check --quiet -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    New-Item -ItemType Directory -Path $demoState -Force | Out-Null
    # Windows command-line quoting: both paths are fixed local filesystem paths.
    $demoArguments = '"' + $demoScript + '" --supervise'
    Start-Process -FilePath $projectPython -ArgumentList $demoArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $demoState 'launcher.stdout.log') -RedirectStandardError (Join-Path $demoState 'launcher.stderr.log') | Out-Null
    Start-Sleep -Seconds 1
}

$demoDeadline = (Get-Date).AddMinutes(6)
$lastStage = ''
while ((Get-Date) -lt $demoDeadline) {
    $demoStatus = & $projectPython $demoScript --status | ConvertFrom-Json
    if ($demoStatus.state -eq 'ready' -and $demoStatus.running) {
        Write-Host ''
        Write-Host ('Website: ' + $demoStatus.website)
        Write-Host ('Content editor: ' + $demoStatus.editor)
        Write-Host 'Login details: backend/.local/shared-demo/access.txt'
        Write-Host 'Sign in with your username and password. Published changes appear automatically.'
        Write-Host 'Keep this PC awake and online. The temporary URL expires when the demo stops.'
        Write-Host 'Stop with: .\stop-shareable-demo.ps1'
        exit 0
    }
    if ($demoStatus.state -eq 'failed') {
        throw ('Demo startup failed: ' + $demoStatus.error + ' Logs: backend/.local/shared-demo/')
    }
    if ($demoStatus.state -eq 'unavailable') {
        throw 'The demo process is running, but its public HTTPS link is unavailable. Check this PC is online. If it stays unavailable, run .\stop-shareable-demo.ps1 and then .\start-shareable-demo.ps1 to obtain a new link. Saved content and login will be retained.'
    }
    if (-not $demoStatus.running) {
        throw 'The demo launcher stopped. See backend/.local/shared-demo/launcher.stderr.log.'
    }
    if ($demoStatus.stage -and $demoStatus.stage -ne $lastStage) {
        Write-Host $demoStatus.stage
        $lastStage = $demoStatus.stage
    }
    Start-Sleep -Seconds 2
}
throw 'The demo is still preparing. Run this command again to check its status, or run stop-shareable-demo.ps1.'
