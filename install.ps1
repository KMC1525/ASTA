# ASTA — instalador/atualizador para Windows (PowerShell 5.1+).
#
#   irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex
#
# O MESMO comando instala e atualiza. Seus dados (%USERPROFILE%\.asta) nunca são tocados.
# Variáveis opcionais: $env:ASTA_EXTRAS = "all" (padrão: instala/atualiza TODAS as bibliotecas do ASTA) | "none" (só o ASTA)
#                                         | lista: "docs,media,local". Uma biblioteca que falhe não aborta a instalação.
#                      $env:ASTA_MODELS = (vazio: PERGUNTA no terminal, sim/não, antes de baixar os modelos locais pré-instalados: Qwen3.8 2B Distill Q8_0 (texto)
#                                         e Z-Image Q4_K_M (imagem)) | "all" | "text" | "image" (baixam sem perguntar) | "none" (pula)
#                      $env:ASTA_PYTHON = "auto" (padrão: instala o Python se faltar e o atualiza pelo winget, com pip/setuptools/wheel)
#                                         | "keep" (nunca mexe no Python do sistema)
#                      $env:ASTA_STEP = "python" → só instala/atualiza o Python e as ferramentas dele.
#                      $env:ASTA_SOURCE = <url|pasta>   (padrão: GitHub, branch main)
#                      $env:ASTA_FORCE = "1" → reinstala o ASTA mesmo que a versão instalada já seja a mais recente.
#                      $env:ASTA_RUST = "ask" (padrão: PERGUNTA no terminal antes de instalar o Rust; se ele já existe, atualiza e recompila o núcleo do ASTA)
#                                         | "yes" (instala/atualiza sem perguntar) | "no" (pula). Sem terminal, nunca instala sem permissão.
#                      $env:ASTA_LANG = "pt" | "en" → idioma dos textos (padrão: o idioma do computador).
# O que já está instalado NÃO é instalado de novo: o Python só é atualizado se o winget tiver versão nova, o ambiente (venv) é reaproveitado,
# o ASTA só é baixado se houver versão mais nova, e as bibliotecas/modelos já presentes só são atualizados se precisar.

# 'Continue' de propósito: no Windows PowerShell 5.1, com 'Stop' qualquer texto que um programa externo (python, pip, winget) escreva no stderr
# — até com 2>$null — vira uma exceção (NativeCommandError). Os erros que importam são checados por $LASTEXITCODE e por -ErrorAction Stop.
$ErrorActionPreference = 'Continue'
$Source = if ($env:ASTA_SOURCE) { $env:ASTA_SOURCE } else { 'https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip' }
$Extras = $env:ASTA_EXTRAS
$Root   = Join-Path $env:LOCALAPPDATA 'ASTA'
$AppDir = Join-Path $Root 'app'
$BinDir = Join-Path $Root 'bin'

# Idioma dos textos = idioma do computador (pt ou en). $env:ASTA_LANG = "pt" | "en" força. O `asta` chamado daqui lê a mesma variável.
$AstaLang = 'en'
try {
  $forced = "$($env:ASTA_LANG)".ToLower()
  if ($forced) { $AstaLang = if ($forced -like 'pt*') { 'pt' } else { 'en' } }
  else { $AstaLang = if ((Get-UICulture).Name -like 'pt*') { 'pt' } else { 'en' } }
} catch { }
$env:ASTA_LANG = $AstaLang
function L($pt, $en) { if ($AstaLang -eq 'pt') { return $pt } else { return $en } }

function Say($m)  { Write-Host $m -ForegroundColor White }
function Note($m) { Write-Host "  $m" }
function Die($m)  { Write-Host "✗ $m" -ForegroundColor Red; throw $m }

Say (L 'ASTA — instalação/atualização' 'ASTA — install/update')

