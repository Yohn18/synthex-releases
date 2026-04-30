# YohnShell — AI-Powered Dev Terminal by Yohn18

$Host.UI.RawUI.WindowTitle = "YohnShell"

# ── ANSI helpers ──────────────────────────────────────────────────────────────
$ESC = [char]27
$R   = "$ESC[0m"
$B   = "$ESC[1m"
$PRP = "$ESC[38;5;135m"
$CYN = "$ESC[38;5;51m"
$GRN = "$ESC[38;5;82m"
$YEL = "$ESC[38;5;220m"
$RED = "$ESC[38;5;196m"
$GRY = "$ESC[38;5;244m"
$WHT = "$ESC[97m"

Clear-Host

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "${PRP}${B}  ██╗   ██╗ ██████╗ ██╗  ██╗███╗  ██╗${R}"
Write-Host "${PRP}${B}  ╚██╗ ██╔╝██╔═══██╗██║  ██║████╗ ██║${R}"
Write-Host "${PRP}${B}   ╚████╔╝ ██║   ██║███████║██╔██╗██║${R}"
Write-Host "${PRP}${B}    ╚██╔╝  ██║   ██║██╔══██║██║╚████║${R}"
Write-Host "${PRP}${B}     ██║   ╚██████╔╝██║  ██║██║ ╚███║${R}"
Write-Host "${PRP}${B}     ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚══╝${R}"
Write-Host "${CYN}${B}  ███████╗██╗  ██╗███████╗██╗     ██╗     ${R}"
Write-Host "${CYN}${B}  ██╔════╝██║  ██║██╔════╝██║     ██║     ${R}"
Write-Host "${CYN}${B}  ███████╗███████║█████╗  ██║     ██║     ${R}"
Write-Host "${CYN}${B}  ╚════██║██╔══██║██╔══╝  ██║     ██║     ${R}"
Write-Host "${CYN}${B}  ███████║██║  ██║███████╗███████╗███████╗${R}"
Write-Host "${CYN}${B}  ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝${R}"
Write-Host ""
Write-Host "  ${GRY}AI-Powered Dev Terminal  ·  by ${WHT}Yohn18${R}"
Write-Host "  ${GRY}$('─' * 48)${R}"
Write-Host ""

# ── Greeting ──────────────────────────────────────────────────────────────────
$now      = Get-Date
$hour     = $now.Hour
$greeting = if ($hour -lt 12) { "Selamat pagi" } elseif ($hour -lt 17) { "Selamat siang" } else { "Selamat malam" }
$dateStr  = $now.ToString("dddd, dd MMMM yyyy  HH:mm")
Write-Host "  ${GRN}${B}$greeting, Yohn!${R}  ${GRY}$dateStr${R}"
Write-Host ""

# ── Environment ───────────────────────────────────────────────────────────────
$_keysFile = Join-Path $PSScriptRoot ".yohn_keys.ps1"
if (Test-Path $_keysFile) { . $_keysFile }

$projectsPath = "D:\Yohn Project"
$synthexPath  = "$projectsPath\synthex"
Set-Location $projectsPath

# ── Git status synthex ────────────────────────────────────────────────────────
$branch = git -C $synthexPath branch --show-current 2>$null
if ($branch) {
    $ahead    = (git -C $synthexPath rev-list "origin/$branch..HEAD" 2>$null | Measure-Object -Line).Lines
    $dirty    = (git -C $synthexPath status --porcelain 2>$null | Measure-Object -Line).Lines
    $aheadTxt = if ($ahead -gt 0) { " ${YEL}↑$ahead ahead${R}" } else { "" }
    $dirtyTxt = if ($dirty -gt 0) { " ${YEL}~$dirty unsaved${R}" } else { " ${GRN}✓ clean${R}" }
    Write-Host "  ${PRP}synthex${R}  ${WHT}$branch${R}$aheadTxt$dirtyTxt"
    Write-Host ""
}

