param(
  [string]$OutFile = "$env:USERPROFILE\\.claude\\kait-hooks.json"
)

$ErrorActionPreference = "Stop"

$kaitDir = Resolve-Path (Join-Path $PSScriptRoot "..") | Select-Object -ExpandProperty Path
$claudeDir = Split-Path -Parent $OutFile
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null

$observePath = Join-Path $kaitDir "hooks\\observe.py"
if (!(Test-Path $observePath)) {
  throw "observe.py not found at: $observePath"
}

# Claude Code expects absolute paths for hook commands.
$cmd = "python `"$observePath`""

$hooks = @{
  hooks = @{
    PreToolUse         = @(@{ matcher = ""; hooks = @(@{ type = "command"; command = $cmd }) })
    PostToolUse        = @(@{ matcher = ""; hooks = @(@{ type = "command"; command = $cmd }) })
    PostToolUseFailure = @(@{ matcher = ""; hooks = @(@{ type = "command"; command = $cmd }) })
    UserPromptSubmit   = @(@{ matcher = ""; hooks = @(@{ type = "command"; command = $cmd }) })
  }
}

$json = $hooks | ConvertTo-Json -Depth 8
Set-Content -Path $OutFile -Value $json -Encoding utf8

Write-Host "[kait] wrote:" $OutFile
Write-Host "[kait] next: merge the hooks object into ~/.claude/settings.json (see docs/claude_code.md)"