# 1) Python 3.9+ — instala se faltar e atualiza (o winget também atualiza o pip que vem com ele). $env:ASTA_PYTHON = "keep": nunca mexe no Python do sistema.
$PyMode = if ($env:ASTA_PYTHON) { $env:ASTA_PYTHON } else { 'auto' }
function Find-Python {
  foreach ($cand in @(@('py', '-3'), @('python'), @('python3'))) {
    try {
      $exe = $cand[0]; $args0 = @($cand | Select-Object -Skip 1)
      & $exe @args0 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { return (@($exe) + $args0) }
    } catch { }
  }
  return $null
}
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') }
function Winget-Python($mode) {
  # winget (vem com o Windows 10/11): "install" instala o Python 3.12; "upgrade" atualiza as versões do Python instaladas por ele
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
  $flags = @('--exact', '--silent', '--accept-package-agreements', '--accept-source-agreements')
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    if ($mode -eq 'install') { & winget install --id Python.Python.3.12 @flags | Out-Null; return ($LASTEXITCODE -eq 0) }
    foreach ($id in @('Python.Python.3.13', 'Python.Python.3.12', 'Python.Python.3.11', 'Python.Python.3.10', 'Python.Python.3.9')) {
      & winget list --id $id --exact 2>$null | Out-Null
      if ($LASTEXITCODE -eq 0) { & winget upgrade --id $id @flags | Out-Null }
    }
    return $true
  } finally { $ErrorActionPreference = $prev }
}
$py = Find-Python
if ($py) {
  if ($PyMode -ne 'keep') {
    $pyBefore = "$(& $py[0] @($py | Select-Object -Skip 1) --version)"
    Note (L "Python já instalado ($pyBefore) — verificando se há versão mais nova …" "Python already installed ($pyBefore) — checking for a newer version …")
    if (Winget-Python 'upgrade') {
      Refresh-Path; $py = Find-Python
      $pyAfter = "$(& $py[0] @($py | Select-Object -Skip 1) --version)"
      if ($pyAfter -ne $pyBefore) { Note (L "Python atualizado: $pyBefore → $pyAfter" "Python updated: $pyBefore → $pyAfter") } else { Note (L 'Python já está na versão mais recente disponível.' 'Python is already at the latest available version.') }
    } else { Note (L 'Não foi possível atualizar o Python automaticamente (sem o winget); seguindo com o atual.' 'Could not update Python automatically (no winget); continuing with the current one.') }
  }
} else {
  if ($PyMode -eq 'keep') { Die (L 'Python 3.9 ou superior não encontrado. Instale com:  winget install Python.Python.3.12   (ou https://www.python.org/downloads/) e rode este comando de novo.' 'Python 3.9 or newer not found. Install with:  winget install Python.Python.3.12   (or https://www.python.org/downloads/) and run this command again.') }
  Note (L 'Python 3.9+ não encontrado — instalando com o winget …' 'Python 3.9+ not found — installing with winget …')
  [void](Winget-Python 'install'); Refresh-Path; $py = Find-Python
  if (-not $py) { Die (L 'Não consegui instalar o Python 3.9+ automaticamente. Instale com:  winget install Python.Python.3.12   (ou https://www.python.org/downloads/) e rode este comando de novo.' 'Could not install Python 3.9+ automatically. Install with:  winget install Python.Python.3.12   (or https://www.python.org/downloads/) and run this command again.') }
}
Note ("Python: " + (& $py[0] @($py | Select-Object -Skip 1) --version))

# 2) ambiente isolado. Se o Python foi atualizado para uma versão mais nova, o ambiente é recriado.
New-Item -ItemType Directory -Force -ErrorAction Stop -Path $AppDir, $BinDir | Out-Null
$venv = Join-Path $AppDir 'venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
$pyV = (& $py[0] @($py | Select-Object -Skip 1) -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if (Test-Path $venv) {
  $vv = $null
  try { $vv = (& $venvPy -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null) } catch { }
  $vv = if ($vv) { "$vv".Trim() } else { '' }
  if ((-not $vv) -or ([version]$vv -lt [version]$pyV)) {
    Note (L "Recriando o ambiente para o Python $pyV (antes: $(if ($vv) { $vv } else { 'quebrado' })) — as bibliotecas serão reinstaladas …" "Recreating the environment for Python $pyV (before: $(if ($vv) { $vv } else { 'broken' })) — the libraries will be reinstalled …")
    Remove-Item -Recurse -Force -ErrorAction Stop $venv
  }
}
if (Test-Path $venvPy) { Note (L "Ambiente já existe ($venv) — reaproveitando." "Environment already exists ($venv) — reusing it.") }
else {
  Note (L "Criando ambiente em $venv …" "Creating environment in $venv …")
  & $py[0] @($py | Select-Object -Skip 1) -m venv $venv
  if ($LASTEXITCODE -ne 0) { Die (L 'Não foi possível criar o ambiente virtual.' 'Could not create the virtual environment.') }
}
# ferramentas do Python (pip, setuptools, wheel) sempre na versão mais recente
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $venvPy -m pip install --upgrade --quiet --disable-pip-version-check pip setuptools wheel 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Note (L '⚠ Não foi possível atualizar o pip/setuptools/wheel agora (sem internet?); seguindo.' '⚠ Could not update pip/setuptools/wheel right now (no internet?); continuing.') }
$ErrorActionPreference = $prevEap
if ($env:ASTA_STEP -eq 'python') { Say (L "✓ Python $pyV e ferramentas (pip, setuptools, wheel) prontos." "✓ Python $pyV and tools (pip, setuptools, wheel) ready."); return }