# ── Commands hint ─────────────────────────────────────────────────────────────
Write-Host "  ${GRY}${B}ai${R} ${GRY}<tanya>  ${B}ai${R}${GRY}(chat)  ${B}ai reset${R}${GRY}   ${PRP}synthex   build   gs   glog${R}"
Write-Host "  ${GRY}$('─' * 48)${R}"
Write-Host ""

# ══════════════════════════════════════════════════════════════════════════════
#  AI AGENT — YohnAI
# ══════════════════════════════════════════════════════════════════════════════

$_YOHNAI_SYSTEM = @"
Kamu adalah YohnAI, AI assistant yang terintegrasi langsung di YohnShell terminal milik Yohn18.
Kamu bisa membantu: coding, membuat aplikasi, debug, menjalankan perintah, analisis, dan segala hal teknis.
Selalu jawab dalam Bahasa Indonesia kecuali diminta lain.
Jika menghasilkan kode PowerShell yang bisa dijalankan, bungkus dalam ```powershell ... ```.
Jika menghasilkan kode Python, bungkus dalam ```python ... ```.
Jika menghasilkan kode lain (js, html, dll), bungkus dalam ```namalang ... ```.
Jawaban singkat, padat, dan langsung ke inti. Gunakan bullet point jika perlu.
Proyek user ada di: D:\Yohn Project\
"@

# History percakapan — tersimpan selama sesi terminal aktif
$_YOHNAI_HISTORY = [System.Collections.Generic.List[hashtable]]::new()

function ai {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$words)
    $prompt = $words -join " "

    # Perintah khusus
    if ($prompt -eq "reset") {
        $_YOHNAI_HISTORY.Clear()
        Write-Host "  ${GRN}YohnAI: History percakapan dihapus.${R}"; Write-Host ""; return
    }
    if ($prompt -eq "history") {
        if ($_YOHNAI_HISTORY.Count -eq 0) { Write-Host "  ${GRY}(belum ada history)${R}"; return }
        Write-Host ""
        foreach ($m in $_YOHNAI_HISTORY) {
            $who = if ($m.role -eq "user") { "${YEL}Kamu  ${R}" } else { "${CYN}YohnAI${R}" }
            $txt = $m.content -replace "`n"," " | ForEach-Object { if ($_.Length -gt 80) { $_.Substring(0,80) + "..." } else { $_ } }
            Write-Host "  $who ${GRY}$txt${R}"
        }
        Write-Host ""; return
    }

    # Mode tanpa argumen → chat interaktif terus-menerus
    if (-not $prompt) {
        Write-Host ""
        Write-Host "  ${CYN}${B}YohnAI Chat${R} ${GRY}— ketik pesan, '${WHT}exit${GRY}' untuk keluar, '${WHT}reset${GRY}' untuk hapus history${R}"
        Write-Host "  ${GRY}$('─' * 48)${R}"
        Write-Host ""
        while ($true) {
            Write-Host "  ${YEL}Kamu:${R} " -NoNewline
            $input = Read-Host
            if ($input -eq "exit" -or $input -eq "quit") { Write-Host ""; break }
            if ($input -eq "reset") {
                $_YOHNAI_HISTORY.Clear()
                Write-Host "  ${GRN}History dihapus.${R}"; Write-Host ""; continue
            }
            if (-not $input.Trim()) { continue }
            _yohnai_send $input
        }
        return
    }

    _yohnai_send $prompt
}

