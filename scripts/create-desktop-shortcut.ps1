# Create Desktop and Start Menu shortcuts for the lightsheet app on the rig.
#
# Run on the microscope PC after `git pull`:
#   powershell -ExecutionPolicy Bypass -File scripts\create-desktop-shortcut.ps1
#
# Writes four shortcuts (idempotent - re-running overwrites them):
#   Desktop:            Lightsheet.lnk, Lightsheet Demo.lnk
#   Start Menu\Programs\Lightsheet\: Lightsheet.lnk, Lightsheet Demo.lnk
#
# Safety invariants:
#   - TargetPath always points inside the repo's own .venv (lightsheetw.exe,
#     the no-console launcher produced by `uv sync`).
#   - WorkingDirectory is pinned to the repo root so the app starts even if
#     the shortcut is invoked from an unexpected location.
#   - No user input is interpolated into any .lnk field.

param(
    # Repo root; defaults to the parent of this script's directory so the
    # script works from any current location.
    [string]$RepoRoot = (Split-Path $PSScriptRoot -Parent),
    # Skip the `uv sync` preflight (offline or dry-run use).
    [switch]$SkipSync,
    # Print what would be created without writing any .lnk files.
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

# Preflight: make sure the venv exists and matches the lockfile, which is
# what produces .venv\Scripts\lightsheetw.exe. Skipped under -WhatIf so a
# dry run does not mutate .venv.
if (-not $SkipSync -and -not $WhatIf) {
    Push-Location $RepoRoot
    try {
        uv sync
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

$Exe  = Join-Path $RepoRoot ".venv\Scripts\lightsheetw.exe"
$Icon = Join-Path $RepoRoot "lightsheet\resources\lightsheet.ico"

# Never write a shortcut that points at a missing target or icon.
if (-not (Test-Path $Exe))  { throw "Missing $Exe - run this script without -SkipSync so 'uv sync' can create it" }
if (-not (Test-Path $Icon)) { throw "Missing $Icon - the committed icon asset must be present in the checkout" }

$Wsh = New-Object -ComObject WScript.Shell
try {
    $startMenuBase = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Lightsheet"
    if ($WhatIf) {
        Write-Output "Would ensure Start Menu folder exists: $startMenuBase"
    } else {
        $null = New-Item -ItemType Directory -Force -Path $startMenuBase
    }

    $bases = @(
        $Wsh.SpecialFolders("Desktop"),
        $startMenuBase
    )
    $shortcuts = @(
        @("Lightsheet.lnk", "", "Lightsheet microscope controller"),
        @("Lightsheet Demo.lnk", "--demo", "Lightsheet microscope controller (demo mode)")
    )

    foreach ($base in $bases) {
        foreach ($pair in $shortcuts) {
            $name = $pair[0]
            $shortcutArgs = $pair[1]
            $description = $pair[2]
            $path = Join-Path $base $name
            if ($WhatIf) {
                Write-Output "Would create $path -> $Exe $shortcutArgs"
                continue
            }
            $sc = $Wsh.CreateShortcut($path)
            $sc.TargetPath = $Exe
            $sc.WorkingDirectory = $RepoRoot
            $sc.Arguments = $shortcutArgs
            $sc.IconLocation = "$Icon,0"
            $sc.WindowStyle = 1
            $sc.Description = $description
            $sc.Save()
            Write-Output "Created $path -> $Exe $shortcutArgs"
        }
    }
} finally {
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($Wsh) | Out-Null
}
