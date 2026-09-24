$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required.' }
}
& $projectPython -m pip install --disable-pip-version-check --quiet -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$env:KONTTURI_ENV = 'local'
& $projectPython backend/manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Database setup failed.' }
& $projectPython backend/manage.py seed_site
if ($LASTEXITCODE -ne 0) { throw 'Content import failed.' }
& $projectPython backend/manage.py setup_roles
if ($LASTEXITCODE -ne 0) { throw 'Role setup failed.' }
& $projectPython backend/manage.py bootstrap_demo
if ($LASTEXITCODE -ne 0) { throw 'Demo account setup failed.' }
& $projectPython backend/manage.py collectstatic --noinput --verbosity 0
if ($LASTEXITCODE -ne 0) { throw 'Static asset setup failed.' }
Write-Host ''
Write-Host 'Website: http://127.0.0.1:8000/'
Write-Host 'Content editor: http://127.0.0.1:8000/admin/'
Write-Host 'Login details: backend/.local/demo-access.txt'
Write-Host 'First login includes authenticator setup. Stop with Ctrl+C.'
& $projectPython backend/manage.py runserver 127.0.0.1:8000 --noreload --nostatic
