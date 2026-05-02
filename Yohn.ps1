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
# Load key files: .yohn_keys.ps1 (local) then D:\.aiconfig.ps1 (master override)
$_keysFile = Join-Path $PSScriptRoot ".yohn_keys.ps1"
if (Test-Path $_keysFile) { . $_keysFile }
if (Test-Path "D:\.aiconfig.ps1") { . "D:\.aiconfig.ps1" }
# Normalize: .aiconfig.ps1 uses OPENROUTER_KEY / GROQ_KEY; script uses the _API_KEY form
if (-not $env:OPENROUTER_API_KEY -and $env:OPENROUTER_KEY) { $env:OPENROUTER_API_KEY = $env:OPENROUTER_KEY }
if (-not $env:GROQ_API_KEY       -and $env:GROQ_KEY)       { $env:GROQ_API_KEY       = $env:GROQ_KEY       }

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
Write-Host "  ${GRY}Ketik pertanyaan langsung, atau ketik ${WHT}help${GRY} untuk daftar perintah.${R}"
Write-Host "  ${GRY}$('─' * 48)${R}"
Write-Host ""

# ══════════════════════════════════════════════════════════════════════════════
#  AI AGENT — YohnAI
# ══════════════════════════════════════════════════════════════════════════════

$_YOHNAI_SYSTEM = @"
Kamu adalah YohnAI — asisten pribadi Yohn18 yang hidup di dalam terminal YohnShell.
Sifat kamu: santai, cerdas, to the point. Ngobrol seperti teman developer senior.
Kamu ngerti bahasa campur (Indonesia + slang + English) dan selalu paham maksud user walau kalimatnya tidak formal.

Kemampuan kamu:
- Coding semua bahasa, debug, refactor, jelasin kode
- Buat aplikasi dari nol (Python, web, Android, dll)
- Bantu setup environment, install tools, konfigurasi sistem
- Analisis error dan kasih solusi langsung
- Jalankan perintah PowerShell/Python jika diminta
- Diskusi teknis atau non-teknis

YohnShell — Tim Spesialis AI (router pilih otomatis per tugas):
- 💬 Llama 3.3 70b (Groq, gratis)     — chat umum, pertanyaan simpel
- 💻 DeepSeek R1 70b (Groq, gratis)   — coding, debug, logika
- ⚡ Qwen 2.5 72b (OpenRouter)        — coding skala besar, arsitektur
- ✨ Gemini 2.0 Flash (OpenRouter)    — dokumen panjang, analisis
- 💡 GPT-4o mini (OpenRouter)         — kreatif, brainstorm
- 🔮 Hermes 3 405b (OpenRouter)       — reasoning kompleks, multi-step, tool use
- 👑 Claude Haiku (OpenRouter)        — nuansa bahasa, sintesis

Yohn adalah pengguna vibe coding — dia memberi instruksi dalam bahasa natural, tidak nulis kode manual.
Selalu asumsikan Yohn ingin hasil langsung, bukan teori panjang.
Semua data Synthex dan YohnShell ada di SSD external — portable antar PC.

Aturan jawaban:
- Bahasa Indonesia santai, kecuali kalau user pakai English
- Singkat dan langsung — tidak bertele-tele
- Kalau ada kode PowerShell yang bisa langsung dijalankan, bungkus di ```powershell
- Kalau ada kode Python, bungkus di ```python
- Kode lain: ```namalang
- Kalau pertanyaannya simpel, jawab 1-2 kalimat. Kalau kompleks, jelaskan bertahap.
- JANGAN pura-pura menjalankan sesuatu yang tidak nyata — kalau tidak bisa, bilang terus terang.

Konteks: semua project ada di D:\Yohn Project\  — synthex ada di D:\Yohn Project\synthex\
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

# ── API helper ───────────────────────────────────────────────────────────────
function _api_call {
    param([string]$uri, [string]$key, [string]$model, $messages, [int]$maxTok = 2048, [float]$temp = 0.7)
    try {
        if (-not $key) { return $null }
        # Pastikan messages selalu array saat di-serialize ke JSON
        $msgArray = @($messages)
        $payload = [ordered]@{
            model       = $model
            messages    = $msgArray
            max_tokens  = $maxTok
            temperature = $temp
        }
        $body = $payload | ConvertTo-Json -Depth 15 -Compress
        $headers = @{ "Authorization" = "Bearer $key" }
        $r = Invoke-RestMethod -Uri $uri -Method POST -Headers $headers `
             -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 30
        return $r.choices[0].message.content
    } catch {
        $code = $null
        try { $code = $_.Exception.Response.StatusCode.value__ } catch {}
        $script:_lastApiError = "[$model] $(if ($code) {"HTTP $code — "})$($_.Exception.Message)"
        try {
            $ed = $_.ErrorDetails.Message | ConvertFrom-Json
            $script:_lastApiError += " | $($ed.error.message)"
        } catch {}
        return $null
    }
}

