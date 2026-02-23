param(
  [string]$KaitdUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"

Write-Host ("Kaitd health: {0}/health" -f $KaitdUrl)
$res = Invoke-RestMethod -Uri ("{0}/health" -f $KaitdUrl) -Method Get -TimeoutSec 5
$res | ConvertTo-Json -Depth 8

