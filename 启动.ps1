$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) { $runtime = $bundledPython }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $runtime = (Get-Command python).Source }
else { throw '请先安装 Python 3.10 或更高版本。' }
$windowRuntime = Join-Path (Split-Path $runtime -Parent) 'pythonw.exe'
if (Test-Path -LiteralPath $windowRuntime) {
    Start-Process -FilePath $windowRuntime -ArgumentList @('desktop.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
} else {
    & $runtime desktop.py
}