# ── Render reply (code blocks + run prompt) ───────────────────────────────────
function _render_reply {
    param([string]$reply)
    $lines    = $reply -split "`n"
    $inCode   = $false
    $codeBuf  = [System.Collections.Generic.List[string]]::new()
    $codeLang = ""
    foreach ($line in $lines) {
        if ($line -match '^```(\w*)') {
            if (-not $inCode) {
                $inCode = $true
                $codeLang = if ($matches[1]) { $matches[1] } else { "code" }
                $codeBuf.Clear()
                Write-Host "  ${GRY}┌─ $codeLang ──────────────────────────────${R}"
            } else {
                $inCode = $false
                Write-Host "  ${GRY}└─────────────────────────────────────────${R}"
                Write-Host ""
                $captured = $codeBuf.ToArray()
                if ($codeLang -in @("powershell","ps1","pwsh")) {
                    Write-Host "  ${YEL}Jalankan? [y/N]${R} " -NoNewline
                    $c = Read-Host
                    if ($c -eq "y" -or $c -eq "Y") { Write-Host ""; $captured | ForEach-Object { Invoke-Expression $_ }; Write-Host "" }
                } elseif ($codeLang -in @("python","py")) {
                    Write-Host "  ${YEL}Jalankan Python? [y/N]${R} " -NoNewline
                    $c = Read-Host
                    if ($c -eq "y" -or $c -eq "Y") {
                        $tmp = [System.IO.Path]::GetTempFileName() -replace '\.tmp$','.py'
                        $captured | Set-Content $tmp -Encoding UTF8
                        python $tmp; Remove-Item $tmp -ErrorAction SilentlyContinue; Write-Host ""
                    }
                }
            }
        } elseif ($inCode) {
            $codeBuf.Add($line); Write-Host "  ${GRN}  $line${R}"
        } else {
            if ($line.Trim()) { Write-Host "  ${WHT}$line${R}" } else { Write-Host "" }
        }
    }
}

function _yohnai_send {
    param([string]$prompt)

    $_YOHNAI_HISTORY.Add(@{ role = "user"; content = $prompt })

    $OR  = "https://openrouter.ai/api/v1/chat/completions"
    $GQ  = "https://api.groq.com/openai/v1/chat/completions"
    $ORK = $env:OPENROUTER_API_KEY
    $GQK = $env:GROQ_API_KEY

    # ── Urutan fallback ────────────────────────────────────────────────────────
    # Primary: Hermes 3 405b (OpenRouter berbayar, terbaik)
    # Fallback gratis: Groq Llama 3.3 → Groq DeepSeek R1 → OpenRouter free models
    $chain = @(
        @{ url=$OR; key=$ORK; model="nousresearch/hermes-3-llama-3.1-405b"; label="Hermes 3";    icon="🔮"; color=$PRP }
        @{ url=$GQ; key=$GQK; model="llama-3.3-70b-versatile";              label="Llama 3.3";   icon="💬"; color=$WHT }
        @{ url=$GQ; key=$GQK; model="deepseek-r1-distill-llama-70b";        label="DeepSeek R1"; icon="💻"; color=$GRN }
        @{ url=$GQ; key=$GQK; model="llama-3.1-8b-instant";                 label="Llama 3.1";   icon="⚡"; color=$CYN }
        @{ url=$OR; key=$ORK; model="meta-llama/llama-3.3-70b-instruct:free"; label="Llama free"; icon="💬"; color=$GRY }
        @{ url=$OR; key=$ORK; model="google/gemini-2.0-flash-exp:free";       label="Gemini free"; icon="✨"; color=$GRY }
        @{ url=$OR; key=$ORK; model="mistralai/mistral-7b-instruct:free";     label="Mistral free"; icon="💡"; color=$GRY }
    )

    $sysMsgs = [System.Collections.Generic.List[object]]::new()
    $sysMsgs.Add(@{ role="system"; content=$_YOHNAI_SYSTEM })
    foreach ($m in $_YOHNAI_HISTORY) { $sysMsgs.Add(@{ role=$m.role; content=$m.content }) }

    Write-Host ""
    Write-Host "  ${PRP}🔮${R} ${GRY}Hermes 3 mengerjakan...${R}" -NoNewline

    $reply     = $null
    $usedEntry = $chain[0]

    foreach ($entry in $chain) {
        if (-not $entry.key) { continue }
        $r = _api_call $entry.url $entry.key $entry.model $sysMsgs 2048
        if ($r) { $reply = $r; $usedEntry = $entry; break }
    }

    if (-not $reply) {
        Write-Host "`r  ${RED}YohnAI: Semua model tidak tersedia.${R}"
        if ($script:_lastApiError) { Write-Host "  ${RED}Error terakhir: $($script:_lastApiError)${R}" }
        Write-Host "  ${GRY}Cek: api (test)${R}"
        $_YOHNAI_HISTORY.RemoveAt($_YOHNAI_HISTORY.Count - 1)
        Write-Host ""; return
    }

    $_YOHNAI_HISTORY.Add(@{ role = "assistant"; content = $reply })
    while ($_YOHNAI_HISTORY.Count -gt 40) { $_YOHNAI_HISTORY.RemoveAt(0) }

    # ══ DISPLAY ════════════════════════════════════════════════════════════════
    $workerColor = $usedEntry.color
    Write-Host "`r  $($usedEntry.icon) $workerColor$($usedEntry.label)${R}                                    "
    Write-Host ""

    _render_reply $reply
    Write-Host ""
}