# 3) instala / atualiza
$spec = 'asta'
if ($Source -match '://') { $req = "$spec @ $Source" }
elseif (Test-Path $Source) { $req = "$spec @ " + ([System.Uri](Resolve-Path -ErrorAction Stop $Source).Path).AbsoluteUri }
else { $req = $Source }
$old = & $venvPy -I -c "import asta; print(asta.__version__)" 2>$null   # ASTA ainda não instalado: o Python escreve um erro no stderr, que é descartado
if ($LASTEXITCODE -ne 0) { $old = $null }
# Só baixa o ASTA se ele não está instalado ou se há uma versão mais nova. Com a origem padrão (ou ASTA_VERSION_URL) a versão publicada é
# consultada; com outra origem (ASTA_SOURCE) não há como saber, então instala. ASTA_FORCE=1 sempre reinstala.
$skipAsta = $false
$force = $env:ASTA_FORCE -and ($env:ASTA_FORCE -ne '0')
if ($old -and (Test-Path (Join-Path $venv 'Scripts\asta.exe')) -and (-not $force) -and ((-not $env:ASTA_SOURCE) -or $env:ASTA_VERSION_URL)) {
  $verUrl = if ($env:ASTA_VERSION_URL) { $env:ASTA_VERSION_URL } else { 'https://raw.githubusercontent.com/KMC1525/ASTA/main/asta/__init__.py' }
  $remote = $null
  try {
    $txt = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 -Uri $verUrl -ErrorAction Stop).Content
    if ($txt -is [byte[]]) { $txt = [System.Text.Encoding]::UTF8.GetString($txt) }
    if ($txt -match "__version__\s*=\s*[`"']([0-9][0-9.]*)") { $remote = $Matches[1] }
  } catch { }
  try { if ($remote -and ([version]$remote -le [version]("$old".Trim()))) { $skipAsta = $true } } catch { }
}
if ($skipAsta) { Note (L "ASTA $old já instalado e na versão mais recente — nada a baixar." "ASTA $old already installed and up to date — nothing to download.") }
else {
  Note (L 'Baixando e instalando ASTA …' 'Downloading and installing ASTA …')
  & $venvPy -m pip install --upgrade --disable-pip-version-check --quiet --no-cache-dir $req
  if ($LASTEXITCODE -ne 0) { Die (L 'Falha ao instalar. Verifique sua conexão e tente de novo.' 'Installation failed. Check your connection and try again.') }
}
$new = & $venvPy -I -c "import asta; print(asta.__version__)"

