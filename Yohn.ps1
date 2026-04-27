# Yohn.ps1 — Custom PowerShell profile for Yohn's terminal
# Auto-loads on "Yohn" Windows Terminal profile

$Host.UI.RawUI.WindowTitle = "Yohn Terminal · Synthex"

# ── ANSI helpers ──────────────────────────────────────────────────────────────
$ESC  = [char]27
$R    = "$ESC[0m"
$B    = "$ESC[1m"
$DIM  = "$ESC[2m"
$PRP  = "$ESC[38;5;135m"
$CYN  = "$ESC[38;5;51m"
$GRN  = "$ESC[38;5;82m"
$YEL  = "$ESC[38;5;220m"
$RED  = "$ESC[38;5;196m"
$GRY  = "$ESC[38;5;244m"
$WHT  = "$ESC[97m"

Clear-Host

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "${PRP}${B}  ███████╗██╗   ██╗███╗   ██╗████████╗██╗  ██╗███████╗██╗  ██╗${R}"
Write-Host "${PRP}${B}  ██╔════╝╚██╗ ██╔╝████╗  ██║╚══██╔══╝██║  ██║██╔════╝╚██╗██╔╝${R}"
Write-Host "${PRP}${B}  ███████╗ ╚████╔╝ ██╔██╗ ██║   ██║   ███████║█████╗   ╚███╔╝ ${R}"
Write-Host "${PRP}${B}  ╚════██║  ╚██╔╝  ██║╚██╗██║   ██║   ██╔══██║██╔══╝   ██╔██╗ ${R}"
Write-Host "${PRP}${B}  ███████║   ██║   ██║ ╚████║   ██║   ██║  ██║███████╗██╔╝ ██╗${R}"
Write-Host "${PRP}${B}  ╚══════╝   ╚═╝   ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝${R}"
Write-Host ""
Write-Host "  ${CYN}${B}Yohn's Terminal${R}  ${GRY}—${R}  ${WHT}Synthex Dev Environment${R}  ${GRY}by Yohn18${R}"
Write-Host "  ${GRY}$('─' * 60)${R}"
Write-Host ""

# ── Date / time greeting ──────────────────────────────────────────────────────
$now  = Get-Date
$hour = $now.Hour
$greeting = if ($hour -lt 12) { "Selamat pagi" } elseif ($hour -lt 17) { "Selamat siang" } else { "Selamat malam" }
$dateStr  = $now.ToString("dddd, dd MMMM yyyy  HH:mm")

Write-Host "  ${GRN}${B}$greeting, Yohn!${R}  ${GRY}$dateStr${R}"
Write-Host ""

# ── Git status (if inside synthex repo) ──────────────────────────────────────
$synthexPath = "C:\Users\Admin\synthex"
Set-Location $synthexPath

$branch = git branch --show-current 2>$null
if ($branch) {
    $ahead  = (git rev-list "origin/$branch..HEAD" 2>$null | Measure-Object -Line).Lines
    $dirty  = (git status --porcelain 2>$null | Measure-Object -Line).Lines
    $aheadTxt  = if ($ahead  -gt 0) { "  ${YEL}↑$ahead ahead${R}" }  else { "" }
    $dirtyTxt  = if ($dirty  -gt 0) { "  ${YEL}~$dirty unsaved${R}" } else { "  ${GRN}clean${R}" }
    Write-Host "  ${CYN}git${R}  ${WHT}$branch${R}$aheadTxt$dirtyTxt"
    Write-Host ""
}

# ── Quick commands ────────────────────────────────────────────────────────────
Write-Host "  ${GRY}Quick commands:${R}"
Write-Host "  ${PRP}synthex${R}    ${GRY}— buka Synthex GUI${R}"
Write-Host "  ${PRP}build${R}      ${GRY}— build Synthex.exe${R}"
Write-Host "  ${PRP}gs${R}         ${GRY}— git status${R}"
Write-Host "  ${PRP}glog${R}       ${GRY}— git log ringkas${R}"
Write-Host ""
Write-Host "  ${GRY}$('─' * 60)${R}"
Write-Host ""

# ── Aliases ───────────────────────────────────────────────────────────────────
function synthex  { python "$synthexPath\main.py" }
function build    {
    Write-Host "${YEL}Building Synthex...${R}"
    Set-Location $synthexPath
    pyinstaller Synthex.spec
}
function gs    { git status }
function glog  { git log --oneline --graph --decorate -20 }
function gpush { git push }
function gadd  { git add -A }
function gcom  { param([string]$msg) git commit -m $msg }

# ── Custom prompt ─────────────────────────────────────────────────────────────
function prompt {
    $loc = (Get-Location).Path -replace [regex]::Escape($synthexPath), "~synthex"
    $gb  = git branch --show-current 2>$null
    $branchPart = if ($gb) { " ${PRP}($gb)${R}" } else { "" }
    "${CYN}${B}yohn${R}${GRY}:${R}${WHT}$loc${R}$branchPart ${YEL}❯${R} "
}