# ── AI Welcome (cepat, non-blocking via background job) ───────────────────────
$_welcomeJob = Start-Job -ScriptBlock {
    param($orKey, $groqKey, $hour)
    $tod = if ($hour -lt 12) { "pagi" } elseif ($hour -lt 17) { "siang" } else { "malam" }
    $sys = "Kamu YohnAI di YohnShell terminal. Sambut Yohn dengan 1 kalimat singkat, santai, dan natural — seperti teman. Bahasa Indonesia gaul. Tanpa tanda bintang atau markdown."
    $models = @(
        @{ uri="https://openrouter.ai/api/v1/chat/completions"; key=$orKey;   model="nousresearch/hermes-3-llama-3.1-405b" },
        @{ uri="https://api.groq.com/openai/v1/chat/completions"; key=$groqKey; model="llama-3.3-70b-versatile"            },
        @{ uri="https://api.groq.com/openai/v1/chat/completions"; key=$groqKey; model="llama-3.1-8b-instant"               }
    )
    foreach ($m in $models) {
        try {
            $headers = @{ "Authorization" = "Bearer $($m.key)"; "Content-Type" = "application/json" }
            $body = @{
                model    = $m.model
                messages = @(
                    @{ role = "system"; content = $sys },
                    @{ role = "user";   content = "Sambut sesi $tod ini, singkat aja." }
                )
                max_tokens = 60; temperature = 0.9
            } | ConvertTo-Json -Depth 5
            $r = Invoke-RestMethod -Uri $m.uri -Method POST -Headers $headers -Body $body
            $msg = $r.choices[0].message.content.Trim()
            if ($msg) { return $msg }
        } catch { continue }
    }
    return ""
} -ArgumentList $env:OPENROUTER_API_KEY, $env:GROQ_API_KEY, $hour

