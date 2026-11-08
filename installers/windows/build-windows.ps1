# ASTA — monta a pasta `stage` e compila o instalador do Windows (Inno Setup).
#   build-windows.ps1 -Version 0.14.0 -Label 0-14 -CoreDll C:\caminho\asta_core.dll [-PythonVersion 3.12.10]
# Resultado: dist-installers\ASTA-<label>-Win.exe
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [Parameter(Mandatory = $true)][string]$Label,
  [Parameter(Mandatory = $true)][string]$CoreDll,
  [string]$PythonVersion = "3.12.10"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$stage = Join-Path $PSScriptRoot "stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

# 1) Python embutido (a distribuição "embeddable" do python.org)
$zip = Join-Path $env:TEMP "python-embed.zip"
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath (Join-Path $stage "python")
$mm = ($PythonVersion.Split(".")[0..1]) -join ""
# o arquivo ._pth manda no caminho do Python embutido: liga o site e o site-packages (onde o ASTA e o pip instalam)
$pth = Join-Path $stage "python\python$mm._pth"
Set-Content -Path $pth -Value @("python$mm.zip", ".", "Lib\site-packages", "import site") -Encoding ASCII

# 2) o ASTA (só a biblioteca padrão do Python: sem dependências) no site-packages do Python embutido
$site = Join-Path $stage "python\Lib\site-packages"
New-Item -ItemType Directory -Path $site -Force | Out-Null
python -m pip install --no-deps --disable-pip-version-check --quiet --target $site $root
if ($LASTEXITCODE -ne 0) { throw "pip install do ASTA falhou" }

# 3) núcleo Rust, lançador e ícone
New-Item -ItemType Directory -Path (Join-Path $stage "native") | Out-Null
Copy-Item $CoreDll (Join-Path $stage "native\asta_core.dll")
Copy-Item (Join-Path $PSScriptRoot "ASTA.cmd") $stage
python -m pip install --quiet pillow
python (Join-Path $PSScriptRoot "make_ico.py") (Join-Path $root "asta\web\icons\icon-512.png") (Join-Path $stage "asta.ico")

# 4) teste rápido do que vai dentro do instalador: o Python embutido importa o ASTA e carrega o núcleo
$env:ASTA_NATIVE_LIB = (Join-Path $stage "native\asta_core.dll")
& (Join-Path $stage "python\python.exe") -c "import asta, asta.native as n; print('ASTA', asta.__version__, '| núcleo Rust ativo:', n.available())"
if ($LASTEXITCODE -ne 0) { throw "o Python embutido não conseguiu importar o ASTA" }

# 5) Inno Setup
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue)
if (-not $iscc) { $iscc = Get-Item "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" }
& $iscc.Source "/DAppVersion=$Version" "/DFileLabel=$Label" (Join-Path $PSScriptRoot "asta.iss")
if ($LASTEXITCODE -ne 0) { throw "o Inno Setup falhou" }
Get-ChildItem (Join-Path $root "dist-installers") | ForEach-Object { Write-Host "pronto:" $_.FullName ("{0:N1} MB" -f ($_.Length / 1MB)) }
