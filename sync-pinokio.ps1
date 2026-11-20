# ChessGrind Pinokio sync. Run after stopping ChessGrind in Pinokio.
# Backs up the SQLite database, preserves dirty repo changes using Git stash,
# updates with fast-forward only, and rebuilds local chess intelligence.
# This script intentionally NEVER deletes user data, force-resets Git, or
# automatically restores older app files over the new release.
param(
    [string]$PinokioFolder = "C:\pinokio\api\ChessGrind",
    [switch]$SkipDependencies,
    [switch]$SkipKnowledgeRebuild
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Run-Checked {
    param([string]$Command,[string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Failed ($LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

$installed = Join-Path $PinokioFolder "app"
if (Test-Path (Join-Path $installed ".git")) {
    $repo = $installed
} elseif (Test-Path (Join-Path $PinokioFolder ".git")) {
    $repo = $PinokioFolder
} else {
    throw "Could not locate the ChessGrind Git checkout in $PinokioFolder. No files changed."
}
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "ChessGrind's Python environment was not found at $python. Repair the Pinokio installation first. No files changed."
}
$backupFolder = Join-Path $PinokioFolder ("sync-backups\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
Write-Host "ChessGrind checkout: $repo"
Write-Host "Backup destination: $backupFolder"

# SQLite online-backup API works even if an ordinary game database uses WAL.
$database = Join-Path $repo "userdata\chess.db"
if (Test-Path $database) {
    $dst = Join-Path $backupFolder "chess-before-update.db"
    $dbScript = @'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
print("Saved verified SQLite backup:",sys.argv[2])
'@
    $dbScript | & $python - $database $dst
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dst)) {
        throw "Database backup failed. Sync aborted without changing Git."
    }
}

# Preserve the custom outer Pinokio wrappers used by legacy nested layouts.
$launchers = @("pinokio.js","start.js","install.js","update.js","doctor.js","pinokio.json")
$launcherBackup = Join-Path $backupFolder "legacy-launcher"
New-Item -ItemType Directory -Force -Path $launcherBackup | Out-Null
foreach ($name in $launchers) {
    $source = Join-Path $PinokioFolder $name
    if (Test-Path $source) { Copy-Item -LiteralPath $source -Destination $launcherBackup -Force }
}

# The installed app may contain modified tracked files from prior repairs.
# Stash these (and untracked files) rather than discarding or overwriting them.
Push-Location $repo
try {
    Run-Checked "git" @("rev-parse","--is-inside-work-tree")
    $changes = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect Git status. No source update attempted." }
    if ($changes.Count -gt 0) {
        $label = "ChessGrind Pinokio local changes before release sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        Run-Checked "git" @("stash","push","--include-untracked","-m",$label)
        Write-Warning "Local source changes were preserved in Git stash, NOT discarded and NOT automatically reapplied."
        & git stash list -n 1
    }
    Run-Checked "git" @("fetch","origin","main")
    Run-Checked "git" @("merge","--ff-only","origin/main")
    Write-Host "ChessGrind source updated to:"
    Run-Checked "git" @("log","-1","--format=%h %s")
} finally {
    Pop-Location
}

# In the older Pinokio layout the outer menu is not part of the app Git
# checkout. Refresh just its Update action, after preserving its old copy.
# That makes future menu-based updates use this same safe sync workflow.
$legacyUpdate = Join-Path $PinokioFolder "update.js"
if (([IO.Path]::GetFullPath($repo)) -ne ([IO.Path]::GetFullPath($PinokioFolder)) -and
    (Test-Path $legacyUpdate)) {
    $updatedLauncher = @'
module.exports = {
  run:[{method:"shell.run",params:{
    path:"app",
    message:"powershell -NoProfile -ExecutionPolicy Bypass -File sync-pinokio.ps1 -PinokioFolder .."
  }}]
};
'@
    [IO.File]::WriteAllText($legacyUpdate,$updatedLauncher,
                            (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Legacy Pinokio Update menu repaired for future safe releases."
}

Push-Location $repo
try {
    if (-not $SkipDependencies) {
        Run-Checked $python @("-m","pip","install","-r","requirements.txt")
    }
    # The small 3-/4-piece set is a deliberate, bounded download.
    try {
        Run-Checked $python @("install_syzygy.py","--pieces","4")
    } catch {
        Write-Warning "Exact endgame data setup was unavailable; Stockfish remains usable. $($_.Exception.Message)"
    }
    if (-not $SkipKnowledgeRebuild) {
        Run-Checked $python @("chess_knowledge.py","build","--master-games","150")
        try {
            Run-Checked $python @("chess_knowledge.py","vectors")
        } catch {
            Write-Warning "Semantic vectors could not finish. Exact-position and text retrieval still work. $($_.Exception.Message)"
        }
    }
    # Refresh the local conversation engine and neural character voices.
    # A missing optional download never destroys existing chess installation.
    Run-Checked $python @("local_ai_setup.py","install")
    Run-Checked $python @("pinokio/bootstrap.py","doctor")
    Write-Host ""
    Write-Host "SUCCESS: ChessGrind source and available local knowledge updated." -ForegroundColor Green
    Write-Host "Your games were preserved. Database backup: $backupFolder"
    Write-Host "Restart ChessGrind with Start in Pinokio, then Ctrl+Shift+R in the browser."
    Write-Host "If you had local source edits, inspect 'git stash list' before restoring any older files."
} finally {
    Pop-Location
}
