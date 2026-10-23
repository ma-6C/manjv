$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) { $runtime = $bundledPython }
else { $runtime = (Get-Command python -ErrorAction Stop).Source }
& $runtime -m pip install --target (Join-Path $PSScriptRoot 'vendor') --cache-dir (Join-Path $PSScriptRoot 'tmp\pip-cache') -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查上方错误信息。' }
