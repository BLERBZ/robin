param(
    [string]$TaskName = "Kait Up"
)

schtasks /Delete /TN "$TaskName" /F | Out-Null
Write-Host "Removed scheduled task: $TaskName"