# Tunggu max 4 detik lalu tampilkan
$null = Wait-Job $_welcomeJob -Timeout 4
$_welcomeMsg = Receive-Job $_welcomeJob 2>$null
Remove-Job $_welcomeJob -Force 2>$null
if ($_welcomeMsg) {
    Write-Host "  ${CYN}${B}YohnAI${R}  ${WHT}$_welcomeMsg${R}"
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

function help {
    Write-Host ""
    Write-Host "  ${CYN}${B}YohnShell — Daftar Perintah${R}"
    Write-Host "  ${GRY}$('─' * 48)${R}"
    Write-Host ""
    Write-Host "  ${PRP}${B}AI${R}"
    Write-Host "  ${WHT}ai <pertanyaan>${R}     ${GRY}tanya YohnAI langsung${R}"
    Write-Host "  ${WHT}ai${R}                  ${GRY}masuk mode chat interaktif${R}"
    Write-Host "  ${WHT}ai reset${R}             ${GRY}hapus history percakapan${R}"
    Write-Host "  ${GRY}  atau ketik kalimat bebas → otomatis ke YohnAI${R}"
    Write-Host ""
    Write-Host "  ${PRP}${B}Synthex${R}"
    Write-Host "  ${WHT}buka${R}                 ${GRY}jalankan Synthex app${R}"
    Write-Host "  ${WHT}build${R}                ${GRY}build Synthex jadi .exe${R}"
    Write-Host "  ${WHT}edit${R}                 ${GRY}buka folder project di Explorer${R}"
    Write-Host ""
    Write-Host "  ${PRP}${B}Git${R}"
    Write-Host "  ${WHT}status${R}               ${GRY}git status${R}"
    Write-Host "  ${WHT}log${R}                  ${GRY}git log ringkas${R}"
    Write-Host "  ${WHT}push${R}                 ${GRY}git push${R}"
    Write-Host "  ${WHT}pull${R}                 ${GRY}git pull${R}"
    Write-Host "  ${WHT}add${R}                  ${GRY}git add semua perubahan${R}"
    Write-Host "  ${WHT}commit <pesan>${R}        ${GRY}git commit -m${R}"
    Write-Host "  ${WHT}simpan <pesan>${R}        ${GRY}add + commit + push sekaligus${R}"
    Write-Host ""
    Write-Host "  ${PRP}${B}Lainnya${R}"
    Write-Host "  ${WHT}goto <folder>${R}         ${GRY}pindah ke folder di Yohn Project${R}"
    Write-Host "  ${WHT}models${R}               ${GRY}lihat daftar model AI yang tersedia${R}"
    Write-Host "  ${WHT}reload${R}               ${GRY}reload YohnShell${R}"
    Write-Host "  ${WHT}clear${R}                ${GRY}bersihkan layar${R}"
    Write-Host ""
}

# ── Synthex ───────────────────────────────────────────────────────────────────
function buka   { python "$synthexPath\main.py" }
function synthex { buka }   # alias lama tetap jalan

function build {
    Write-Host ""
    Write-Host "  ${YEL}Building Synthex...${R}"
    Set-Location $synthexPath
    pyinstaller Synthex.spec
    Set-Location $projectsPath
    Write-Host "  ${GRN}Build selesai!${R}"
    Write-Host ""
}

function edit {
    explorer $synthexPath
}

# ── Git ───────────────────────────────────────────────────────────────────────
function status { git -C (Get-Location).Path status }
function log    {
    param([int]$n = 20)
    git log --oneline --graph --decorate -$n
}
function push   { git push }
function pull   { git pull }
function add    { git add -A; Write-Host "  ${GRN}Semua perubahan di-stage.${R}" }

function commit {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$words)
    $msg = $words -join " "
    if (-not $msg) { Write-Host "  ${RED}Tulis pesan commit: commit <pesan>${R}"; return }
    git commit -m $msg
}

function simpan {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$words)
    $msg = $words -join " "
    if (-not $msg) { Write-Host "  ${RED}Tulis pesan: simpan <pesan>${R}"; return }
    Write-Host "  ${YEL}Menyimpan...${R}"
    git add -A
    git commit -m $msg
    git push
    Write-Host "  ${GRN}Tersimpan dan ter-push!${R}"
    Write-Host ""
}

# ── Navigation ────────────────────────────────────────────────────────────────
function goto {
    param([string]$folder)
    if (-not $folder) { Set-Location $projectsPath; return }
    $target = Join-Path $projectsPath $folder
    if (Test-Path $target) { Set-Location $target }
    else { Write-Host "  ${RED}Folder tidak ditemukan: $target${R}" }
}

function reload {
    . "$PSScriptRoot\Yohn.ps1"
}

# ── Models list ──────────────────────────────────────────────────────────────
function models {
    Write-Host ""
    Write-Host "  ${CYN}${B}YohnAI — Model Chain${R}"
    Write-Host "  ${GRY}$('─' * 54)${R}"
    Write-Host ""
    Write-Host "  ${GRY}PRIMARY (selalu dicoba pertama)${R}"
    Write-Host "  ${WHT}${PRP}🔮 Hermes 3 405b${R}  ${GRY}OpenRouter · reasoning, coding, semua task${R}"
    Write-Host ""
    Write-Host "  ${GRY}FALLBACK GRATIS (jika Hermes limit/error)${R}"
    Write-Host "  ${WHT}💬 Llama 3.3 70b${R}  ${GRY}Groq — cepat, gratis${R}"
    Write-Host "  ${WHT}💻 DeepSeek R1${R}    ${GRY}Groq — reasoning & coding${R}"
    Write-Host "  ${WHT}⚡ Llama 3.1 8b${R}   ${GRY}Groq — ringan, gratis${R}"
    Write-Host "  ${WHT}💬 Llama free${R}     ${GRY}OpenRouter free tier${R}"
    Write-Host "  ${WHT}✨ Gemini free${R}    ${GRY}OpenRouter free tier${R}"
    Write-Host "  ${WHT}💡 Mistral free${R}   ${GRY}OpenRouter free tier${R}"
    Write-Host ""
    Write-Host "  ${GRY}Hermes 3 selalu menjawab pertama.${R}"
    Write-Host "  ${GRY}Otomatis turun ke gratis jika rate limit.${R}"
    Write-Host ""
}

