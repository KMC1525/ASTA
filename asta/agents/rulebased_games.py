"""Gerador determinístico (sem IA) de jogos 2D: provedor Demo e fallback dos agentes.

Cada gênero tem um projeto de jogo completo e jogável (texto em português/inglês), parametrizado pelo pedido
do usuário (nomes, ambientação, tema, duração). Tudo é validado depois por games2d.schema.normalize_game.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..games2d import schema as S
from .rulebased import CLOTH, HAIR, SKIN, _rng, detect_lang, short_title
from .rulebased_avatars import NAME_RES

GENRE_KEYS = [
    ("point_and_click", r"point.?and.?click|point ?& ?click|aventura gr[áa]fica|adventure game|escape room|monkey island|enigma|puzzle de objetos|sala trancada"),
    ("side_scroller", r"side.?scroll|shoot.?em.?up|shmup|\bnave\b|spaceship|runner|corrida infinita|endless|r-type|atirar|shooter"),
    ("platformer", r"platform|plataforma|mario|\bpular\b|\bpulo\b|metroid|sonic"),
    ("visual_novel", r"visual novel|\bvn\b|ren'?py|dating sim|romance|novela visual|hist[óo]ria interativa|namor|escolhas"),
    ("rpg", r"\brpg\b|rpg maker|jrpg|masmorra|dungeon|her[óo]i\b|\bhero\b|\bquest\b|miss[ãa]o|aventura|drag[ãa]o|dragon|magia|magic|batalha|battle"),
]
SETTING_KEYS = [  # (regex, cena VN/P&C, tema, humor)
    (r"floresta|forest|bosque|woods", "forest", "forest", "mysterious"), (r"praia|beach|mar\b|ocean|oceano|sea\b", "beach", "sea", "joyful"),
    (r"escola|school|faculdade|college|universidade|university|col[ée]gio", "school", "cozy", "joyful"), (r"caf[ée]|coffee", "cafe", "cozy", "calm"),
    (r"castelo|castle|reino|kingdom|medieval", "castle", "fantasy", "epic"), (r"caverna|cave|masmorra|dungeon", "cave", "dungeon", "tense"),
    (r"biblioteca|library", "library", "cozy", "calm"), (r"jardim|garden|parque|park", "garden", "forest", "calm"),
    (r"espa[çc]o|space|nave|galax|alien", "ship", "space", "mysterious"), (r"laborat[óo]rio|laboratory|\blab\b|cyber|futur", "lab", "retro", "tense"),
    (r"escrit[óo]rio|office|empresa", "office", "city", "calm"), (r"cidade|city|rua\b|street|urbano|noite na cidade", "street", "city", "calm"),
    (r"deserto|desert|egito|egypt", "field", "desert", "epic"), (r"neve|snow|inverno|winter|gelo", "field", "snow", "melancholic"),
    (r"terror|horror|assombrad|haunted|fantasma|ghost", "cellar", "horror", "tense"), (r"p[ôo]r do sol|sunset|entardecer", "sunset", "sunset", "melancholic"),
    (r"noite|night|estrelas|stars", "night_sky", "night", "mysterious"), (r"cozinha|kitchen", "kitchen", "cozy", "calm"), (r"quarto|bedroom", "bedroom", "cozy", "calm"),
]
DEFAULT_NAMES = {"pt": ["Alex", "Luna", "Theo", "Mia"], "en": ["Alex", "Luna", "Theo", "Mia"]}


def _L(text_: str, hint: str = "") -> str:
    code = (hint or "").lower()[:2]
    if code in ("pt", "en"):
        return code
    return "pt" if detect_lang(text_ or "") == "pt" else "en"


def _t(lang: str, pt: str, en: str) -> str:
    return pt if lang == "pt" else en


def _app(rng, hair=None, top=None, fem=None) -> Dict[str, Any]:
    fem = rng.random() < 0.5 if fem is None else fem
    return {"skin": SKIN[rng.randrange(len(SKIN))], "hair": hair or HAIR[rng.randrange(len(HAIR))], "hair_style": "long" if fem else "short",
            "top": top or CLOTH[rng.randrange(len(CLOTH))], "bottom": "#2a2a30", "height": 1.65 if fem else 1.78, "build": 0.95 if fem else 1.05, "accessory": "none"}


# --------------------------------------------------------------------------- analista


def analyst(inp: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(inp.get("prompt") or "")
    digest = str(inp.get("attachments_digest") or "")
    blob = f"{prompt}\n{digest[:1500]}"
    lang = _L(prompt or digest, inp.get("language_hint", ""))
    want = str(inp.get("genre") or "auto")
    genre = want if want in S.GENRE_IDS else next((g for g, pat in GENRE_KEYS if re.search(pat, blob, re.I)), "visual_novel")
    names: List[str] = []
    for rx in NAME_RES:
        for m in rx.finditer(prompt):
            for part in re.split(r"\s*(?:,|\be\b|\band\b|\by\b|&)\s*", m.group(1)):
                if part.strip() and part.strip() not in names:
                    names.append(part.strip())
    settings = [(sc, th, mo) for pat, sc, th, mo in SETTING_KEYS if re.search(pat, blob, re.I)]
    scenes = list(dict.fromkeys(s[0] for s in settings))[:3]
    theme = settings[0][1] if settings else "fantasy"
    mood = settings[0][2] if settings else "calm"
    mode = "runner" if re.search(r"runner|corrida|correr|endless|infinit", blob, re.I) else "shooter"
    prev = inp.get("previous") or {}  # atualização: o jogo mantém o nome (o pedido de mudança não é o título)
    title = str(prev.get("title") or "") or short_title(prompt, _t(lang, "Novo jogo", "New game"), words=8)
    return {"genre": genre, "title": title, "premise": prompt[:300] or digest[:300], "language": {"pt": "pt-BR", "en": "en"}[lang],
            "theme": theme, "mood": mood, "names": names[:6], "scenes": scenes, "mode": mode, "length": str(inp.get("length") or "medium"),
            "notes": ([digest[:240].replace("\n", " ")] if digest else [])}


def reviewer(inp: Dict[str, Any]) -> Dict[str, Any]:
    issues = [{"area": "game", "severity": "high", "problem": p, "fix": "corrija isso no jogo"} for p in (inp.get("problems") or [])]
    return {"approved": not issues, "score": 7 if not issues else 4, "issues": issues, "summary": "Revisão automática (modo Demo)."}


# --------------------------------------------------------------------------- designer


def designer(inp: Dict[str, Any]) -> Dict[str, Any]:
    brief = inp.get("brief") or {}
    genre = brief.get("genre") if brief.get("genre") in S.GENRE_IDS else "visual_novel"
    lang = _L("", brief.get("language", "en"))
    length = brief.get("length") if brief.get("length") in S.LENGTHS else "medium"
    rng = _rng("game", genre, brief.get("title"), brief.get("premise"))
    fn = {"visual_novel": _vn, "rpg": _rpg, "platformer": _platformer, "side_scroller": _side_scroller, "point_and_click": _adventure}[genre]
    data = fn(brief, lang, length, rng)
    mood = brief.get("mood") if brief.get("mood") in S.MOODS else "calm"
    return {"title": brief.get("title") or "Game", "description": (brief.get("premise") or "")[:240], "language": brief.get("language", "en"),
            "style": {"theme": brief.get("theme") if brief.get("theme") in S.THEMES else "fantasy", "accent": "#ffd166", "pixel": True},
            "audio": {"music": {"enabled": True, "mood": mood, "scale": "minor" if mood in ("tense", "melancholic", "mysterious") else "major", "tempo": 76 if mood == "calm" else 100}, "sfx": True},
            "data": data}


# --------------------------------------------------------------------------- visual novel


def _vn(b: Dict[str, Any], lang: str, length: str, rng) -> Dict[str, Any]:
    names = list(b.get("names") or [])
    A = names[0] if names else rng.choice(["Luna", "Mia", "Clara", "Nina"])
    B = names[1] if len(names) > 1 else rng.choice([n for n in ["Theo", "Caio", "Davi", "Leo"] if n != A])
    scenes = list(b.get("scenes") or []) + [s for s in ("garden", "cafe", "street", "sunset", "night_sky") if s not in (b.get("scenes") or [])]
    n_scenes = {"short": 2, "medium": 3, "long": 4}[length]
    t = lambda pt, en: _t(lang, pt, en)  # noqa: E731
    hair = ["#b5451b", "#2a2a35", "#e3c36a", "#5a3a22"]
    chars = [{"id": "a", "name": A, "color": "#f4a6c8", "appearance": _app(rng, hair[rng.randrange(4)], "#c0506f", True)},
             {"id": "b", "name": B, "color": "#8ecbff", "appearance": _app(rng, hair[rng.randrange(4)], "#3b5b7a", False)}]
    labels: Dict[str, List[dict]] = {}
    say = lambda who, text_: {"c": "say", "who": who, "text": text_}  # noqa: E731
    nar = lambda text_: {"c": "say", "who": "", "text": text_}  # noqa: E731
    premise = (b.get("premise") or "").strip()
    labels["start"] = [
        {"c": "music", "mood": b.get("mood", "calm")}, {"c": "scene", "bg": scenes[0]},
        nar(t(f"Tudo começou num dia comum. {premise[:140]}" if premise else "Tudo começou num dia comum, mas algo estava diferente no ar.",
              f"It all started on an ordinary day. {premise[:140]}" if premise else "It all started on an ordinary day, but something felt different in the air.")),
        {"c": "input", "var": "player", "prompt": t("Qual é o seu nome?", "What is your name?"), "default": "Alex"},
        {"c": "show", "char": "a", "expr": "happy", "at": "center"},
        say("a", t("Ei, {player}! Estava te esperando. Você veio mesmo!", "Hey, {player}! I was waiting for you. You really came!")),
        {"c": "menu", "prompt": t("O que você responde?", "What do you say?"), "choices": [
            {"text": t("“Claro que vim. Queria te ver.”", "“Of course I came. I wanted to see you.”"), "jump": "s1_warm", "set": [{"var": "bond", "op": "+=", "value": 2}]},
            {"text": t("“Fiquei curioso(a) com o convite.”", "“I was curious about the invitation.”"), "jump": "s1_curious", "set": [{"var": "bond", "op": "+=", "value": 1}]},
            {"text": t("“Não tenho muito tempo.”", "“I don't have much time.”"), "jump": "s1_cold", "set": [{"var": "bond", "op": "-=", "value": 1}]}]}]
    labels["s1_warm"] = [{"c": "show", "char": "a", "expr": "shy", "at": "center"}, say("a", t("Eu... fico feliz de ouvir isso. De verdade.", "I... I'm happy to hear that. Really.")), {"c": "sfx", "name": "chime"}, {"c": "jump", "label": "scene2"}]
    labels["s1_curious"] = [say("a", t("Haha, então valeu a pena o mistério! Vem, quero te mostrar uma coisa.", "Haha, so the mystery paid off! Come on, I want to show you something.")), {"c": "jump", "label": "scene2"}]
    labels["s1_cold"] = [{"c": "show", "char": "a", "expr": "sad", "at": "center"}, say("a", t("Ah... entendo. Então vou ser rápida(o).", "Oh... I see. Then I'll keep it short.")), {"c": "jump", "label": "scene2"}]
    nxt = "scene2"
    for i in range(2, n_scenes + 1):
        cur, after = f"scene{i}", (f"scene{i + 1}" if i < n_scenes else "finale")
        bg = scenes[(i - 1) % len(scenes)]
        who = "b" if i % 2 == 0 else "a"
        labels[cur] = [
            {"c": "scene", "bg": bg}, {"c": "show", "char": "a", "expr": "neutral", "at": "left"}, {"c": "show", "char": "b", "expr": "happy", "at": "right"},
            nar(t("O lugar estava quase vazio. Só o vento e o som distante da cidade.", "The place was almost empty. Only the wind and the distant sound of the city.")),
            say("b", t(f"{A}, você não me disse que traria alguém! Prazer, {{player}}. Eu sou {B}.", f"{A}, you never told me you'd bring someone! Nice to meet you, {{player}}. I'm {B}.")),
            say("a", t(f"{B} é meu melhor amigo. Ele fala demais, mas é gente boa.", f"{B} is my best friend. He talks too much, but he's a good guy.")),
            {"c": "menu", "prompt": t("Como você reage?", "How do you react?"), "choices": [
                {"text": t(f"Conversar com {B} e fazer amizade", f"Talk to {B} and make friends"), "jump": f"{cur}_b", "set": [{"var": "friends", "op": "+=", "value": 1}, {"var": "bond", "op": "+=", "value": 1}]},
                {"text": t(f"Ficar do lado de {A}", f"Stay by {A}'s side"), "jump": f"{cur}_a", "set": [{"var": "bond", "op": "+=", "value": 2}]},
                {"text": t("Observar em silêncio", "Watch in silence"), "jump": after}]}]
        labels[f"{cur}_b"] = [{"c": "show", "char": "b", "expr": "surprised", "at": "right"}, say("b", t("Você é legal, sabia? Pode contar comigo!", "You're cool, you know? You can count on me!")), {"c": "sfx", "name": "coin"}, {"c": "jump", "label": after}]
        labels[f"{cur}_a"] = [{"c": "show", "char": "a", "expr": "shy", "at": "left"}, say("a", t("Obrigada(o) por não me deixar sozinha(o) nessa.", "Thanks for not leaving me alone in this.")), {"c": "jump", "label": after}]
    labels["finale"] = [
        {"c": "scene", "bg": scenes[-1] if len(scenes) > 1 else "sunset"}, {"c": "music", "mood": "melancholic"}, {"c": "show", "char": "a", "expr": "happy", "at": "center"},
        nar(t("O dia chegava ao fim. Havia algo a dizer e pouco tempo para dizer.", "The day was coming to an end. There was something to say and little time to say it.")),
        {"c": "if", "cond": "bond >= 4", "then": [{"c": "jump", "label": "end_best"}], "else": [{"c": "if", "cond": "bond >= 2", "then": [{"c": "jump", "label": "end_good"}], "else": [{"c": "jump", "label": "end_cold"}]}]}]
    labels["end_best"] = [{"c": "show", "char": "a", "expr": "shy", "at": "center"}, say("a", t("{player}... eu acho que gosto de você. Posso te dar a mão?", "{player}... I think I like you. May I hold your hand?")), {"c": "sfx", "name": "chime"},
                          nar(t("Vocês caminharam juntos até o fim da tarde.", "You walked together until the end of the afternoon.")), {"c": "end", "title": t("Final: Juntos", "Ending: Together")}]
    labels["end_good"] = [say("a", t("Foi um dia muito bom, {player}. Vamos repetir qualquer dia?", "It was a really good day, {player}. Shall we do it again sometime?")), {"c": "end", "title": t("Final: Bons amigos", "Ending: Good friends")}]
    labels["end_cold"] = [{"c": "show", "char": "a", "expr": "sad", "at": "center"}, say("a", t("Tudo bem. Talvez em outra hora...", "That's okay. Maybe some other time...")), {"c": "end", "title": t("Final: Cada um por si", "Ending: Separate ways")}]
    return {"characters": chars, "backgrounds": {s: {"scene": s} for s in scenes}, "variables": {"bond": 0, "friends": 0}, "start": "start", "labels": labels}


# --------------------------------------------------------------------------- RPG


def _grid(w: int, h: int, ch: str = ".") -> List[List[str]]:
    return [[ch] * w for _ in range(h)]


def _border(g, ch="T"):
    for x in range(len(g[0])):
        g[0][x] = g[-1][x] = ch
    for y in range(len(g)):
        g[y][0] = g[y][-1] = ch


def _rect(g, x, y, w, h, ch):
    for yy in range(y, min(y + h, len(g))):
        for xx in range(x, min(x + w, len(g[0]))):
            g[yy][xx] = ch


def _house(g, x, y):
    _rect(g, x, y, 5, 3, "H")
    g[y + 2][x + 2] = "D"
    _rect(g, x, y + 3, 5, 1, ",")


def _scatter(g, rng, ch, n, keep=(".",)):
    for _ in range(n):
        x, y = rng.randrange(1, len(g[0]) - 1), rng.randrange(1, len(g) - 1)
        if g[y][x] in keep:
            g[y][x] = ch


def _rows(g) -> List[str]:
    return ["".join(r) for r in g]


def _rpg(b: Dict[str, Any], lang: str, length: str, rng) -> Dict[str, Any]:
    t = lambda pt, en: _t(lang, pt, en)  # noqa: E731
    names = list(b.get("names") or [])
    hero_name = names[0] if names else rng.choice(["Aria", "Kael", "Lia", "Ravi"])
    npc_name = names[1] if len(names) > 1 else t("Anciã Maren", "Elder Maren")
    foe = {"pt": ("Lorde das Sombras", "Slime", "Morcego"), "en": ("Shadow Lord", "Slime", "Bat")}[lang]
    cnt = {"short": 1, "medium": 2, "long": 3}[length]

    # ----- vila
    v = _grid(28, 18)
    _border(v)
    for x in (3, 12, 20):
        _house(v, x, 2)
    _rect(v, 2, 6, 25, 1, ",")
    for x in (5, 14, 22):
        _rect(v, x, 5, 1, 1, ",")
    _rect(v, 21, 10, 4, 3, "~")
    _scatter(v, rng, "T", 22)
    _scatter(v, rng, "F", 14)
    v[6][27] = ","
    v[7][27] = ","
    # ----- floresta
    f = _grid(32, 18)
    _border(f)
    _rect(f, 1, 8, 30, 2, ",")
    for y in range(8, 3, -1):
        f[y][16] = ","
    _scatter(f, rng, "T", 120)
    _rect(f, 1, 8, 30, 2, ",")
    _rect(f, 15, 3, 3, 3, ",")
    f[8][0] = f[9][0] = f[8][31] = f[9][31] = ","
    _scatter(f, rng, "F", 18)
    # ----- caverna
    c = _grid(30, 16, "#")
    _rect(c, 1, 7, 28, 2, "_")
    _rect(c, 3, 3, 6, 4, "_")
    _rect(c, 12, 9, 6, 5, "_")
    _rect(c, 21, 3, 7, 11, "_")
    _rect(c, 5, 6, 2, 2, "_")
    _rect(c, 14, 8, 2, 2, "_")
    c[7][0] = c[8][0] = "_"
    maps: Dict[str, Any] = {
        "village": {"name": t("Vila Alder", "Alder Village"), "theme": "town", "music": "calm", "tiles": _rows(v), "events": [
            {"id": "elder", "kind": "npc", "x": 7, "y": 7, "name": npc_name, "pages": [
                {"if": "boss_down", "commands": [{"c": "say", "who": npc_name, "text": t("Você salvou a vila! Seremos eternamente gratos.", "You saved the village! We'll be forever grateful.")}]},
                {"if": "met_elder", "commands": [{"c": "say", "who": npc_name, "text": t(f"Vá à caverna, a leste da floresta, e derrote o {foe[0]}.", f"Go to the cave, east of the forest, and defeat the {foe[0]}.")}]},
                {"commands": [{"c": "say", "who": npc_name, "text": t(f"{hero_name}! Uma sombra tomou a caverna além da floresta.", f"{hero_name}! A shadow has taken the cave beyond the forest.")},
                              {"c": "say", "who": npc_name, "text": t("Leve estas poções e derrote o mal que a habita.", "Take these potions and defeat the evil that dwells there.")},
                              {"c": "item", "id": "potion", "n": 3}, {"c": "set", "var": "met_elder", "op": "=", "value": True}]}]},
            {"id": "merchant", "kind": "npc", "x": 15, "y": 7, "name": t("Mercador", "Merchant"), "commands": [{"c": "say", "who": t("Mercador", "Merchant"), "text": t("Bem-vindo! Dê uma olhada nas mercadorias.", "Welcome! Have a look at my wares.")}, {"c": "shop", "items": ["potion", "ether"]}]},
            {"id": "fountain", "kind": "heal", "x": 18, "y": 9, "name": t("Fonte", "Fountain"), "icon": "⛲", "pages": [{"commands": [{"c": "say", "who": "", "text": t("A água cristalina restaura suas forças.", "The crystal water restores your strength.")}, {"c": "heal"}]}]},
            {"id": "villager", "kind": "npc", "x": 9, "y": 11, "name": t("Aldeã", "Villager"), "commands": [{"c": "say", "who": t("Aldeã", "Villager"), "text": t("A floresta está cheia de slimes. Cuidado!", "The forest is full of slimes. Be careful!")}]},
            {"id": "sign", "kind": "sign", "x": 26, "y": 5, "icon": "🪧", "commands": [{"c": "say", "who": "", "text": t("→ Floresta Sussurrante", "→ Whispering Forest")}]},
            {"id": "to_forest", "kind": "warp", "x": 27, "y": 6, "pages": [{"commands": [{"c": "warp", "map": "forest", "x": 1, "y": 8}]}]},
            {"id": "to_forest2", "kind": "warp", "x": 27, "y": 7, "pages": [{"commands": [{"c": "warp", "map": "forest", "x": 1, "y": 9}]}]}], "encounters": {"rate": 0, "groups": []}},
        "forest": {"name": t("Floresta Sussurrante", "Whispering Forest"), "theme": "forest", "music": "mysterious", "tiles": _rows(f), "events": [
            {"id": "w_back", "kind": "warp", "x": 0, "y": 8, "pages": [{"commands": [{"c": "warp", "map": "village", "x": 26, "y": 6}]}]},
            {"id": "w_back2", "kind": "warp", "x": 0, "y": 9, "pages": [{"commands": [{"c": "warp", "map": "village", "x": 26, "y": 7}]}]},
            {"id": "w_cave", "kind": "warp", "x": 31, "y": 8, "pages": [{"commands": [{"c": "warp", "map": "cave", "x": 1, "y": 7}]}]},
            {"id": "w_cave2", "kind": "warp", "x": 31, "y": 9, "pages": [{"commands": [{"c": "warp", "map": "cave", "x": 1, "y": 8}]}]},
            {"id": "chest1", "kind": "chest", "x": 16, "y": 4, "icon": "🎁", "pages": [{"if": "chest1_open", "commands": [{"c": "say", "who": "", "text": t("O baú está vazio.", "The chest is empty.")}]},
                                                                            {"commands": [{"c": "item", "id": "ether", "n": 2}, {"c": "gold", "n": 25}, {"c": "set", "var": "chest1_open", "op": "=", "value": True},
                                                                                          {"c": "say", "who": "", "text": t("Você encontrou 2 Éteres e 25 moedas!", "You found 2 Ethers and 25 gold!")}, {"c": "sfx", "name": "coin"}]}]},
            {"id": "mage", "kind": "npc", "x": 16, "y": 6, "name": "Lyra", "appearance": _app(rng, "#7a4ab5", "#5b3b6b", True), "pages": [
                {"if": "lyra_joined", "commands": [{"c": "say", "who": "Lyra", "text": t("Vamos juntos!", "Let's go together!")}]},
                {"commands": [{"c": "say", "who": "Lyra", "text": t("Sou Lyra, maga. Ouvi falar da sombra na caverna. Posso ir com você?", "I'm Lyra, a mage. I heard about the shadow in the cave. May I join you?")},
                              {"c": "choice", "options": [{"text": t("Sim, bem-vinda!", "Yes, welcome!"), "do": [{"c": "recruit", "id": "lyra"}, {"c": "set", "var": "lyra_joined", "op": "=", "value": True},
                                                                                                          {"c": "say", "who": "Lyra", "text": t("Você não vai se arrepender!", "You won't regret it!")}, {"c": "remove"}]},
                                                   {"text": t("Agora não.", "Not now."), "do": []}]}]}]}],
            "encounters": {"rate": 0.07 * cnt / 2 + 0.03, "groups": [["slime"], ["bat"], ["slime", "slime"], ["slime", "bat"]]}},
        "cave": {"name": t("Caverna das Sombras", "Shadow Cave"), "theme": "cave", "music": "tense", "tiles": _rows(c), "events": [
            {"id": "c_back", "kind": "warp", "x": 0, "y": 7, "pages": [{"commands": [{"c": "warp", "map": "forest", "x": 30, "y": 8}]}]},
            {"id": "c_back2", "kind": "warp", "x": 0, "y": 8, "pages": [{"commands": [{"c": "warp", "map": "forest", "x": 30, "y": 9}]}]},
            {"id": "chest2", "kind": "chest", "x": 6, "y": 4, "icon": "🎁", "pages": [{"if": "chest2_open", "commands": [{"c": "say", "who": "", "text": t("Vazio.", "Empty.")}]},
                                                                                {"commands": [{"c": "item", "id": "potion", "n": 3}, {"c": "set", "var": "chest2_open", "op": "=", "value": True}, {"c": "say", "who": "", "text": t("3 Poções!", "3 Potions!")}]}]},
            {"id": "boss", "kind": "enemy", "x": 25, "y": 8, "name": foe[0], "pages": [
                {"if": "boss_down", "commands": []},
                {"commands": [{"c": "say", "who": foe[0], "text": t("Ninguém sai vivo daqui...", "No one leaves here alive...")},
                              {"c": "battle", "enemies": ["boss", "bat"], "boss": True, "win": [{"c": "set", "var": "boss_down", "op": "=", "value": True},
                                                                                              {"c": "say", "who": "", "text": t("A escuridão se dissipa. A vila está salva!", "The darkness fades. The village is saved!")},
                                                                                              {"c": "end", "title": t("Você venceu!", "You win!")}]}]}]}],
            "encounters": {"rate": 0.06, "groups": [["bat"], ["bat", "bat"], ["slime", "bat"]]}},
    }
    cls_skill = {"slash": {"name": t("Golpe Duplo", "Double Strike"), "mp": 3, "kind": "damage", "power": 1.8, "stat": "atk", "target": "enemy"},
                 "fire": {"name": t("Bola de Fogo", "Fireball"), "mp": 4, "kind": "damage", "power": 2.0, "stat": "mag", "target": "enemy"},
                 "heal": {"name": t("Cura", "Heal"), "mp": 4, "kind": "heal", "power": 2.2, "stat": "mag", "target": "ally"}}
    return {
        "start": {"map": "village", "x": 6, "y": 8}, "start_party": ["hero"],
        "party": [{"id": "hero", "name": hero_name, "cls": "warrior", "level": 1, "hp": 38, "mp": 10, "atk": 9, "def": 4, "mag": 3, "spd": 6, "skills": ["slash"], "appearance": _app(rng, None, "#3b5b7a", None)},
                  {"id": "lyra", "name": "Lyra", "cls": "mage", "level": 1, "hp": 26, "mp": 20, "atk": 4, "def": 2, "mag": 10, "spd": 7, "skills": ["fire", "heal"], "appearance": _app(rng, "#7a4ab5", "#5b3b6b", True)}],
        "skills": cls_skill,
        "items": {"potion": {"name": t("Poção", "Potion"), "kind": "heal_hp", "amount": 30, "price": 12, "desc": t("Recupera 30 de HP.", "Restores 30 HP.")},
                  "ether": {"name": t("Éter", "Ether"), "kind": "heal_mp", "amount": 12, "price": 20, "desc": t("Recupera 12 de MP.", "Restores 12 MP.")}},
        "enemies": {"slime": {"name": foe[1], "hp": 14, "atk": 5, "def": 1, "spd": 3, "xp": 7, "gold": 4, "color": "#6bd16b", "shape": "slime"},
                    "bat": {"name": foe[2], "hp": 11, "atk": 6, "def": 1, "spd": 7, "xp": 8, "gold": 5, "color": "#9b72d0", "shape": "bat"},
                    "boss": {"name": foe[0], "hp": 90, "atk": 11, "def": 4, "spd": 5, "xp": 60, "gold": 100, "color": "#7a1fa2", "shape": "dragon", "boss": True}},
        "maps": maps}


# --------------------------------------------------------------------------- plataforma


def _plat_level(rng, idx: int, length: str, theme: str) -> Dict[str, Any]:
    H = 14
    width = {"short": 70, "medium": 100, "long": 130}[length] + idx * 14
    hard = min(0.9, 0.3 + idx * 0.18)
    g = _grid(width, H)
    gy = [11] * width  # altura do chão em cada coluna
    x = 0
    kinds = ["flat", "flat", "gap", "steps", "platforms", "flat", "spikes", "gap"]
    while x < width - 14:
        k = "flat" if x < 8 else rng.choice(kinds)
        if k == "flat":
            n = rng.randint(4, 9)
            for i in range(n):
                if x + i < width - 12:
                    if rng.random() < 0.35:
                        g[gy[min(x + i, width - 1)] - 2][x + i] = "C"
            if n >= 6 and rng.random() < 0.5 + hard / 2 and x > 10:
                g[gy[x + 2] - 1][x + 3] = "E"
            elif idx >= 1 and n >= 7 and rng.random() < 0.5 and x > 10:  # morcegos só sobre chão firme (nunca sobre buracos)
                g[gy[x + 3] - 4][x + 3] = "B"
            x += n
        elif k == "gap":
            n = rng.randint(2, 4)
            for i in range(n):
                if x + i < width - 12:
                    gy[x + i] = H + 1
            if n >= 3 and rng.random() < 0.6:
                px = x + 1
                g[gy[max(0, x - 1)] - 3][px] = "="
                g[gy[max(0, x - 1)] - 3][px + 1] = "="
                g[gy[max(0, x - 1)] - 4][px] = "C"
            x += n
            # chão firme depois do buraco (uma "ilha" curta demais entre dois buracos seria injusta)
            for i in range(5):
                if x + i < width:
                    gy[x + i] = gy[max(0, x - n - 1)]
            x += 5
        elif k == "steps":
            base = gy[max(0, x - 1)]
            for i in range(1, 4):
                lvl = max(7, base - i)
                for j in range(2):
                    if x + (i - 1) * 2 + j < width - 12:
                        gy[x + (i - 1) * 2 + j] = lvl
            x += 6
            for i in range(3):
                if x + i < width:
                    gy[x + i] = gy[x - 1]
            x += 3
        elif k == "platforms":
            n = rng.randint(2, 4)
            h0 = gy[max(0, x - 1)] - 3
            for i in range(n):
                px = x + i * 4
                if px + 2 < width - 12:
                    for j in range(3):
                        g[max(2, h0 - (i % 2))][px + j] = "="
                    g[max(1, h0 - (i % 2) - 1)][px + 1] = "C"
            x += n * 4
        elif k == "spikes":
            n = rng.randint(1, 2)  # faixas de 3+ espinhos exigem um pulo no limite do alcance
            for i in range(n):
                if x + i < width - 12:
                    g[gy[x + i] - 1][x + i] = "^"
            x += n + 3
    for xx in range(width):
        for yy in range(gy[xx], H):
            g[yy][xx] = "#"
    # justiça: sem inimigos/espinhos em volta de buracos (pular um inimigo e já ter de pular o buraco é cruel)
    for gx in [i for i in range(width) if gy[i] > H]:
        for xx in range(max(0, gx - 7), min(width, gx + 7)):
            for yy in range(H):
                if g[yy][xx] in "EB^":
                    g[yy][xx] = "."
    # checkpoint no meio da fase, só sobre chão firme (5 colunas seguidas, sem inimigos/espinhos na superfície)
    for kx in range(width // 2, width - 14):
        if all(gy[j] <= H - 3 for j in range(kx - 2, kx + 3)) and all(g[gy[j] - 1][j] == "." for j in range(kx - 2, kx + 3)):
            g[gy[kx] - 1][kx] = "K"
            break
    g[gy[2] - 1][2] = "P"
    for xx in range(width - 12, width):
        gy_ = 11
        for yy in range(gy_, H):
            g[yy][xx] = "#"
    g[10][width - 4] = "F"
    if rng.random() < 0.8:
        g[10][width // 3] = "H" if g[10][width // 3] == "." and g[11][width // 3] == "#" else g[10][width // 3]
    return {"name": f"{idx + 1}", "theme": theme, "tiles": _rows(g)}


def _platformer(b: Dict[str, Any], lang: str, length: str, rng) -> Dict[str, Any]:
    n = {"short": 2, "medium": 3, "long": 5}[length]
    themes = [b.get("theme") if b.get("theme") in S.THEMES else "forest", "night", "dungeon", "desert", "snow"]
    levels = []
    for i in range(n):
        lv = _plat_level(rng, i, length, themes[i % len(themes)])
        lv["name"] = _t(lang, f"Fase {i + 1}", f"Level {i + 1}")
        levels.append(lv)
    return {"player": {"appearance": _app(rng, None, "#c0506f", None), "lives": 3, "hp": 3, "double_jump": False, "speed": 1.0, "jump": 1.0}, "levels": levels,
            "ending": _t(lang, "Você chegou ao fim da jornada. Parabéns!", "You reached the end of the journey. Congratulations!")}


# --------------------------------------------------------------------------- side scroller


def _side_scroller(b: Dict[str, Any], lang: str, length: str, rng) -> Dict[str, Any]:
    mode = b.get("mode") if b.get("mode") in ("shooter", "runner") else "shooter"
    n = {"short": 2, "medium": 3, "long": 5}[length]
    themes = ["space", "sky", "cave", "sea", "city"]
    enemies = {"drone": {"hp": 1, "speed": 1.0, "score": 100, "shoots": False, "shape": "saucer", "color": "#ff6b6b"},
               "blob": {"hp": 2, "speed": 0.8, "score": 150, "shoots": False, "shape": "blob", "color": "#9b72d0"},
               "gunner": {"hp": 3, "speed": 0.7, "score": 250, "shoots": True, "shape": "ship", "color": "#ffb703"}}
    stages = []
    for i in range(n):
        length_s = 40 + i * 8
        waves, obstacles, pickups = [], [], []
        t = 3.0
        patterns = ["line", "sine", "zigzag", "v", "swarm"]
        while t < length_s - 14:
            eid = "drone" if i == 0 and t < 15 else rng.choice(["drone", "drone", "blob", "gunner"] if i > 0 else ["drone", "blob"])
            waves.append({"t": round(t, 1), "enemy": eid, "count": rng.randint(3, 5 + i), "pattern": rng.choice(patterns), "y": round(rng.uniform(0.2, 0.8), 2), "gap": round(rng.uniform(0.35, 0.7), 2)})
            t += rng.uniform(3.2, 5.0) - min(1.2, i * 0.3)
        t = 4.0
        while t < length_s - 4:
            obstacles.append({"t": round(t, 1), "type": rng.choice(["rock", "rock", "crate", "pit", "flyer"])})
            t += rng.uniform(1.4, 2.6) - min(0.6, i * 0.15)
        for k in range(1, length_s // 12):
            pickups.append({"t": float(k * 12), "type": rng.choice(["power", "shield", "heart"]) if mode == "shooter" else "coin", "y": round(rng.uniform(0.25, 0.75), 2)})
        stages.append({"name": _t(lang, f"Fase {i + 1}", f"Stage {i + 1}"), "theme": themes[i % len(themes)], "length": length_s, "speed": 120 + i * 12, "waves": waves if mode == "shooter" else [],
                       "obstacles": obstacles if mode == "runner" else [], "pickups": pickups,
                       "boss": {"t": float(length_s - 10), "name": _t(lang, f"Guardião {i + 1}", f"Guardian {i + 1}"), "hp": 24 + i * 10, "pattern": ["strafe", "sweep", "rain"][i % 3], "color": "#ff4d6d"} if mode == "shooter" else None})
    return {"mode": mode, "player": {"appearance": _app(rng, None, "#3b5b7a", None), "hp": 3, "speed": 1.0, "fire_rate": 1.0, "ship": "ship"}, "stages": stages, "enemies": enemies,
            "ending": _t(lang, "Missão cumprida! O céu está livre.", "Mission accomplished! The sky is free.")}


# --------------------------------------------------------------------------- point & click


def _adventure(b: Dict[str, Any], lang: str, length: str, rng) -> Dict[str, Any]:
    t = lambda pt, en: _t(lang, pt, en)  # noqa: E731
    sc = (b.get("scenes") or [])
    room = sc[0] if sc and sc[0] in ("room", "bedroom", "lab", "library", "kitchen", "cellar", "office") else "room"
    names = list(b.get("names") or [])
    guide = names[0] if names else t("Velho Tomás", "Old Tom")
    say = lambda who, text_: {"c": "say", "who": who, "text": text_}  # noqa: E731
    return {"start": "room", "variables": {"drawer_open": False, "has_key": False},
            "items": {"key": {"name": t("Chave enferrujada", "Rusty key"), "emoji": "🗝️", "desc": t("Parece abrir uma porta antiga.", "It looks like it opens an old door.")},
                      "note": {"name": t("Bilhete", "Note"), "emoji": "📜", "desc": t("“A senha é: ESTRELA”.", "“The password is: STAR”.")}},
            "scenes": {
                "room": {"name": t("Quarto trancado", "Locked room"), "theme": room, "tone": "cozy", "intro": t("Você acorda num quarto desconhecido. A porta está trancada.", "You wake up in an unfamiliar room. The door is locked."), "hotspots": [
                    {"id": "window", "name": t("Janela", "Window"), "x": 0.12, "y": 0.18, "w": 0.18, "h": 0.28, "shape": "window", "look": t("Lá fora, só neblina. Não dá para ver nada.", "Outside there's only fog. You can't see anything.")},
                    {"id": "drawer", "name": t("Gaveta", "Drawer"), "x": 0.42, "y": 0.52, "w": 0.2, "h": 0.2, "shape": "box", "look": t("Uma gaveta emperrada.", "A stuck drawer."),
                     "use": [{"c": "if", "cond": "drawer_open", "then": [say("", t("Já está aberta.", "It's already open."))], "else": [{"c": "set", "var": "drawer_open", "op": "=", "value": True}, {"c": "sfx", "name": "door"}, say("", t("A gaveta se abre! Há uma chave lá dentro.", "The drawer opens! There's a key inside."))]}]},
                    {"id": "key", "name": t("Chave", "Key"), "x": 0.47, "y": 0.5, "w": 0.07, "h": 0.07, "shape": "key", "if": "drawer_open and not has_key", "look": t("Uma chave enferrujada.", "A rusty key."),
                     "take": [{"c": "item", "id": "key", "n": 1}, {"c": "set", "var": "has_key", "op": "=", "value": True}, {"c": "hide"}, {"c": "sfx", "name": "coin"}]},
                    {"id": "door", "name": t("Porta", "Door"), "x": 0.76, "y": 0.2, "w": 0.15, "h": 0.55, "shape": "door", "look": t("Uma porta de madeira, trancada.", "A locked wooden door."),
                     "use": [say("", t("Está trancada. Preciso de uma chave.", "It's locked. I need a key."))],
                     "use_item": {"key": [{"c": "item", "id": "key", "n": -1}, {"c": "sfx", "name": "door"}, say("", t("A chave gira. A porta se abre!", "The key turns. The door opens!")), {"c": "goto", "scene": "hall"}]}}]},
                "hall": {"name": t("Corredor", "Hallway"), "theme": "street" if room == "room" else "castle", "tone": "night", "intro": t("Um corredor escuro. Alguém espera aqui.", "A dark hallway. Someone is waiting here."), "hotspots": [
                    {"id": "guide", "name": guide, "x": 0.2, "y": 0.3, "w": 0.1, "h": 0.5, "shape": "npc", "appearance": _app(rng, "#8a8a8a", "#6b5b3b", False), "look": t("Um senhor de olhar gentil.", "An old man with kind eyes."),
                     "talk": [{"c": "if", "cond": "has_note", "then": [say(guide, t("Boa sorte lá fora!", "Good luck out there!"))], "else": [
                         say(guide, t("Você acordou! Vai precisar de uma senha para sair da casa.", "You're awake! You'll need a password to leave the house.")),
                         {"c": "choice", "options": [{"text": t("Onde acho a senha?", "Where can I find it?"), "do": [say(guide, t("Está neste bilhete. Cuide bem dele.", "It's on this note. Take good care of it.")), {"c": "item", "id": "note", "n": 1}, {"c": "set", "var": "has_note", "op": "=", "value": True}]},
                                                {"text": t("Quem é você?", "Who are you?"), "do": [say(guide, t("Só um velho guardião desta casa.", "Just an old keeper of this house."))]}]}]}]},
                    {"id": "painting", "name": t("Quadro", "Painting"), "x": 0.5, "y": 0.2, "w": 0.16, "h": 0.25, "shape": "painting", "look": t("Uma paisagem noturna cheia de estrelas.", "A night landscape full of stars.")},
                    {"id": "door2", "name": t("Porta do jardim", "Garden door"), "x": 0.8, "y": 0.2, "w": 0.14, "h": 0.55, "shape": "door", "look": t("Leva ao jardim.", "Leads to the garden."), "use": [{"c": "goto", "scene": "garden"}]}]},
                "garden": {"name": t("Jardim", "Garden"), "theme": "garden", "tone": "forest", "intro": t("O ar fresco da noite. O portão da saída está à frente.", "The fresh night air. The exit gate is ahead."), "hotspots": [
                    {"id": "tree", "name": t("Árvore", "Tree"), "x": 0.1, "y": 0.2, "w": 0.2, "h": 0.6, "shape": "tree", "look": t("Uma árvore velha. Há corações entalhados no tronco.", "An old tree. There are hearts carved into the trunk.")},
                    {"id": "statue", "name": t("Estátua", "Statue"), "x": 0.45, "y": 0.3, "w": 0.1, "h": 0.4, "shape": "statue", "look": t("Uma estátua de mármore apontando para o portão.", "A marble statue pointing at the gate.")},
                    {"id": "gate", "name": t("Portão", "Gate"), "x": 0.75, "y": 0.25, "w": 0.18, "h": 0.5, "shape": "gate", "look": t("O portão de saída tem um cadeado com senha.", "The exit gate has a combination lock."),
                     "use": [say("", t("Preciso da senha para abrir o cadeado.", "I need the password to open the lock."))],
                     "use_item": {"note": [say("", t("ESTRELA. O cadeado se abre... e a noite é sua!", "STAR. The lock opens... and the night is yours!")), {"c": "sfx", "name": "powerup"}, {"c": "end", "title": t("Você escapou!", "You escaped!")}]}}]}}}