function _yohnai_send {
    param([string]$prompt)

    $_YOHNAI_HISTORY.Add(@{ role = "user"; content = $prompt })

    $messages = @(@{ role = "system"; content = $_YOHNAI_SYSTEM })
    foreach ($m in $_YOHNAI_HISTORY) { $messages += $m }

    # ── Model priority chain ─────────────────────────────────────────────────
    # Groq (cepat, gratis) → OpenRouter (fallback)
    $script:_modelChain = @(
        @{ provider="groq";        model="llama-3.3-70b-versatile";              label="llama3.3-70b"    },
        @{ provider="groq";        model="llama-3.1-70b-versatile";              label="llama3.1-70b"    },
        @{ provider="groq";        model="deepseek-r1-distill-llama-70b";        label="deepseek-r1-70b" },
        @{ provider="groq";        model="llama-3.1-8b-instant";                 label="llama3.1-8b"     },
        @{ provider="openrouter";  model="meta-llama/llama-3.3-70b-instruct:free"; label="or:llama3.3"  },
        @{ provider="openrouter";  model="google/gemini-flash-1.5";              label="or:gemini-flash" },
        @{ provider="openrouter";  model="openai/gpt-4o-mini";                   label="or:gpt4o-mini"   }
    )

    Write-Host ""
    Write-Host "  ${CYN}${B}YohnAI${R} ${GRY}▸ thinking...${R}" -NoNewline

    $res   = $null
    $reply = $null
    $usedLabel = ""

    foreach ($m in $script:_modelChain) {
        try {
            if ($m.provider -eq "groq") {
                $headers = @{ "Authorization" = "Bearer $env:GROQ_API_KEY"; "Content-Type" = "application/json" }
                $uri     = "https://api.groq.com/openai/v1/chat/completions"
            } else {
                $headers = @{ "Authorization" = "Bearer $env:OPENROUTER_API_KEY"; "Content-Type" = "application/json" }
                $uri     = "https://openrouter.ai/api/v1/chat/completions"
            }
            $body = @{
                model       = $m.model
                messages    = $messages
                max_tokens  = 2048
                temperature = 0.7
            } | ConvertTo-Json -Depth 10

            $res       = Invoke-RestMethod -Uri $uri -Method POST -Headers $headers -Body $body
            $reply     = $res.choices[0].message.content
            $usedLabel = $m.label
            break
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            # 429 = rate limit, 503 = overloaded → coba model berikutnya
            if ($code -in @(429, 503, 500) -or $_.Exception.Message -match "decommission|overload|rate.limit") {
                continue
            }
            # Error lain (auth, network) → stop
            throw
        }
    }

    if (-not $reply) {
        Write-Host "`r  ${RED}YohnAI: Semua model tidak tersedia saat ini. Coba lagi nanti.${R}"
        $_YOHNAI_HISTORY.RemoveAt($_YOHNAI_HISTORY.Count - 1)
        Write-Host ""; return
    }

    try {
        # Simpan reply ke history
        $_YOHNAI_HISTORY.Add(@{ role = "assistant"; content = $reply })
        # Batasi history max 20 pasang pesan
        while ($_YOHNAI_HISTORY.Count -gt 40) { $_YOHNAI_HISTORY.RemoveAt(0) }

        Write-Host "`r  ${CYN}${B}YohnAI${R} ${GRY}▸ [$usedLabel]${R}              "
        Write-Host ""

        $lines   = $reply -split "`n"
        $inCode  = $false
        $codeBuf = [System.Collections.Generic.List[string]]::new()
        $codeLang = ""

        foreach ($line in $lines) {
            if ($line -match '^```(\w*)') {
                if (-not $inCode) {
                    $inCode   = $true
                    $codeLang = if ($matches[1]) { $matches[1] } else { "code" }
                    $codeBuf.Clear()
                    Write-Host "  ${GRY}┌─ $codeLang ─────────────────────────────${R}"
                } else {
                    $inCode = $false
                    Write-Host "  ${GRY}└────────────────────────────────────────${R}"
                    Write-Host ""
                    $captured = $codeBuf.ToArray()
                    if ($codeLang -in @("powershell","ps1","pwsh")) {
                        Write-Host "  ${YEL}Jalankan? ${WHT}[y/N]${R} " -NoNewline
                        $c = Read-Host
                        if ($c -eq "y" -or $c -eq "Y") {
                            Write-Host ""
                            $captured | ForEach-Object { Invoke-Expression $_ }
                            Write-Host ""
                        }
                    } elseif ($codeLang -in @("python","py")) {
                        Write-Host "  ${YEL}Jalankan Python? ${WHT}[y/N]${R} " -NoNewline
                        $c = Read-Host
                        if ($c -eq "y" -or $c -eq "Y") {
                            $tmp = [System.IO.Path]::GetTempFileName() -replace '\.tmp$','.py'
                            $captured | Set-Content $tmp -Encoding UTF8
                            python $tmp
                            Remove-Item $tmp -ErrorAction SilentlyContinue
                            Write-Host ""
                        }
                    }
                }
            } elseif ($inCode) {
                $codeBuf.Add($line)
                Write-Host "  ${GRN}  $line${R}"
            } else {
                if ($line.Trim() -ne "") {
                    Write-Host "  ${WHT}$line${R}"
                } else {
                    Write-Host ""
                }
            }
        }
        Write-Host ""
    } catch {
        Write-Host "`r  ${RED}YohnAI error: $($_.Exception.Message)${R}"
        if ($_.ErrorDetails.Message) {
            try {
                $err = $_.ErrorDetails.Message | ConvertFrom-Json
                Write-Host "  ${RED}$($err.error.message)${R}"
            } catch { Write-Host "  ${RED}$($_.ErrorDetails.Message)${R}" }
        }
        Write-Host ""
    }
}