# ── Backward compat aliases ───────────────────────────────────────────────────
function gs    { status }
function glog  { log }
function gpush { push }
function gadd  { add }
function gcom  { param([string]$msg) commit $msg }

function api {
    param([string]$cmd)
    if ($cmd -eq "test" -or -not $cmd) {
        Write-Host ""
        Write-Host "  ${CYN}${B}Test Koneksi API${R}"
        Write-Host "  ${GRY}$('─' * 40)${R}"
        $OR  = "https://openrouter.ai/api/v1/chat/completions"
        $GQ  = "https://api.groq.com/openai/v1/chat/completions"
        $ORK = $env:OPENROUTER_API_KEY
        $GQK = $env:GROQ_API_KEY
        $testMsg = @(@{ role="user"; content="hi" })

        Write-Host "  ${GRY}OpenRouter key:${R} $(if ($ORK) { "${GRN}ada${R}" } else { "${RED}TIDAK ADA${R}" })"
        Write-Host "  ${GRY}Groq key:${R}       $(if ($GQK) { "${GRN}ada${R}" } else { "${RED}TIDAK ADA${R}" })"
        Write-Host ""

        Write-Host "  ${GRY}Groq (llama-3.1-8b)...${R} " -NoNewline
        $r1 = _api_call $GQ $GQK "llama-3.1-8b-instant" $testMsg 5
        if ($r1) { Write-Host "${GRN}OK${R}" } else { Write-Host "${RED}GAGAL${R}  $($script:_lastApiError)" }

        Write-Host "  ${GRY}Groq (llama-3.3-70b)...${R} " -NoNewline
        $r2 = _api_call $GQ $GQK "llama-3.3-70b-versatile" $testMsg 5
        if ($r2) { Write-Host "${GRN}OK${R}" } else { Write-Host "${RED}GAGAL${R}  $($script:_lastApiError)" }

        Write-Host "  ${GRY}OpenRouter (claude-haiku-4-5)...${R} " -NoNewline
        $r3 = _api_call $OR $ORK "anthropic/claude-haiku-4-5" $testMsg 5
        if ($r3) { Write-Host "${GRN}OK${R}" } else { Write-Host "${RED}GAGAL${R}  $($script:_lastApiError)" }

        Write-Host "  ${GRY}OpenRouter (qwen-2.5-72b)...${R} " -NoNewline
        $r4 = _api_call $OR $ORK "qwen/qwen-2.5-72b-instruct" $testMsg 5
        if ($r4) { Write-Host "${GRN}OK${R}" } else { Write-Host "${RED}GAGAL${R}  $($script:_lastApiError)" }

        Write-Host ""
    }
}

function prompt {
    $loc = (Get-Location).Path -replace [regex]::Escape($projectsPath), "~yohn"
    $gb  = git branch --show-current 2>$null
    $branchPart = if ($gb) { " ${PRP}($gb)${R}" } else { "" }
    "${CYN}${B}yohn${R}${GRY}:${R}${WHT}$loc${R}$branchPart ${YEL}❯${R} "
}

# ── Natural language fallback → YohnAI ───────────────────────────────────────
# Kalau command tidak dikenal, rekonstruksi kalimat penuh dan kirim ke YohnAI
$ExecutionContext.InvokeCommand.CommandNotFoundAction = {
    param($cmdName, $eventArgs)
    $captured = $cmdName
    $eventArgs.CommandScriptBlock = {
        param([Parameter(ValueFromRemainingArguments=$true)][string[]]$rest)
        $full = (@($captured) + @($rest) | Where-Object { $_ }) -join " "
        _yohnai_send $full
    }.GetNewClosure()
    $eventArgs.StopSearch = $true
}
