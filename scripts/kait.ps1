param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$KaitArgs
)

Write-Host "[deprecated] scripts/kait.ps1 is deprecated. Use: python -m kait.cli <command>" -ForegroundColor Yellow
python -m kait.cli @KaitArgs
exit $LASTEXITCODE