# 4) comando `asta`
$shim = Join-Path $BinDir 'asta.cmd'
Set-Content -ErrorAction Stop -Path $shim -Value "@echo off`r`n`"$venv\Scripts\asta.exe`" %*" -Encoding ASCII

# 4b) o comando `asta` no PATH — do usuário (para novos terminais) e deste terminal (para usar já). Feito ANTES das bibliotecas, que demoram.
$asta = Join-Path $venv 'Scripts\asta.exe'
function Same-Dir($a, $b) { return ($a.TrimEnd('\') -ieq $b.TrimEnd('\')) }
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$userParts = @(if ($userPath) { $userPath -split ';' | Where-Object { $_ } })   # o Path do usuário pode ser vazio (null) numa conta nova
if (-not ($userParts | Where-Object { Same-Dir $_ $BinDir })) {
  [Environment]::SetEnvironmentVariable('Path', (($userParts + $BinDir) -join ';'), 'User')
  Note (L 'Adicionei o comando ao seu PATH.' 'I added the command to your PATH.')
}
if (-not (($env:Path -split ';') | Where-Object { $_ -and (Same-Dir $_ $BinDir) })) { $env:Path = $env:Path.TrimEnd(';') + ';' + $BinDir }   # vale já neste terminal (com `irm | iex`)

# 5) bibliotecas do ASTA (todas, a menos que ASTA_EXTRAS diga outra coisa); a lista vem da versão recém-instalada
$libsFailed = $false
if ($Extras -in @('none', 'core')) { Note (L "Bibliotecas opcionais: puladas (ASTA_EXTRAS=$Extras)." "Optional libraries: skipped (ASTA_EXTRAS=$Extras).") }
else {
  Say (L 'Bibliotecas do ASTA: instalo o que falta e atualizo o que tiver versão mais nova (a primeira vez pode demorar e baixar vários GB) …' 'ASTA libraries: installing what is missing and updating what has a newer version (the first time can take long and download several GB) …')
  $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'   # avisos do pip no stderr não podem abortar o instalador
  & $asta libs
  if ($LASTEXITCODE -ne 0) { $libsFailed = $true }
  $ErrorActionPreference = $prevEap
}

# 6) modelos locais pré-instalados (texto e imagem). Sem $env:ASTA_MODELS, o ASTA PERGUNTA no terminal (sim/não) antes de baixar; o que já está na pasta é pulado
$modelsFailed = $false
if ($env:ASTA_MODELS -in @('none', 'no', '0')) { Note (L "Modelos pré-instalados: pulados (ASTA_MODELS=$($env:ASTA_MODELS))." "Pre-installed models: skipped (ASTA_MODELS=$($env:ASTA_MODELS)).") }
elseif (-not $env:ASTA_MODELS) {
  & $asta models install --ask
  if ($LASTEXITCODE -ne 0) { $modelsFailed = $true }
}
else {
  Say (L 'Modelos locais pré-instalados: baixo só o que ainda não está na pasta (vários GB na primeira vez) …' 'Pre-installed local models: downloading only what is not in the folder yet (several GB the first time) …')
  & $asta models install
  if ($LASTEXITCODE -ne 0) { $modelsFailed = $true }
}
# 7) Rust (opcional, deixa o ASTA mais rápido e leve): instala o Rust se faltar, atualiza se já existir e recompila o núcleo do ASTA.
#    $env:ASTA_RUST = "ask" (padrão: pergunta no terminal; sem terminal só atualiza o que já existe, nunca instala sem permissão) | "yes" | "no".
if (-not $env:ASTA_RUST) { $env:ASTA_RUST = 'ask' }
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $asta native setup
if ($LASTEXITCODE -ne 0) { Note (L 'Rust: não foi possível concluir agora (opcional; o ASTA usa Python). Tente depois:  asta native setup' 'Rust: could not finish right now (optional; ASTA uses Python). Try later:  asta native setup') }
$ErrorActionPreference = $prevEap
if ($modelsFailed) { Note (L '⚠ Alguns modelos pré-instalados não foram baixados (veja acima). O ASTA já funciona; para tentar de novo: asta models install' '⚠ Some pre-installed models were not downloaded (see above). ASTA already works; to try again: asta models install') }

if (-not $old) { Say (L "✓ ASTA $new instalado." "✓ ASTA $new installed.") }
elseif ($old -eq $new) { Say (L "✓ ASTA $new já estava atualizado." "✓ ASTA $new was already up to date.") }
else { Say (L "✓ ASTA atualizado: $old → $new." "✓ ASTA updated: $old → $new.") }
if ($libsFailed) { Note (L '⚠ Algumas bibliotecas opcionais não foram instaladas (veja acima). O ASTA já funciona; para tentar de novo: asta libs' '⚠ Some optional libraries were not installed (see above). ASTA already works; to try again: asta libs') }
Write-Host ''
if (Get-Command asta -ErrorAction SilentlyContinue) { Note (L 'Para abrir a WebUI:   asta' 'To open the WebUI:   asta') }
else {
  Note (L "Para abrir a WebUI:   & '$asta'" "To open the WebUI:   & '$asta'")
  Note (L "O comando 'asta' só será reconhecido em terminais NOVOS (feche e abra o PowerShell) ou, neste, depois de rodar o instalador com:  irm <endereço> | iex" "The 'asta' command will only be recognized in NEW terminals (close and reopen PowerShell) or, in this one, after running the installer with:  irm <address> | iex")
}
Note (L 'Para atualizar:       rode este mesmo comando de novo (ou: asta update) — atualiza o ASTA e as bibliotecas dele' 'To update:            run this same command again (or: asta update) — it updates ASTA, its libraries and (optionally) Rust')
