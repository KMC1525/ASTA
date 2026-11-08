#!/usr/bin/env python3
"""Texto da Release do GitHub: tabela de downloads + as notas da versão tiradas do CHANGELOG (pt-BR e inglês).

Uso:  release_notes.py <versão> <rótulo-dos-arquivos>     (ex.: release_notes.py 0.14.0 0-14)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(path: Path, version: str) -> str:
    """O trecho «## [versão] …» do changelog (até o próximo «## [»)."""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)" % re.escape(version), text, re.S | re.M)
    return m.group(1).strip() if m else ""


def main(argv: list) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    version, label = argv[1], argv[2]
    pt = section(ROOT / "CHANGELOG.md", version)
    en = section(ROOT / "CHANGELOG.en.md", version)
    out = [
        f"# ASTA {version}",
        "",
        "| Plataforma / Platform | Arquivo / File | Como usar / How to use |",
        "|---|---|---|",
        f"| Windows 10/11 (64-bit) | `ASTA-{label}-Win.exe` | Execute o instalador (sem administrador) · Run the installer (no admin needed) |",
        f"| macOS 11+ (Apple Silicon e Intel) | `ASTA-{label}-macOS.pkg` | Clique com o botão direito → Abrir (não assinado) · Right-click → Open (unsigned) |",
        f"| Linux x86_64 | `ASTA-{label}-Linux.appimage` | `chmod +x ASTA-{label}-Linux.appimage && ./ASTA-{label}-Linux.appimage` |",
        f"| Linux ARM64 | `ASTA-{label}-Linux-arm64.appimage` | idem · same |",
        f"| Android 7+ | `ASTA-{label}-Android.apk` | Permita instalar apps desconhecidos uma vez · Allow unknown apps once. **O ASTA roda dentro do aparelho, sem computador · ASTA runs on the device, no computer needed.** |",
        "",
        "Terminal (Linux/macOS): `curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh` · Windows: veja o README / see the README.",
        "",
        "`asta-core-*` e `SHA256SUMS.txt` são o núcleo em Rust pré-compilado de cada plataforma (usado pelo instalador do terminal e por `asta native setup`; conferido por SHA-256). / "
        "`asta-core-*` and `SHA256SUMS.txt` are the pre-built Rust core for each platform (used by the terminal installer and `asta native setup`; verified by SHA-256).",
        "",
    ]
    if pt:
        out += ["## Novidades", "", pt, ""]
    if en:
        out += ["## What's new", "", en, ""]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
