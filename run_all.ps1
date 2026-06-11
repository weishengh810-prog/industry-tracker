$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
& python (Join-Path $ProjectRoot "scripts/run_pipeline.py") @args
exit $LASTEXITCODE
