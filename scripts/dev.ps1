param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('doctor')]
    [string]$CommandName
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

# With a WSL distro, run the same source entry point inside Linux. Docker and
# application services belong to that environment. The doctor will reject a
# repository opened under /mnt/c and explain why.
$wsl = Get-Command 'wsl.exe' -ErrorAction SilentlyContinue
if ($wsl) {
    & $wsl.Source --list --quiet 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        & $wsl.Source --cd $projectRoot --exec python3 ./scripts/dev $CommandName
        exit $LASTEXITCODE
    }
}

# Without a working distro, the host doctor still reports all missing setup
# requirements in one JSON result instead of merely returning the WSL error.
& python (Join-Path $PSScriptRoot 'dev') $CommandName
exit $LASTEXITCODE
