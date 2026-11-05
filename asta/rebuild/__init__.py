"""Rebuild: reconstrói jogos que você já tem — Ren'Py e RPG Maker (2000 → MZ) — como jogos 2D do ASTA em HTML, CSS e JavaScript puros.

Lê as pastas/ZIPs dos jogos (scripts e arquivos de dados), reconstrói a estrutura (mapas, eventos, diálogos, escolhas, variáveis, itens, inimigos) nos motores 2D do
ASTA (visual novel e RPG) e empacota. A arte e o áudio originais NÃO são copiados: o jogo reconstruído usa a arte procedural e o áudio sintetizado do ASTA.
Uso pessoal; veja `NOTICE` (aviso mostrado ao final de cada reconstrução).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_READ = 64 * 1024 * 1024          # maior arquivo de dados lido (mapas/scripts são pequenos; mídia nunca é lida)
MAX_FILES = 40000
TEXT_EXT = (".rpy", ".json", ".ini", ".lmu", ".lmt", ".ldb", ".rxdata", ".rvdata", ".rvdata2")

ENGINES = {"renpy": "Ren'Py", "mv": "RPG Maker MV", "mz": "RPG Maker MZ", "ace": "RPG Maker VX Ace", "vx": "RPG Maker VX", "xp": "RPG Maker XP", "rm2k": "RPG Maker 2000/2003"}

NOTICE_PT = {
    "title": "Aviso legal sobre a reconstrução",
    "intro": "Você reconstruiu um jogo existente. Leia antes de continuar:",
    "points": [
        "Não publique este jogo na Steam, itch.io, lojas de aplicativos ou qualquer outra plataforma.",
        "Uso somente pessoal.",
        "Qualquer problema legal é de responsabilidade de quem gerou a reconstrução — não do criador do ASTA nem dos contribuidores.",
        "Mesmo com este aviso, o ASTA não impede a reconstrução, mas tenha consciência das suas ações.",
    ],
    "scope": "A reconstrução refaz a estrutura do jogo (mapas, eventos, diálogos, escolhas, variáveis, itens e inimigos) em HTML, CSS e JavaScript puros; a arte e o áudio originais não são copiados.",
}
NOTICE_EN = {
    "title": "Legal notice about the rebuild",
    "intro": "You rebuilt an existing game. Read this before going on:",
    "points": [
        "Do not publish this game on Steam, itch.io, app stores or any other platform.",
        "Personal use only.",
        "Any legal problem is the responsibility of whoever generated the rebuild — not of ASTA's creator nor its contributors.",
        "Even with this notice, ASTA does not stop you from rebuilding, but be aware of your actions.",
    ],
    "scope": "The rebuild recreates the game's structure (maps, events, dialogue, choices, variables, items and enemies) in plain HTML, CSS and JavaScript; the original art and audio are not copied.",
}


def notice(lang: str = "pt") -> Dict[str, Any]:
    return NOTICE_PT if str(lang).lower().startswith("pt") else NOTICE_EN


def notice_markdown(lang: str = "pt") -> str:
    n = notice(lang)
    return f"## ⚠ {n['title']}\n\n{n['intro']}\n\n" + "\n".join(f"- {p}" for p in n["points"]) + f"\n\n_{n['scope']}_\n"


class SourceError(ValueError):
    pass


class Source:
    """Árvore virtual de arquivos de um jogo: um ZIP (ou vários arquivos soltos). Só os arquivos de dados são lidos; imagens e áudio nunca."""

    def __init__(self) -> None:
        self._files: Dict[str, Callable[[], bytes]] = {}
        self._low: Dict[str, str] = {}

    def add(self, name: str, reader: Callable[[], bytes]) -> None:
        name = name.replace("\\", "/").lstrip("/")
        if not name or ".." in name.split("/") or len(self._files) >= MAX_FILES:
            return
        self._files[name] = reader
        self._low[name.lower()] = name

    @classmethod
    def from_uploads(cls, metas: List[Dict[str, Any]]) -> "Source":
        src = cls()
        for meta in metas:
            path = Path(meta["path"])
            if zipfile.is_zipfile(path):
                zf = zipfile.ZipFile(path)
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(TEXT_EXT) or info.file_size > MAX_READ:
                        continue
                    src.add(info.filename, lambda zf=zf, n=info.filename: zf.read(n))
            elif str(meta.get("name", "")).lower().endswith(TEXT_EXT):
                src.add(meta["name"], lambda p=path: p.read_bytes()[:MAX_READ])
        return src

    @classmethod
    def from_dir(cls, root: Path) -> "Source":
        src = cls()
        for p in Path(root).rglob("*"):
            if p.is_file() and p.name.lower().endswith(TEXT_EXT) and p.stat().st_size <= MAX_READ:
                src.add(p.relative_to(root).as_posix(), lambda p=p: p.read_bytes())
        return src

    def names(self) -> List[str]:
        return list(self._files)

    def find(self, tail: str) -> Optional[str]:
        """Arquivo cujo caminho termina em `tail` (sem diferenciar maiúsculas; a pasta raiz do jogo pode ter qualquer nome)."""
        t = tail.lower()
        for low, name in self._low.items():
            if low == t or low.endswith("/" + t):
                return name
        return None

    def find_all(self, pattern: str) -> List[str]:
        rx = re.compile(pattern, re.I)
        return sorted(n for n in self._files if rx.search(n))

    def read(self, name: str) -> bytes:
        return self._files[name]()

    def text(self, name: str) -> str:
        b = self.read(name)
        for enc in ("utf-8-sig", "cp932", "cp1252"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
        return b.decode("latin-1")


def detect(src: Source) -> str:
    """'renpy' | 'mv' | 'mz' | 'ace' | 'vx' | 'xp' | 'rm2k'; levanta SourceError explicando o que falta."""
    sysj = src.find("data/system.json")
    if sysj and src.find_all(r"data/map\d+\.json$"):
        try:
            import json

            d = json.loads(src.text(sysj))
            return "mz" if ("advanced" in d or "tileSize" in d) else "mv"
        except ValueError:
            return "mv"
    for ext, eng in (("rvdata2", "ace"), ("rvdata", "vx"), ("rxdata", "xp")):
        if src.find_all(rf"data/map\d+\.{ext}$"):
            return eng
    if src.find_all(r"map\d{4}\.lmu$"):
        return "rm2k"
    if src.find_all(r"\.rpy$"):
        return "renpy"
    raise SourceError("Não reconheci o jogo. Envie um ZIP com a pasta do jogo (ou a pasta «game» do Ren'Py com os scripts .rpy, ou a pasta «data» do RPG Maker). "
                      "Arquivos compilados do Ren'Py (.rpyc/.rpa) e pacotes criptografados do RPG Maker (.rgssad/.rgss3a) não são lidos — extraia-os antes, se o jogo é seu.")


def rebuild_source(src: Source, title_hint: str = "") -> Tuple[Dict[str, Any], str, List[str], Dict[str, Any]]:
    """Fonte → (dicionário bruto do jogo, gênero, avisos, informações {engine, title, …}). Levanta SourceError se não der."""
    from ..games2d import schema as S  # noqa: F401
    from . import renpy as rp
    from .rpgconv import build_rpg
    from .rpgload import load_lcf, load_mvmz, load_rgss

    eng = detect(src)
    info: Dict[str, Any] = {"engine": eng, "engine_name": ENGINES[eng]}
    if eng == "renpy":
        files = [(n, src.text(n)) for n in src.find_all(r"\.rpy$")]
        raw, warns, extra = rp.convert(files)
        info.update(extra)
        raw["title"] = raw.get("title") or title_hint
        return raw, "visual_novel", warns, {**info, "title": raw["title"]}
    p = load_mvmz(src) if eng in ("mv", "mz") else load_lcf(src) if eng == "rm2k" else load_rgss(src, {"ace": "rvdata2", "vx": "rvdata", "xp": "rxdata"}[eng])
    if not p.get("maps"):
        raise SourceError("Não consegui ler nenhum mapa do jogo (arquivo corrompido, criptografado ou de outra versão).")
    raw, warns = build_rpg(p)
    raw["title"] = p.get("title") or title_hint
    raw["language"] = "pt-BR" if re.search(r"[ãõçáéíóú]|\b(você|não|para)\b", " ".join(str(m.get("name")) for m in p["maps"].values()).lower()) else "en"
    info.update({"title": raw["title"], "maps": len(p["maps"])})
    return raw, "rpg", warns, info
