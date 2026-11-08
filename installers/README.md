# installers/

Tudo o que gera os instaladores do ASTA. O workflow [`release`](../.github/workflows/release.yml) roda isto a cada push na `main` que muda a versão, o núcleo em Rust, os instaladores ou o app Android, e publica a Release `vX.Y.Z`.

| Pasta | Gera | Como |
|---|---|---|
| `windows/` | `ASTA-X-Y-Win.exe` | `build-windows.ps1` monta `stage/` (Python embutido + ASTA + `asta_core.dll`) e o Inno Setup (`asta.iss`) compila o instalador. Instala só para o usuário. |
| `macos/` | `ASTA-X-Y-macOS.pkg` | `build-pkg.sh` monta o `ASTA.app` (lançador + `install.sh` + código do ASTA + núcleo Rust arm64 e x86_64) e o `pkgbuild`/`productbuild` empacota. Na primeira abertura o app instala o ASTA para o usuário num Terminal. |
| `linux/` | `ASTA-X-Y-Linux.appimage` | `build-appimage.sh` usa um Python portátil (python-build-standalone) e a `appimagetool`. Dados e bibliotecas opcionais ficam em `~/.asta`. |
| `../mobile-app/` | `ASTA-X-Y-Android.apk` | Capacitor + Chaquopy (Python no app) + núcleo Rust por ABI; `android-overlay/patch_android.py` prepara o projeto gerado. |
| `release_notes.py` | texto da Release | tabela de downloads + notas do changelog (pt-BR e inglês). |

Nome dos arquivos: versão `0.14.0` → `0-14` (`0.14.1` → `0-14-1`). O núcleo pré-compilado de cada plataforma (`asta-core-<plataforma>.<so|dylib|dll>`) e o `SHA256SUMS.txt` vão na mesma Release: é de lá que `asta native setup` o baixa.

Testar localmente (Linux): `sh installers/linux/build-appimage.sh 0.14.0 /tmp/ASTA.AppImage <python-portatil> asta/native/target/release/libasta_core.so`.
Não assinados (precisam de certificado pago): Windows (SmartScreen) e macOS (Gatekeeper) pedem uma confirmação na primeira vez.
