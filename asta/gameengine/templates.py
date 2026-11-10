"""Gerador de jogos **sem IA** (regras): do pedido (e do tipo/gênero/tema escolhidos) a um jogo completo e jogável — cenas, mapa, diálogos, sprites, sons, trilha e documento de design.

É o fallback de todo o fluxo da aba Main: sem modelo configurado, com resposta inválida ou sem internet o ASTA ainda entrega um jogo de verdade (e a IA, quando existe,
só refina os mesmos dados). Determinístico por `seed`."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from . import art, audio, maps, schema as S

KIND_WORDS = (("vr", ("realidade virtual", " vr ", "vr,", "oculus", "quest", "headset", "meta quest")), ("ar", ("realidade aumentada", " ar ", "augmented", "hololens")),
              ("2.5d", ("2.5d", "2,5d", "isometric", "isom", "meio 3d", "pseudo 3d", "profundidade")), ("3d", ("3d", "tridimensional", "primeira pessoa", "terceira pessoa", "first person", "third person", "fps", "mundo aberto", "open world")),
              ("2d", ("2d", "pixel", "retro", "plataforma", "platform", "side scroll", "vista de cima", "top down", "topdown")))
GENRE_WORDS = (("shooter", ("nave", "shoot", "atirar", "tiro", "space invader", "side scroller", "shmup", "espaço sideral", "naves")), ("fps", ("primeira pessoa", "first person", "fps")),
               ("platformer", ("plataforma", "platform", "pular", "pulo", "mario", "sonic", "side-scroll", "corrida lateral")), ("topdown", ("vista de cima", "top down", "topdown", "rpg", "zelda", "aventura", "labirinto", "maze", "explorar", "dungeon", "masmorra")),
               ("iso", ("isometric", "isom", "tactics", "diablo")), ("vr_room", ("sala", "room", "arremess", "throw", "jogar objetos")), ("ar_hunt", ("caça", "cacar", "hunt", "pokemon", "coletar ao redor")), ("ar_place", ("colocar", "place", "decorar", "mobília", "mobilia")))
THEME_WORDS = (("night", ("noite", "night", "escuro", "dark", "lua", "moon")), ("snow", ("neve", "snow", "gelo", "ice", "inverno", "winter", "frio")), ("desert", ("deserto", "desert", "areia", "sand", "egito", "egypt", "piramide")),
               ("cave", ("caverna", "cave", "mina", "mine", "masmorra", "dungeon", "subterr")), ("city", ("cidade", "city", "urbano", "urban", "cyber", "neon", "rua", "street")), ("space", ("espaço", "espaco", "space", "galax", "planeta", "planet", "alien", "estrela", "star")),
               ("sea", ("mar ", "oceano", "ocean", "sea ", "praia", "beach", "ilha", "island", "pirata", "pirate", "navio")), ("candy", ("doce", "candy", "bolo", "cake", "açúcar", "acucar", "fofo", "cute")), ("lava", ("lava", "vulc", "volcan", "inferno", "fogo", "fire")),
               ("retro", ("retro", "retrô", "arcade", "8-bit", "8 bit", "pixel")), ("sunset", ("pôr do sol", "por do sol", "sunset", "entardecer", "crepúsculo")), ("forest", ("floresta", "forest", "bosque", "selva", "jungle", "natureza", "verde", "campo")))

TR = {
    "pt": {"score": "Pontos: {score}", "coins": "Moedas: {coins}/{total}", "level": "Fase {level}", "hint_move": "Setas/WASD movem · Espaço pula · E fala", "hint_move3d": "WASD move · mouse olha · Espaço pula · E fala",
           "place": "Toque no chão para colocar", "place_hint": "Aponte para o chão e toque para colocar objetos", "vr_hint": "Teletransporte: aponte e aperte o gatilho · pegar: botão lateral", "guia": "Guia"},
    "en": {"score": "Score: {score}", "coins": "Coins: {coins}/{total}", "level": "Level {level}", "hint_move": "Arrows/WASD move · Space jumps · E talks", "hint_move3d": "WASD moves · mouse looks · Space jumps · E talks",
           "place": "Tap the ground to place", "place_hint": "Point at the ground and tap to place objects", "vr_hint": "Teleport: point and press the trigger · grab: side button", "guia": "Guide"},
}
THEME_NAMES = {"pt": {"forest": "da Floresta", "desert": "do Deserto", "snow": "da Neve", "night": "da Noite", "cave": "da Caverna", "city": "da Cidade", "space": "do Espaço", "sea": "do Mar", "candy": "dos Doces", "lava": "da Lava", "retro": "Retrô", "sunset": "do Entardecer"},
               "en": {"forest": "of the Forest", "desert": "of the Desert", "snow": "of the Snow", "night": "of the Night", "cave": "of the Cave", "city": "of the City", "space": "of Space", "sea": "of the Sea", "candy": "of Candy", "lava": "of Lava", "retro": "Retro", "sunset": "of Sunset"}}
KIND_TITLE = {"pt": {"platformer": "Corrida", "topdown": "Aventura", "shooter": "Ataque", "iso": "Expedição", "explore": "Exploração", "fps": "Caçada", "vr_explore": "Travessia", "vr_room": "Sala", "ar_place": "Jardim", "ar_hunt": "Caça"},
              "en": {"platformer": "Run", "topdown": "Adventure", "shooter": "Strike", "iso": "Expedition", "explore": "Exploration", "fps": "Hunt", "vr_explore": "Crossing", "vr_room": "Room", "ar_place": "Garden", "ar_hunt": "Hunt"}}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def _has(p: str, words: Tuple[str, ...]) -> bool:
    return any(_norm(w) in p for w in words)


def detect_lang(prompt: str, default: str = "pt") -> str:
    p = " " + _norm(prompt) + " "
    en = sum(1 for w in (" the ", " and ", " with ", " game ", " player ", " you ", " a ", " of ", " to ", " in ", " enemies ", " collect ") if w in p)
    pt = sum(1 for w in (" o ", " a ", " e ", " com ", " jogo ", " jogador ", " um ", " uma ", " de ", " para ", " inimigos ", " coletar ", " que ", " em ") if w in p)
    return "en" if en > pt + 1 else ("pt" if pt else default)


def detect(prompt: str, kind: str = "", genre: str = "", theme: str = "") -> Tuple[str, str, str]:
    """(tipo, gênero, tema) a partir do pedido; o que o usuário escolheu na tela vence."""
    p = " " + _norm(prompt).replace(",", " ,") + " "
    if kind not in S.KINDS:
        kind = ""
        for k, words in KIND_WORDS:
            if _has(p, words):
                kind = k
                break
        kind = kind or "2d"
    if genre not in S.GENRES or kind not in S.GENRES[genre]["kinds"]:
        genre = ""
        for g, words in GENRE_WORDS:
            if kind in S.GENRES[g]["kinds"] and _has(p, words):
                genre = g
                break
        genre = genre or S.DEFAULT_GENRE[kind]
    if theme not in S.THEMES:
        theme = ""
        for t, words in THEME_WORDS:
            if _has(p, words):
                theme = t
                break
        theme = theme or ("space" if genre == "shooter" else "forest")
    return kind, genre, theme


def make_title(prompt: str, genre: str, theme: str, lang: str) -> str:
    m = re.search(r"[\"“”']([^\"“”']{3,50})[\"“”']", prompt or "")
    if m:
        return m.group(1).strip()
    return f"{KIND_TITLE[lang].get(genre, 'Jogo')} {THEME_NAMES[lang].get(theme, '')}".strip()


def seed_of(prompt: str, extra: str = "") -> int:
    return int(hashlib.sha1((prompt + extra).encode("utf-8")).hexdigest()[:8], 16) % (2 ** 31)


# ============================================================================ blocos de cena
def _hud(lang: str, genre: str, total_hint: bool = True) -> List[Dict[str, Any]]:
    tr = TR[lang]
    nodes = [{"type": "UILabel", "name": "Placar", "text": tr["score"] + "   " + (tr["coins"] if total_hint else ""), "anchor": "top-left", "size": 18, "color": "#ffffff"},
             {"type": "UIBar", "name": "Vida", "bind": "hp", "anchor": "top-right", "w": 120, "color": "#ff4d6d"},
             {"type": "UILabel", "name": "Fase", "text": tr["level"], "anchor": "top-center", "size": 16, "color": "#ffffffcc"[:7]}]
    return nodes


def _parallax(theme: str, deep: bool = False) -> List[Dict[str, Any]]:
    c = S.THEME_COLORS[theme]
    styles = {"night": ["stars", "mountains", "hills"], "space": ["stars", "stars", "hills"], "city": ["city", "city"], "cave": ["mountains", "hills"], "desert": ["clouds", "mountains", "hills"], "snow": ["clouds", "mountains", "hills"],
              "sea": ["clouds", "hills"], "candy": ["clouds", "hills", "hills"], "lava": ["mountains", "mountains", "hills"], "retro": ["stars", "city"], "sunset": ["clouds", "mountains", "hills"], "forest": ["clouds", "mountains", "trees"]}.get(theme, ["clouds", "hills"])
    out = []
    n = len(styles)
    for i, st in enumerate(styles):
        k = i / max(1, n - 1)
        base = c["ground"] if st in ("hills", "trees") else c["stone"]
        col = art._shade(base, -0.35 + 0.3 * (1 - k)) if st not in ("stars", "clouds") else ("#ffffff" if st == "stars" else art._shade(c["bottom"], 0.35))
        node = {"type": "Parallax2D", "name": f"Fundo {i + 1}", "style": st, "color": col, "color2": art._shade(col, 0.25), "factor": round(0.08 + 0.22 * i, 2), "y": round(0.62 + 0.1 * i, 2), "h": round(0.3 - 0.05 * i, 2), "seed": i * 17, "opacity": 0.95 if st != "clouds" else 0.7}
        if st == "stars":
            node.update({"y": 0, "h": 1, "factor": 0.05})
        out.append(node)
    if deep:   # 2.5D com profundidade: mais uma camada de árvores/colinas bem perto
        out.append({"type": "Parallax2D", "name": "Primeiro plano", "style": "trees", "color": art._shade(c["ground"], -0.55), "factor": 0.7, "y": 0.95, "h": 0.3, "seed": 99, "opacity": 0.9})
    return out


def _settings2d(theme: str, genre: str, kind: str) -> Dict[str, Any]:
    c = S.THEME_COLORS[theme]
    s: Dict[str, Any] = {"sky_top": c["top"], "sky_bottom": c["bottom"], "view_h": 540, "genre": genre}
    if genre in ("platformer",):
        s["gravity"] = 1500
    if genre == "shooter":
        s["autoscroll"] = 55
        s["view_h"] = 520
    if genre == "iso":
        s.update({"projection": "iso", "view_h": 480})
    if genre == "topdown":
        s["ysort"] = True
    return s


def _scene2d(kind: str, genre: str, theme: str, lang: str, map_path: str, title: str, name: str = "main", nxt: str = "") -> Dict[str, Any]:
    tr = TR[lang]
    kids: List[Dict[str, Any]] = []
    if genre != "iso":
        kids += _parallax(theme, deep=(kind == "2.5d"))
    kids.append({"type": "TileMap", "name": "Mapa", "map": map_path, "objects": True})
    kids.append({"type": "Camera2D", "name": "Câmera", "follow": "Jogador", "zoom": 1, "smooth": 1.2})
    kids += _hud(lang, genre)
    if genre == "shooter":
        kids.append({"type": "Node2D", "name": "Gerador", "behaviors": [{"type": "spawner", "interval": 1.1, "max": 9}]})
    kids.append({"type": "UILabel", "name": "Dica", "text": tr["hint_move"] if genre != "shooter" else ("Setas/WASD movem · Espaço atira" if lang == "pt" else "Arrows/WASD move · Space shoots"), "anchor": "bottom-center", "size": 13, "color": "#ffffff"})
    rules = {"win": "collect_all" if genre in ("topdown", "iso") else "reach_goal"}
    return {"name": name, "kind": kind, "settings": _settings2d(theme, genre, kind), "rules": rules, "root": {"type": "Node2D", "name": title[:40] or "Main", "children": kids}}


def _lights(theme: str, extent: float = 90) -> List[Dict[str, Any]]:
    night = theme in ("night", "cave", "space")
    return [{"type": "Light3D", "name": "Sol" if not night else "Lua", "kind": "directional", "color": "#cfd8ff" if night else "#fff3d6", "intensity": 0.55 if night else 1.1, "x": 40, "y": 70, "z": 30, "extent": extent},
            {"type": "Light3D", "name": "Ambiente", "kind": "hemisphere", "color": "#6b7bb5" if night else "#cfe8ff", "intensity": 0.55 if night else 0.85}]


def _scene3d(kind: str, genre: str, theme: str, lang: str, map_path: str, title: str) -> Dict[str, Any]:
    tr = TR[lang]
    c = S.THEME_COLORS[theme]
    kids: List[Dict[str, Any]] = [{"type": "Sky3D", "name": "Céu", "top": c["top"], "bottom": c["bottom"], "stars": theme in ("night", "space", "cave"), "fog": 0.3}] + _lights(theme)
    kids.append({"type": "Terrain3D", "name": "Terreno", "map": map_path, "objects": True})
    kids.append({"type": "Camera3D", "name": "Câmera", "mode": "first" if genre in ("fps", "vr_explore") else "third", "fov": 72, "distance": 6.5, "height": 2.2})
    if kind == "vr":
        kids.append({"type": "XRRig", "name": "Plataforma VR", "teleport": True, "hands": True})
    kids += _hud(lang, genre)
    kids.append({"type": "UILabel", "name": "Dica", "text": tr["vr_hint"] if kind == "vr" else tr["hint_move3d"], "anchor": "bottom-center", "size": 13, "color": "#ffffff"})
    return {"name": "main", "kind": kind, "settings": {"camera": "first" if genre in ("fps", "vr_explore") else "third", "shadows": True, "genre": genre, "sky_bottom": c["bottom"], "sky_top": c["top"]}, "rules": {"win": "collect_all"}, "root": {"type": "Node3D", "name": title[:40] or "Main", "children": kids}}


def _scene_vr_room(theme: str, lang: str, title: str) -> Dict[str, Any]:
    tr = TR[lang]
    c = S.THEME_COLORS[theme]
    wall = art._shade(c["stone"], 0.3)
    kids: List[Dict[str, Any]] = [{"type": "Sky3D", "name": "Céu", "top": c["top"], "bottom": c["bottom"], "stars": theme in ("night", "space"), "fog": 0.0}] + _lights(theme, 14)
    kids.append({"type": "Mesh3D", "name": "Piso", "shape": "plane", "w": 14, "d": 14, "color": art._shade(c["ground"], -0.2), "shadow": False, "solid": False})
    for nm, (x, z, w, d) in {"Parede N": (0, -7, 14, 0.4), "Parede S": (0, 7, 14, 0.4), "Parede L": (7, 0, 0.4, 14), "Parede O": (-7, 0, 0.4, 14)}.items():
        kids.append({"type": "Mesh3D", "name": nm, "shape": "box", "w": w, "h": 4, "d": d, "x": x, "y": 2, "z": z, "color": wall, "solid": True})
    kids.append({"type": "Mesh3D", "name": "Mesa", "shape": "box", "w": 2.4, "h": 0.9, "d": 1.1, "x": 0, "y": 0.45, "z": -3, "color": "#8b5e3c", "solid": True})
    cols = ["#ef476f", "#ffd23f", "#06d6a0", "#4cc9f0", "#9d4edd", "#fb8500"]
    for i in range(6):
        shape = "sphere" if i % 2 else "box"
        kids.append({"type": "Mesh3D", "name": f"Objeto {i + 1}", "shape": shape, "w": 0.28, "h": 0.28, "d": 0.28, "x": round(-1.0 + i * 0.4, 2), "y": 1.05, "z": -3, "color": cols[i], "tags": ["grab"], "behaviors": [{"type": "grab"}]})
    for i in range(5):
        a = i / 5 * 6.283
        kids.append({"type": "Mesh3D", "name": f"Gema {i + 1}", "shape": "octa", "w": 0.5, "h": 0.5, "x": round(3.5 * __import__("math").cos(a), 2), "y": 1.3, "z": round(-1.5 + 3.5 * __import__("math").sin(a), 2), "color": "#4cc9f0", "emissive": "#0a6a8a", "shadow": False,
                     "behaviors": [{"type": "collectible", "value": 25}, {"type": "spin", "speed": 90}, {"type": "float", "amp": 0.12, "speed": 2}]})
    kids.append({"type": "Humanoid3D", "name": "Jogador", "x": 0, "y": 0, "z": 3, "ry": 0, "tags": ["player"], "behaviors": [{"type": "player_vr"}]})
    kids.append({"type": "Camera3D", "name": "Câmera", "mode": "first", "fov": 75})
    kids.append({"type": "XRRig", "name": "Plataforma VR", "teleport": True, "hands": True})
    kids += _hud(lang, "vr_room")
    kids.append({"type": "UILabel", "name": "Dica", "text": tr["vr_hint"], "anchor": "bottom-center", "size": 13, "color": "#ffffff"})
    return {"name": "main", "kind": "vr", "settings": {"camera": "first", "shadows": True, "genre": "vr_room", "sky_bottom": c["bottom"], "sky_top": c["top"]}, "rules": {"win": "collect_all"}, "root": {"type": "Node3D", "name": title[:40] or "Sala", "children": kids}}


def _scene_ar(genre: str, theme: str, lang: str, title: str, seed: int) -> Dict[str, Any]:
    import math
    import random
    tr = TR[lang]
    rnd = random.Random(seed)
    kids: List[Dict[str, Any]] = _lights(theme, 12)
    kids.append({"type": "Mesh3D", "name": "Chão (prévia)", "shape": "plane", "w": 30, "d": 30, "color": "#2b3040", "shadow": False, "opacity": 0.55})
    if genre == "ar_place":
        kids.append({"type": "Node3D", "name": "Modelo", "visible": False, "behaviors": [{"type": "place_on_tap"}], "children": [
            {"type": "Mesh3D", "shape": "cylinder", "w": 0.08, "h": 0.3, "y": 0.15, "color": "#6b4a2b"}, {"type": "Mesh3D", "shape": "cone", "w": 0.4, "h": 0.5, "y": 0.5, "color": "#2f7a3a"}, {"type": "Mesh3D", "shape": "cone", "w": 0.3, "h": 0.4, "y": 0.8, "color": "#3f9a4a"}]})
    else:
        for i in range(10):
            a = rnd.random() * 6.283
            r = 2 + rnd.random() * 4
            kids.append({"type": "Mesh3D", "name": f"Item {i + 1}", "shape": "octa" if i % 3 else "torus", "w": 0.35, "h": 0.35, "x": round(math.cos(a) * r, 2), "y": round(0.5 + rnd.random() * 1.4, 2), "z": round(math.sin(a) * r, 2), "color": "#ffd23f" if i % 3 else "#4cc9f0",
                         "emissive": "#aa7a00", "shadow": False, "behaviors": [{"type": "collectible", "value": 10}, {"type": "spin", "speed": 120}, {"type": "float", "amp": 0.12, "speed": 2}]})
    kids.append({"type": "Humanoid3D", "name": "Jogador", "x": 0, "y": 0, "z": 0, "ry": 0, "tags": ["player"], "behaviors": [{"type": "player_fps", "speed": 2.4}]})
    kids.append({"type": "Camera3D", "name": "Câmera", "mode": "first", "fov": 70})
    kids.append({"type": "XRRig", "name": "Plataforma AR"})
    kids.append({"type": "UILabel", "name": "Placar", "text": tr["score"], "anchor": "top-left", "size": 18, "color": "#ffffff"})
    kids.append({"type": "UILabel", "name": "Dica", "text": tr["place_hint"] if genre == "ar_place" else ("Ande e colete os itens" if lang == "pt" else "Walk and collect the items"), "anchor": "bottom-center", "size": 14, "color": "#ffffff"})
    return {"name": "main", "kind": "ar", "settings": {"camera": "first", "shadows": True, "genre": genre, "sky_bottom": "#20242f", "sky_top": "#10131a"}, "rules": {"win": "collect_all" if genre == "ar_hunt" else "none"}, "root": {"type": "Node3D", "name": title[:40] or "AR", "children": kids}}


# ============================================================================ jogo completo
def dialogues(lang: str, title: str, genre: str) -> Dict[str, List[Dict[str, str]]]:
    g = TR[lang]["guia"]
    if lang == "pt":
        lines = [(g, f"Bem-vindo a “{title}”!"), (g, "Pegue tudo o que brilha e chegue ao objetivo." if genre not in ("platformer", "shooter") else "Chegue ao fim da fase sem perder todos os corações."), (g, "Cuidado com os inimigos. Boa sorte!")]
    else:
        lines = [(g, f"Welcome to “{title}”!"), (g, "Grab everything that shines and reach the goal." if genre not in ("platformer", "shooter") else "Reach the end of the level without losing all your hearts."), (g, "Watch out for enemies. Good luck!")]
    return {"guia": [{"speaker": s, "text": t} for s, t in lines], "npc1": [{"speaker": s, "text": t} for s, t in lines]}


def gdd(meta: Dict[str, Any], lang: str, prompt: str) -> str:
    pt = lang == "pt"
    k, g = meta["kind"], meta["genre"]
    kinds = S.KINDS[k]
    genre = S.GENRES[g]
    L = (lambda a, b: a if pt else b)
    ctl = {"2d": L("Setas/WASD movem, Espaço pula ou atira, E fala.", "Arrows/WASD move, Space jumps or shoots, E talks."), "2.5d": L("Setas/WASD movem na grade isométrica, Espaço pula, E fala.", "Arrows/WASD move on the isometric grid, Space jumps, E talks."),
           "3d": L("WASD move, mouse olha, Espaço pula, Shift corre, E fala.", "WASD moves, mouse looks, Space jumps, Shift runs, E talks."), "vr": L("Teletransporte com o gatilho, pegar com o botão lateral, analógico para andar.", "Teleport with the trigger, grab with the side button, stick to walk."),
           "ar": L("Aponte para o chão e toque para colocar; ande pelo ambiente.", "Point at the floor and tap to place; walk around.")}[k]
    return "\n".join([f"# {meta['name']} — {L('Documento de design (GDD)', 'Game design document (GDD)')}", "", f"> {L('Gerado pelo ASTA Game Engine. Edite à vontade: este arquivo é seu.', 'Generated by ASTA Game Engine. Edit freely: this file is yours.')}", "",
                      f"## {L('Visão geral', 'Overview')}", "", f"- **{L('Tipo', 'Type')}:** {kinds['label']} — {kinds['hint']}", f"- **{L('Gênero', 'Genre')}:** {genre['label']} — {genre['hint']}", f"- **{L('Tema', 'Theme')}:** {meta['theme']}",
                      f"- **{L('Pedido original', 'Original request')}:** {prompt.strip()[:400] or '—'}", "", f"## {L('Loop de jogo', 'Core loop')}", "",
                      L("1. Explorar o mundo.\n2. Coletar moedas e gemas (pontos).\n3. Evitar ou derrotar inimigos (vida).\n4. Chegar ao objetivo para vencer.", "1. Explore the world.\n2. Collect coins and gems (score).\n3. Avoid or defeat enemies (health).\n4. Reach the goal to win."), "",
                      f"## {L('Controles', 'Controls')}", "", ctl, "", f"## {L('Regras', 'Rules')}", "", f"- {L('Vida inicial', 'Starting health')}: 3.", f"- {L('Vitória', 'Win')}: {L('alcançar o objetivo (e, em alguns jogos, coletar tudo)', 'reach the goal (and, in some games, collect everything)')}.",
                      f"- {L('Derrota', 'Lose')}: {L('perder toda a vida', 'run out of health')}.", "", f"## {L('Personagens', 'Characters')}", "", f"- **{L('Jogador', 'Player')}**", f"- **{L('Guia', 'Guide')}** — {L('NPC que explica o objetivo', 'NPC who explains the goal')}", f"- {L('Inimigos comuns e perseguidores', 'Common enemies and chasers')}", "",
                      f"## {L('Arte e som', 'Art and sound')}", "", L("Sprites vetoriais gerados (aba Assets) e trilha/efeitos sonoros (aba Sound).", "Generated vector sprites (Assets tab) and music/sound effects (Sound tab)."), "", f"## {L('Próximos passos', 'Next steps')}", "",
                      L("- Ajuste fases na aba **Map**.\n- Troque a arte na aba **Assets**.\n- Escreva roteiros e diálogos na aba **Scripts**.\n- Exporte na aba **Publish**.", "- Tweak levels in the **Map** tab.\n- Swap the art in the **Assets** tab.\n- Write scripts and dialogues in the **Scripts** tab.\n- Export in the **Publish** tab."), ""])


def dialogues_md(d: Dict[str, List[Dict[str, str]]]) -> str:
    out = ["# Diálogos", "", "Formato: `## id` e, abaixo, uma fala por linha `Nome: texto`. A aba Scripts envia isto para `data/dialogues.json`.", ""]
    for k, lines in d.items():
        if k == "npc1":
            continue
        out += [f"## {k}", ""] + [f"{l['speaker']}: {l['text']}" for l in lines] + [""]
    return "\n".join(out)


def build(prompt: str, kind: str = "", genre: str = "", theme: str = "", length: str = "medium", seed: int = 0, title: str = "", lang: str = "", enemies: Optional[float] = None, coins: Optional[float] = None,
          hp: Optional[int] = None, mood: str = "", extras: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """O jogo completo (dados): meta, cenas, mapas, diálogos, imagens SVG, sons WAV, configurações e documentos."""
    prompt = prompt or ""
    kind, genre, theme = detect(prompt, kind, genre, theme)
    lang = lang if lang in TR else detect_lang(prompt)
    seed = seed or seed_of(prompt, kind + genre + theme)
    title = (title or make_title(prompt, genre, theme, lang)).strip()[:60]
    length = length if length in maps.SIZES else "medium"
    c = S.THEME_COLORS[theme]
    p = _norm(prompt)
    if enemies is None:
        enemies = 1.6 if re.search(r"dificil|hard|muitos inimigos|many enemies", p) else 0.5 if re.search(r"facil|easy|poucos inimigos|few enemies", p) else 1.0
    if coins is None:
        coins = 1.5 if re.search(r"muitas moedas|many coins|colet", p) else 1.0
    enemies, coins = max(0.0, min(2.5, float(enemies))), max(0.2, min(2.5, float(coins)))
    scenes: Dict[str, Dict[str, Any]] = {}
    mp: Dict[str, Dict[str, Any]] = {}
    if kind in ("2d", "2.5d"):
        mp_path = "maps/level1.map.json"
        gen = {"platformer": maps.gen_platformer, "topdown": maps.gen_topdown, "shooter": maps.gen_shooter, "iso": maps.gen_iso}[genre]
        m = S.norm_map(gen(seed, theme, length, enemies, coins))
        m["name"] = "Fase 1" if lang == "pt" else "Level 1"
        mp[mp_path] = m
        scenes["main"] = S.norm_scene(_scene2d(kind, genre, theme, lang, mp_path, title), kind, "main")
        if length != "short" and genre in ("platformer", "topdown", "iso"):    # uma segunda fase quando o jogo não é curto
            m2 = S.norm_map(gen(seed + 1, theme, length, enemies * 1.3, coins))
            m2["name"] = "Fase 2" if lang == "pt" else "Level 2"
            mp["maps/level2.map.json"] = m2
            scenes["level2"] = S.norm_scene(_scene2d(kind, genre, theme, lang, "maps/level2.map.json", title, "level2"), kind, "level2")
    elif kind in ("3d", "vr") and genre != "vr_room":
        mp_path = "maps/world1.map.json"
        m = maps.generate_3d(seed, theme, "", 200.0 if length != "short" else 140.0, 65, int(14 * coins), int(4 * enemies), 1.0)
        m["name"] = "Mundo 1" if lang == "pt" else "World 1"
        mp[mp_path] = m
        scenes["main"] = S.norm_scene(_scene3d(kind, genre, theme, lang, mp_path, title), kind, "main")
    elif genre == "vr_room":
        scenes["main"] = S.norm_scene(_scene_vr_room(theme, lang, title), "vr", "main")
        kind = "vr"
    else:
        scenes["main"] = S.norm_scene(_scene_ar(genre, theme, lang, title, seed), "ar", "main")
        kind = "ar"
    if extras:
        main = scenes["main"]
        main["root"]["children"] = list(main["root"].get("children", [])) + [x for x in extras if isinstance(x, dict)][:20]
        scenes["main"] = S.norm_scene(main, kind, "main")
    # imagens e sons
    images = art.theme_svg_set(c, genre)
    sounds: Dict[str, bytes] = {n: audio.sfx(n, seed) for n in ("coin", "jump", "hit", "win", "lose", "powerup", "shoot", "select", "door", "place")}
    mood = mood if mood in audio.MOODS else audio.THEME_MOOD.get(theme, "calm")
    sounds["theme"] = audio.music(mood, 8, seed, 196.0 + (seed % 5) * 14, 0)
    settings = S.norm_project_settings({"hp": hp or 3, "audio": {"music": "theme", "events": {n: n for n in ("coin", "jump", "hit", "win", "lose", "powerup", "shoot", "select", "door", "place")}}}, kind)
    meta = {"name": title, "kind": kind, "genre": genre, "theme": theme, "language": lang, "seed": seed, "length": length, "description": (prompt.strip()[:300] or f"{S.GENRES[genre]['label']} — {S.KINDS[kind]['label']}")}
    dlg = dialogues(lang, title, genre)
    return {"meta": meta, "scenes": scenes, "maps": mp, "dialogues": dlg, "images": images, "sounds": sounds, "settings": settings,
            "docs": {"gdd.md": gdd(meta, lang, prompt), "dialogues.md": dialogues_md(dlg), "prompt.md": f"# Prompt\n\n{prompt.strip() or '(vazio)'}\n"}}


# ============================================================================ edições simples por regras (fallback do «editar o jogo»)
def apply_edit(prompt: str, scenes: Dict[str, Dict[str, Any]], maps_: Dict[str, Dict[str, Any]], meta: Dict[str, Any], settings: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    """Ajustes por palavras-chave sobre um jogo existente: tema, mais/menos inimigos e moedas, vida, nova fase. Devolve (o que foi feito, mudanças em {scenes, maps, meta, settings, sounds})."""
    import copy
    import random
    p = _norm(prompt)
    done: List[str] = []
    ch: Dict[str, Any] = {"scenes": {}, "maps": {}, "meta": {}, "settings": {}, "sounds": {}, "images": {}}
    kind, genre = meta.get("kind", "2d"), meta.get("genre", "platformer")
    theme = None
    for t, words in THEME_WORDS:
        if _has(" " + p + " ", words):
            theme = t
            break
    seed = seed_of(prompt, str(meta.get("seed", 0)))
    rnd = random.Random(seed)
    if theme and theme != meta.get("theme"):
        c = S.THEME_COLORS[theme]
        for name, sc in scenes.items():
            sc = copy.deepcopy(sc)
            sc["settings"]["sky_top"], sc["settings"]["sky_bottom"] = c["top"], c["bottom"]
            for n in S.walk(sc["root"]):
                if n["type"] == "Sky3D":
                    n["top"], n["bottom"], n["stars"] = c["top"], c["bottom"], theme in ("night", "space", "cave")
                if n["type"] == "Parallax2D" and n.get("style") in ("hills", "trees", "mountains"):
                    n["color"] = art._shade(c["ground"] if n["style"] != "mountains" else c["stone"], -0.3)
            ch["scenes"][name] = sc
        for path, m in maps_.items():
            m = copy.deepcopy(m)
            m["theme"] = theme
            if m["kind"] == "2d":
                pal = maps.palette2d(theme)
                for k, v in m["palette"].items():
                    if k in pal:
                        v["color"] = pal[k]["color"]
            else:
                m["biome"] = maps.BIOME_OF_THEME.get(theme, m.get("biome", "temperate"))
                m["colors"] = maps.BIOME_COLORS[m["biome"]]
            ch["maps"][path] = m
        ch["meta"]["theme"] = theme
        ch["sounds"]["theme"] = audio.music(audio.THEME_MOOD.get(theme, "calm"), 8, seed, 196.0, 0)
        ch["images"].update(art.theme_svg_set(c, genre))
        done.append(f"tema → {theme}")
    more = re.search(r"mais (inimigo|monstro)|more enem|mais dificil|harder", p)
    less = re.search(r"menos (inimigo|monstro)|fewer enem|mais facil|easier|menos dificil", p)
    morec = re.search(r"mais (moeda|ouro|item|gema)|more coin|more gem|more item", p)
    lessc = re.search(r"menos (moeda|item|gema)|fewer coin", p)
    if more or less or morec or lessc:
        for path, m in maps_.items():
            m = copy.deepcopy(ch["maps"].get(path, m))
            objs = m["objects"]
            if more or less:
                enemies = [o for o in objs if o["type"] in ("enemy", "chaser", "flyer")]
                if less:
                    drop = set(id(o) for o in enemies[: max(1, len(enemies) // 2)])
                    objs = [o for o in objs if id(o) not in drop]
                else:
                    for o in enemies[: max(2, len(enemies))]:
                        c2 = dict(o)
                        if m["kind"] == "3d":
                            c2["x"] = round(o["x"] + rnd.choice((-8, 8)), 2)
                        else:
                            c2["x"] = max(1, min(m["w"] - 2, o["x"] + rnd.choice((-3, 3))))
                        objs.append(c2)
                done.append("mais inimigos" if more else "menos inimigos")
            if morec or lessc:
                coins_ = [o for o in objs if o["type"] in ("coin", "gem")]
                if lessc:
                    drop = set(id(o) for o in coins_[: max(1, len(coins_) // 2)])
                    objs = [o for o in objs if id(o) not in drop]
                else:
                    for o in coins_[: max(3, len(coins_))]:
                        c2 = dict(o)
                        if m["kind"] == "3d":
                            c2["z"] = round(o["z"] + rnd.choice((-4, 4)), 2)
                        else:
                            c2["x"] = max(1, min(m["w"] - 2, o["x"] + rnd.choice((-2, 2))))
                        objs.append(c2)
                done.append("mais itens" if morec else "menos itens")
            m["objects"] = objs
            ch["maps"][path] = S.norm_map(m)
    hp = re.search(r"(\d+)\s*(vidas|coracoes|hearts|lives)", p)
    if hp:
        ch["settings"]["hp"] = max(1, min(99, int(hp.group(1))))
        done.append(f"vida = {hp.group(1)}")
    return done, ch