# ── AI Welcome (cepat, non-blocking via background job) ───────────────────────
$_welcomeJob = Start-Job -ScriptBlock {
    param($key, $hour)
    $headers = @{ "Authorization" = "Bearer $key"; "Content-Type" = "application/json" }
    $tod     = if ($hour -lt 12) { "pagi" } elseif ($hour -lt 17) { "siang" } else { "malam" }
    $body = @{
        model    = "llama-3.1-8b-instant"
        messages = @(
            @{ role = "system"; content = "Kamu YohnAI di YohnShell. Sambut Yohn dengan 1 kalimat singkat, segar, dan motivatif. Sebut siap bantu coding dan buat aplikasi. Bahasa Indonesia. Tanpa tanda bintang atau markdown." },
            @{ role = "user";   content = "Sambut sesi $tod ini." }
        )
        max_tokens = 60; temperature = 0.95
    } | ConvertTo-Json -Depth 5
    try {
        $r = Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/chat/completions" `
                 -Method POST -Headers $headers -Body $body
        $r.choices[0].message.content.Trim()
    } catch { "" }
} -ArgumentList $env:GROQ_API_KEY, $hour

# Tunggu max 4 detik lalu tampilkan
$null = Wait-Job $_welcomeJob -Timeout 4
$_welcomeMsg = Receive-Job $_welcomeJob 2>$null
Remove-Job $_welcomeJob -Force 2>$null
if ($_welcomeMsg) {
    Write-Host "  ${CYN}${B}YohnAI${R}  ${WHT}$_welcomeMsg${R}"
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  ALIASES & FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

function synthex { python "$synthexPath\main.py" }
function build {
    Write-Host "${YEL}Building Synthex...${R}"
    Set-Location $synthexPath
    pyinstaller Synthex.spec
}
function gs    { git status }
function glog  { git log --oneline --graph --decorate -20 }
function gpush { git push }
function gadd  { git add -A }
function gcom  { param([string]$msg) git commit -m $msg }

function prompt {
    $loc = (Get-Location).Path -replace [regex]::Escape($projectsPath), "~yohn"
    $gb  = git branch --show-current 2>$null
    $branchPart = if ($gb) { " ${PRP}($gb)${R}" } else { "" }
    "${CYN}${B}yohn${R}${GRY}:${R}${WHT}$loc${R}$branchPart ${YEL}❯${R} "
}
