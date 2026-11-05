# ASTA — instalador/atualizador para Windows (PowerShell 5.1+).
#
#   irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex
#
# O MESMO comando instala e atualiza. Seus dados (%USERPROFILE%\.asta) nunca são tocados.
# Variáveis opcionais: $env:ASTA_EXTRAS = "all" (padrão: instala/atualiza TODAS as bibliotecas do ASTA) | "none" (só o ASTA)
#                                         | lista: "docs,media,local". Uma biblioteca que falhe não aborta a instalação.
#                      $env:ASTA_SOURCE = <url|pasta>   (padrão: GitHub, branch main)

$ErrorActionPreference = 'Stop'
$Source = if ($env:ASTA_SOURCE) { $env:ASTA_SOURCE } else { 'https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip' }
$Extras = $env:ASTA_EXTRAS
$Root   = Join-Path $env:LOCALAPPDATA 'ASTA'
$AppDir = Join-Path $Root 'app'
$BinDir = Join-Path $Root 'bin'

function Say($m)  { Write-Host $m -ForegroundColor White }
function Note($m) { Write-Host "  $m" }
function Die($m)  { Write-Host "✗ $m" -ForegroundColor Red; throw $m }

Say 'ASTA — instalação/atualização'

# 1) Python 3.9+
$py = $null
foreach ($cand in @(@('py', '-3'), @('python'), @('python3'))) {
  try {
    $exe = $cand[0]; $args0 = @($cand | Select-Object -Skip 1)
    $ok = & $exe @args0 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = @($exe) + $args0; break }
  } catch { }
}
if (-not $py) { Die 'Python 3.9 ou superior não encontrado. Instale com:  winget install Python.Python.3.12   (ou https://www.python.org/downloads/) e rode este comando de novo.' }
Note ("Python: " + (& $py[0] @($py | Select-Object -Skip 1) --version))

# 2) ambiente isolado
New-Item -ItemType Directory -Force -Path $AppDir, $BinDir | Out-Null
$venv = Join-Path $AppDir 'venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
  Note "Criando ambiente em $venv …"
  & $py[0] @($py | Select-Object -Skip 1) -m venv $venv
  if ($LASTEXITCODE -ne 0) { Die 'Não foi possível criar o ambiente virtual.' }
}

# 3) instala / atualiza
$spec = 'asta'
if ($Source -match '://') { $req = "$spec @ $Source" }
elseif (Test-Path $Source) { $req = "$spec @ " + ([System.Uri](Resolve-Path $Source).Path).AbsoluteUri }
else { $req = $Source }
$old = & $venvPy -I -c "import asta; print(asta.__version__)" 2>$null
Note 'Baixando e instalando ASTA …'
& $venvPy -m pip install --upgrade --disable-pip-version-check --quiet --no-cache-dir $req
if ($LASTEXITCODE -ne 0) { Die 'Falha ao instalar. Verifique sua conexão e tente de novo.' }
$new = & $venvPy -I -c "import asta; print(asta.__version__)"

# 4) comando `asta`
$shim = Join-Path $BinDir 'asta.cmd'
Set-Content -Path $shim -Value "@echo off`r`n`"$venv\Scripts\asta.exe`" %*" -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
# 5) bibliotecas do ASTA (todas, a menos que ASTA_EXTRAS diga outra coisa); a lista vem da versão recém-instalada
$asta = Join-Path $venv 'Scripts\asta.exe'
$libsFailed = $false
if ($Extras -in @('none', 'core')) { Note "Bibliotecas opcionais: puladas (ASTA_EXTRAS=$Extras)." }
else {
  Say 'Instalando/atualizando as bibliotecas do ASTA (a primeira vez pode demorar e baixar vários GB) …'
  $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'   # avisos do pip no stderr não podem abortar o instalador
  & $asta libs
  if ($LASTEXITCODE -ne 0) { $libsFailed = $true }
  $ErrorActionPreference = $prevEap
}
if (($userPath -split ';') -notcontains $BinDir) {
  [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $BinDir), 'User')
  Note 'Adicionei o comando ao seu PATH — abra um NOVO terminal para usá-lo.'
}

if (-not $old) { Say "✓ ASTA $new instalado." }
elseif ($old -eq $new) { Say "✓ ASTA $new já estava atualizado (arquivos reinstalados)." }
else { Say "✓ ASTA atualizado: $old → $new." }
if ($libsFailed) { Note '⚠ Algumas bibliotecas opcionais não foram instaladas (veja acima). O ASTA já funciona; para tentar de novo: asta libs' }
Write-Host ''
Note 'Para abrir a WebUI:   asta'
Note 'Para atualizar:       rode este mesmo comando de novo (ou: asta update) — atualiza o ASTA e as bibliotecas dele'
