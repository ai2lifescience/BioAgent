$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$ProjectRoot$([IO.Path]::PathSeparator)$env:PYTHONPATH"
} else {
    $ProjectRoot
}
$PythonCommand = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $PythonCommand -m bacvf @args
exit $LASTEXITCODE
