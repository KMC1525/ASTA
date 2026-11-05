"""Gerador determinístico (sem IA) para o provedor Demo e para fallback dos agentes.

Permite testar o fluxo inteiro offline e garante que um agente com resposta
inválida nunca derruba a geração do mundo.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from typing import Any, Dict, List

PT_WORDS = {" de ", " que ", " um ", " uma ", " com ", " para ", " em ", " no ", " na ", " os ", " as ", " do ", " da ",
            " você", " vila", " mundo", " floresta", " noite", " chuva", " olá", " oi ", " não", " sim", " por ",
            " meu ", " minha ", " nome ", " estou ", " hoje ", " tudo ", " bem ", " gosto ", " quero ", " mas ", " como ", " pra ", " muito ", " obrigad"}
ES_WORDS = {" el ", " los ", " las ", " una ", " con ", " para ", " en ", " del ", " qué ", " usted", " hola", " bosque", " noche"}


def detect_lang(txt: str) -> str:
    t = " " + re.sub(r"[^\w\s¿¡]", " ", txt.lower()) + " "  # pontuação não atrapalha ("oi!" = " oi ")
    if re.search(r"[぀-ヿ]", t):
        return "ja"
    if re.search(r"[가-힯]", t):
        return "ko"
    if re.search(r"[一-鿿]", t):
        return "zh"
    if re.search(r"[Ѐ-ӿ]", t):
        return "ru"
    pt = sum(1 for w in PT_WORDS if w in t) + (2 if re.search(r"[ãõçê]", t) else 0)
    es = sum(1 for w in ES_WORDS if w in t) + (2 if re.search(r"[ñ¿¡]", t) else 0)
    en = sum(1 for w in (" the ", " and ", " with ", " you ", " of ", " in ", " is ", " a ", " my ", " name ", " i ", " am ", " hello ", " hi ") if w in t)
    if pt > en and pt >= es:
        return "pt"
    if es > en and es > pt:
        return "es"
    return "en" if en else ("pt" if pt else "en")


def _rng(*parts: Any) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:12], 16))


BIOME_KEYWORDS = [
    ("desert", ["deserto", "desert", "areia", "dunas", "oásis", "oasis", "egito", "egypt", "sand"]),
    ("snow", ["neve", "snow", "gelo", "inverno", "winter", "ártico", "arctic", "nevasca", "frozen", "ice"]),
    ("swamp", ["pântano", "pantano", "swamp", "brejo", "bog", "mangue"]),
    ("wasteland", ["apocalipse", "apocalypse", "pós-apocal", "wasteland", "devastad", "zumbi", "zombie", "ruínas", "ruins"]),
    ("urban", ["cidade", "city", "urbano", "urban", "cyberpunk", "metrópole", "metropolis", "rua ", "street"]),
    ("tropical", ["tropical", "selva", "jungle", "praia", "beach", "palmeira", "caribe"]),
    ("island", ["ilha", "island", "arquipélago", "pirata", "pirate", "farol", "lighthouse"]),
    ("mountain", ["montanha", "mountain", "penhasco", "cliff", "alpes", "vale ", "valley", "pico"]),
    ("forest", ["floresta", "forest", "bosque", "woods", "mata ", "élfic", "elven", "elfo"]),
]
BIOME_TAG = {
    "temperate": ("vila", "village"), "forest": ("floresta", "forest"), "desert": ("deserto", "desert"),
    "snow": ("neve", "snow"), "tropical": ("tropical", "tropical"), "island": ("ilha", "island"),
    "urban": ("cidade", "city"), "wasteland": ("pós-apocalipse", "wasteland"), "swamp": ("pântano", "swamp"),
    "mountain": ("montanha", "mountain"),
}
MOOD_TAG = {"calm": ("calmo", "calm"), "tense": ("tenso", "tense"), "mysterious": ("misterioso", "mysterious"),
            "epic": ("épico", "epic"), "melancholic": ("melancólico", "melancholic"), "joyful": ("alegre", "joyful")}

# (papel_pt, papel_en, personalidade_pt, personalidade_en)
ARCHETYPES: Dict[str, List[tuple]] = {
    "temperate": [
        ("herbalista", "herbalist", "gentil, curiosa e cheia de histórias sobre plantas", "gentle, curious and full of stories about plants"),
        ("ferreiro", "blacksmith", "direto, orgulhoso do ofício e de poucas palavras", "blunt, proud of his craft and a man of few words"),
        ("comerciante viajante", "traveling merchant", "falante, esperto e sempre procurando uma boa troca", "talkative, shrewd and always after a good trade"),
        ("guarda da vila", "village guard", "desconfiado, leal e atento a tudo", "wary, loyal and observant"),
        ("criança curiosa", "curious child", "animada, faz perguntas sem parar", "excited, never stops asking questions"),
    ],
    "forest": [
        ("guardiã da floresta", "forest warden", "serena, protetora e ligada à natureza", "serene, protective and attuned to nature"),
        ("caçador", "hunter", "silencioso, paciente e observador", "quiet, patient and watchful"),
        ("eremita", "hermit", "enigmático e filosófico", "cryptic and philosophical"),
        ("lenhador", "woodcutter", "bem-humorado e forte", "good-humored and strong"),
    ],
    "desert": [
        ("nômade", "nomad", "sábio, hospitaleiro e resistente", "wise, hospitable and resilient"),
        ("mercador de oásis", "oasis trader", "carismático, regateia tudo", "charismatic, haggles over everything"),
        ("arqueóloga", "archaeologist", "obcecada por ruínas antigas", "obsessed with ancient ruins"),
    ],
    "snow": [
        ("caçador de peles", "fur trapper", "durão e prático", "tough and practical"),
        ("curandeira", "healer", "acolhedora, sempre com chá quente", "warm, always has hot tea"),
        ("sentinela", "lookout", "atento ao horizonte e ao frio", "watchful of the horizon and the cold"),
    ],
    "tropical": [
        ("pescador", "fisherman", "relaxado, conhece as marés", "easygoing, knows the tides"),
        ("vendedora de frutas", "fruit seller", "simpática e brincalhona", "friendly and playful"),
        ("guia da selva", "jungle guide", "corajoso e prático", "brave and practical"),
    ],
    "island": [
        ("faroleiro", "lighthouse keeper", "solitário e contador de histórias", "solitary storyteller"),
        ("pescadora", "fisherwoman", "bem-humorada e experiente", "witty and seasoned"),
        ("náufrago", "castaway", "desconfiado, mas precisa de ajuda", "wary, but in need of help"),
    ],
    "urban": [
        ("vendedor de rua", "street vendor", "esperto e tagarela", "sharp and chatty"),
        ("guarda noturno", "night watchman", "cansado, mas observador", "tired but observant"),
        ("músico de rua", "street musician", "sonhador e expressivo", "dreamy and expressive"),
        ("informante", "informant", "nervoso e bem relacionado", "nervous and well-connected"),
    ],
    "wasteland": [
        ("sobrevivente", "survivor", "cauteloso, pragmático e cansado", "cautious, pragmatic and weary"),
        ("sucateiro", "scavenger", "oportunista, mas leal a quem ajuda", "opportunistic but loyal to those who help"),
        ("médica de campo", "field medic", "calma sob pressão", "calm under pressure"),
    ],
    "swamp": [
        ("bruxa do pântano", "swamp witch", "misteriosa, sarcástica e sábia", "mysterious, sarcastic and wise"),
        ("barqueiro", "ferryman", "taciturno, conhece os caminhos", "taciturn, knows the paths"),
        ("catador de ervas", "herb gatherer", "agitado e supersticioso", "jittery and superstitious"),
    ],
    "mountain": [
        ("pastor", "shepherd", "calmo e observador do tempo", "calm and weather-wise"),
        ("alpinista", "mountaineer", "determinado e aventureiro", "determined and adventurous"),
        ("monge", "monk", "tranquilo e reflexivo", "tranquil and reflective"),
    ],
}
NAMES = ["Mira", "Doran", "Ila", "Bento", "Selene", "Tavi", "Lia", "Caio", "Nora", "Ravi", "Yara", "Otto", "Zeca", "Alma", "Kael", "Dara"]
SKIN = ["#f1c9a5", "#e0ac84", "#c68a63", "#a8693f", "#7a4a2b", "#4d2e1c"]
HAIR = ["#1c1410", "#3a2615", "#6b4423", "#a5742f", "#d8c27a", "#8a8a8a", "#2a2a35"]
CLOTH = ["#3b5b7a", "#7a3b3b", "#4a6b3b", "#6b5b3b", "#5b3b6b", "#2f6f6f", "#8a6a2a", "#3b3b3b", "#a55a3a"]


def _pick_biome(prompt: str, wb: str, default: str = "temperate") -> str:
    t = f" {prompt.lower()} {wb.lower()} "
    for biome, words in BIOME_KEYWORDS:
        if any(w in t for w in words):
            return biome
    return default


def _pick_weather(t: str, biome: str, default: str = "") -> str:
    for w, words in (
        ("storm", ["tempestade", "storm", "trovão", "thunder"]),
        ("rain", ["chuva", "chuvoso", "rain", "garoa", "drizzle"]),
        ("snow", ["nevasca", "snowing", "nevando", "neve caindo"]),
        ("fog", ["névoa", "neblina", "nevoeiro", "fog", "mist", "bruma"]),
        ("cloudy", ["nublado", "cloudy", "overcast", "cinzento"]),
    ):
        if any(x in t for x in words):
            return w
    return default or ("snow" if biome == "snow" else "clear")


def _pick_time(t: str, default: float = 10.0) -> float:
    for hour, words in (
        (23.0, ["meia-noite", "midnight", "madrugada"]),
        (21.5, ["noite", "night", "noturn"]),
        (18.6, ["anoitecer", "pôr do sol", "por do sol", "sunset", "dusk", "entardecer", "crepúsculo"]),
        (6.4, ["amanhecer", "nascer do sol", "dawn", "sunrise", "alvorada"]),
        (11.0, ["de dia", "durante o dia", "daytime", "in daylight", "pela manhã", "manhã", "morning"]),
        (12.0, ["meio-dia", "meio dia", "noon", "midday"]),
        (15.5, ["tarde", "afternoon"]),
    ):
        if any(x in t for x in words):
            return hour
    return default


def _pick_mood(t: str, default: str = "calm") -> str:
    for mood, words in (
        ("tense", ["terror", "horror", "sombrio", "dark", "perigo", "danger", "tenso", "assustador", "creepy"]),
        ("mysterious", ["misteri", "mystery", "enigma", "oculto", "arcano"]),
        ("epic", ["épico", "epic", "batalha", "battle", "guerra", "war", "heróico"]),
        ("melancholic", ["triste", "sad", "melancol", "abandonad", "abandoned", "solitár", "lonely"]),
        ("joyful", ["alegre", "festa", "festival", "feliz", "happy", "celebra", "joyful"]),
    ):
        if any(x in t for x in words):
            return mood
    return default


_TRAIL = {"de", "da", "do", "das", "dos", "com", "sem", "um", "uma", "uns", "umas", "e", "ou", "a", "o", "as", "os", "em", "no", "na", "nos", "nas", "por", "para", "pra", "que", "à", "ao",
          "of", "the", "an", "and", "or", "with", "without", "in", "on", "at", "for", "to", "by", "from", "that", "its", "his", "her", "their", "my", "your"}


def short_title(prompt: str, fallback: str, words: int = 7) -> str:
    """Título curto a partir do prompt (para o gerador offline): a primeira frase/trecho, sem terminar numa preposição/artigo («…à beira de um»), só a 1ª letra maiúscula."""
    text_ = re.sub(r"\s+", " ", (prompt or "").strip().split("\n")[0])
    text_ = re.split(r"\s*(?:[(\[:;—–]|\s-\s|[.!?](?:\s|$))", text_)[0].strip(" .,:;!?-—–")
    ws = text_.split(" ") if text_ else []
    cut = ws[:words]
    if len(ws) > words or len(text_) > 60:  # texto cortado: não deixa preposição/artigo pendurado no fim
        while len(cut) > 2 and cut[-1].lower().strip(",") in _TRAIL:
            cut.pop()
    title = " ".join(cut).strip(" .,:;!?-—–")
    if not title:
        return fallback
    return title[0].upper() + title[1:]


def _sentence_title(prompt: str, lang: str) -> str:
    return short_title(prompt, "Novo mundo" if lang == "pt" else "New world")


# --------------------------------------------------------------------------- agentes


def analyst(inp: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(inp.get("prompt") or "")
    digest = str(inp.get("attachments_digest") or "")
    wb = inp.get("worldbuilding") or {}
    wb_text = f"{wb.get('name', '')} {wb.get('system_prompt', '')}"
    blob = f"{prompt} {digest[:1500]}"
    lang = detect_lang(prompt or wb_text or digest)
    pt = lang == "pt"
    prev = inp.get("previous") or {}
    pb = prev.get("brief") or {}
    biome = _pick_biome(blob, wb_text, pb.get("biome", "temperate"))
    weather = _pick_weather(blob.lower(), biome, pb.get("weather", ""))
    mood = _pick_mood(blob.lower(), pb.get("mood", "calm"))
    title = prev.get("title") or (_sentence_title(prompt, lang) if prompt.strip() else wb.get("name") or "")
    given = inp.get("characters") or []
    gen_cfg = inp.get("settings") or {}
    rng = _rng("analyst", prompt, biome)
    arche = ARCHETYPES.get(biome, ARCHETYPES["temperate"])
    count = int(gen_cfg.get("max_npcs") or 0) or (4 if gen_cfg.get("size") != "large" else 6)
    count = max(2, min(count, len(arche)))
    chars = []
    names = rng.sample(NAMES, min(len(NAMES), count + 1))
    for i in range(count):
        a = arche[i % len(arche)]
        chars.append({"name": names[i], "role": a[0] if pt else a[1], "personality": a[2] if pt else a[3],
                      "relationship_to_player": "desconhecido" if pt else "stranger"})
    tags = [BIOME_TAG[biome][0 if pt else 1], MOOD_TAG[mood][0 if pt else 1]]
    if weather != "clear":
        tags.append({"rain": "chuva", "storm": "tempestade", "fog": "névoa", "snow": "neve", "cloudy": "nublado"}[weather] if pt else weather)
    tod = _pick_time(blob.lower(), float(pb.get("time_of_day", 10.0) or 10.0))
    if tod >= 20 or tod < 5:
        tags.append("noite" if pt else "night")
    return {
        "title": title or ("Novo mundo" if pt else "New world"),
        "summary": (prompt.strip()[:300] or (wb.get("name") or "")) or ("Um mundo gerado pelo ASTA." if pt else "A world generated by ASTA."),
        "change_request": bool(prev),
        "language": {"pt": "pt-BR", "en": "en", "es": "es"}.get(lang, lang),
        "genre": BIOME_TAG[biome][0 if pt else 1],
        "tone": MOOD_TAG[mood][0 if pt else 1],
        "setting": BIOME_TAG[biome][0 if pt else 1],
        "biome": biome, "weather": weather, "mood": mood, "time_of_day": tod,
        "key_elements": [],
        "characters": [] if (given or prev) else chars,
        "player": {"name": "Você" if pt else "You", "description": ""},
        "tags": tags,
        "constraints": [],
        "attachment_insights": [],
    }


def planner(inp: Dict[str, Any]) -> Dict[str, Any]:
    brief = inp.get("brief") or {}
    biome = brief.get("biome") or "temperate"
    pt = str(brief.get("language", "pt")).startswith("pt")
    rng = _rng("planner", brief.get("title"), biome)
    centers = {
        "desert": [("campfire", "Oásis" if pt else "Oasis"), ("ruin", "Ruínas antigas" if pt else "Ancient ruins"), ("tent", "Acampamento" if pt else "Camp")],
        "snow": [("campfire", "Fogueira" if pt else "Bonfire"), ("cabin", "Cabana" if pt else "Cabin"), ("stone_circle", "Círculo de pedras" if pt else "Stone circle")],
        "urban": [("stall", "Barraca de rua" if pt else "Street stall"), ("lamp", "Praça" if pt else "Square"), ("bench", "Banco" if pt else "Bench")],
        "wasteland": [("campfire", "Refúgio" if pt else "Shelter"), ("ruin", "Ruínas" if pt else "Ruins"), ("crates", "Suprimentos" if pt else "Supplies")],
    }.get(biome, [("well", "Poço da vila" if pt else "Village well"), ("campfire", "Fogueira" if pt else "Campfire"), ("tower", "Torre" if pt else "Tower")])
    return {
        "biome": biome, "size_hint": "medium",
        "time_of_day": brief.get("time_of_day", 10), "weather": brief.get("weather", "clear"),
        "layout": "Centro com ponto de encontro e construções ao redor." if pt else "A central gathering point with buildings around it.",
        "landmarks": [{"label": l, "type": t, "where": rng.choice(["center", "north", "east", "south", "west"])} for t, l in centers],
        "npc_plan": [{"id": c["name"].lower(), "name": c["name"], "where": "near landmarks", "behavior": rng.choice(["wander", "idle", "patrol"]), "purpose": c.get("role", "")} for c in brief.get("characters") or []],
        "audio_plan": {"ambience": "auto", "music_mood": brief.get("mood", "calm")},
        "ux_plan": {"accent": "#ffffff", "hud": ["crosshair", "minimap", "compass", "clock"]},
        "performance_notes": "orçamento do hardware aplicado automaticamente" if pt else "hardware budget applied automatically",
    }


def characters(inp: Dict[str, Any]) -> Dict[str, Any]:
    brief = inp.get("brief") or {}
    pt = str(brief.get("language", "pt")).startswith("pt")
    wb = (inp.get("worldbuilding") or {}).get("name") or ""
    setting = brief.get("setting") or brief.get("title") or ""
    detail = inp.get("detail") == "detailed"
    out = []
    for c in inp.get("need") or []:
        rng = _rng("char", c.get("name"), c.get("role"))
        name, role = c.get("name", "NPC"), c.get("role", "")
        pers = c.get("personality", "")
        if c.get("is_player"):
            prompt = (f"O jogador. Nome: {name}. Descrição: {c.get('description', 'aventureiro recém-chegado')}." if pt
                      else f"The player. Name: {name}. Description: {c.get('description', 'a newly arrived adventurer')}.")
        elif pt:
            prompt = (f"Você é {name}, {role} em {setting}. Personalidade: {pers}. "
                      "Fale sempre em primeira pessoa, de forma natural e curta (1 a 3 frases), no idioma do jogador. "
                      "Reaja ao que acontece ao redor, lembre-se do que o jogador disse e tenha seus próprios objetivos.")
            if detail:
                prompt += f" Você conhece bem o lugar{(' (' + wb + ')') if wb else ''} e seus moradores, e tem segredos que só conta a quem ganhar sua confiança."
        else:
            prompt = (f"You are {name}, {role} in {setting}. Personality: {pers}. "
                      "Always speak in first person, naturally and briefly (1-3 sentences), in the player's language. "
                      "React to what happens around you, remember what the player said and pursue your own goals.")
            if detail:
                prompt += f" You know the place{(' (' + wb + ')') if wb else ''} and its people well, and you keep secrets you only share with those who earn your trust."
        out.append({
            "id": c.get("id") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "npc",
            "name": name, "role": "player" if c.get("is_player") else "npc",
            "tags": [t for t in (role, brief.get("tone")) if t],
            "system_prompt": prompt,
            "greeting": ("Olá, viajante." if pt else "Hello, traveler.") if not c.get("is_player") else "",
            "voice": {"engine": "auto", "lang": "auto", "pitch": round(rng.uniform(0.8, 1.25), 2), "rate": round(rng.uniform(0.9, 1.1), 2)},
            "appearance": {
                "skin": rng.choice(SKIN), "hair": rng.choice(HAIR), "hair_style": rng.choice(["short", "long", "bun", "short"]),
                "top": rng.choice(CLOTH), "bottom": rng.choice(CLOTH), "height": round(rng.uniform(1.55, 1.9), 2),
                "build": round(rng.uniform(0.9, 1.15), 2), "accessory": rng.choice(["none", "none", "hat", "cape", "backpack"]),
            },
        })
    return {"characters": out}


STRUCT_RING = {
    "temperate": ["house", "house", "cabin", "barn", "house", "stall", "house"],
    "forest": ["cabin", "cabin", "tent", "cabin", "stone_circle"],
    "desert": ["tent", "tent", "ruin", "pillar", "tent", "ruin"],
    "snow": ["cabin", "cabin", "tent", "cabin", "stone_circle"],
    "tropical": ["cabin", "stall", "tent", "cabin", "stall"],
    "island": ["cabin", "tent", "crates", "cabin"],
    "urban": ["house", "house", "house", "stall", "house", "tower", "house"],
    "wasteland": ["ruin", "tent", "crates", "ruin", "tent", "ruin"],
    "swamp": ["cabin", "ruin", "cabin", "crates"],
    "mountain": ["cabin", "tower", "cabin", "stone_circle"],
}


UPDATE_KEYWORDS = [
    ("tower", ["torre", "tower"]), ("well", ["poço", "poco", "well"]), ("campfire", ["fogueira", "campfire", "bonfire"]),
    ("stall", ["barraca", "mercado", "market", "stall"]), ("tent", ["tenda", "tent"]), ("ruin", ["ruína", "ruina", "ruin"]),
    ("barn", ["celeiro", "barn"]), ("statue", ["estátua", "estatua", "statue"]), ("lamp", ["lampião", "poste", "lamp"]),
    ("bench", ["banco", "bench"]), ("fence", ["cerca", "fence"]), ("crates", ["caixas", "crates"]),
    ("stone_circle", ["círculo de pedras", "stone circle"]), ("pillar", ["pilar", "pillar"]),
    ("cabin", ["cabana", "cabin"]), ("house", ["casa", "house"]),
]
COMPASS = [("north", ["norte", "north"], (0, -1)), ("south", ["sul", "south"], (0, 1)),
           ("east", ["leste", "east"], (1, 0)), ("west", ["oeste", "west"], (-1, 0))]


def _apply_update(inp: Dict[str, Any], prev: Dict[str, Any]) -> Dict[str, Any]:
    """Modo Demo: mantém o mundo anterior e aplica pedidos simples (adicionar estruturas, hora, clima)."""
    brief, plan = inp.get("brief") or {}, inp.get("plan") or {}
    rng = _rng("update", brief.get("summary"), len(prev.get("structures", [])))
    world = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in prev.items()}
    t = f" {str(brief.get('summary', '')).lower()} "
    env = world.setdefault("environment", {})
    env["time_of_day"] = plan.get("time_of_day", env.get("time_of_day", 10))
    env["weather"] = plan.get("weather", env.get("weather", "clear"))
    direction = next(((dx, dz) for _n, words, (dx, dz) in COMPASS if any(w in t for w in words)), None)
    count = 1
    for ctype, words in UPDATE_KEYWORDS:
        if any(w in t for w in words):
            if direction:
                dx, dz = direction
                x, z = dx * 38 + rng.uniform(-8, 8), dz * 38 + rng.uniform(-8, 8)
            else:
                ang = rng.uniform(0, 6.28)
                x, z = math.cos(ang) * 34, math.sin(ang) * 34
            world.setdefault("structures", []).append(
                {"type": ctype, "x": round(x, 1), "z": round(z, 1), "rot": rng.uniform(0, 360), "scale": 1.1, "variant": rng.randint(0, 3), "label": ""})
            count += 1
    return world


def architect(inp: Dict[str, Any]) -> Dict[str, Any]:
    prev = inp.get("previous_world")
    if isinstance(prev, dict) and prev.get("structures"):
        return _apply_update(inp, prev)
    brief, plan = inp.get("brief") or {}, inp.get("plan") or {}
    chars = inp.get("characters") or []
    gen = inp.get("settings") or {}
    budget = inp.get("budget") or {}
    biome = plan.get("biome") or brief.get("biome") or "temperate"
    rng = _rng("architect", brief.get("title"), biome)
    size = {"small": 240, "medium": 420, "large": 760}.get(gen.get("size", "medium"), 420)
    size = min(size, int(budget.get("max_size", size)))
    structures: List[Dict[str, Any]] = []
    # centro
    structures.append({"type": "campfire" if biome != "urban" else "lamp", "x": 0, "z": -4, "label": ""})
    for lm in plan.get("landmarks") or []:
        d = rng.uniform(14, min(60, size * 0.22))
        ang = {"center": rng.uniform(0, 6.28), "north": -1.57, "east": 0, "south": 1.57, "west": 3.14}.get(lm.get("where"), rng.uniform(0, 6.28)) + rng.uniform(-0.4, 0.4)
        structures.append({"type": lm.get("type", "house"), "x": round(math.cos(ang) * d, 1), "z": round(math.sin(ang) * d, 1),
                           "rot": rng.uniform(0, 360), "label": lm.get("label", ""), "scale": round(rng.uniform(0.9, 1.3), 2)})
    ring = STRUCT_RING.get(biome, STRUCT_RING["temperate"])
    n = 8 if gen.get("size") != "large" else 14
    r = max(24, min(size * 0.16, 42))
    for i in range(n):
        ang = (i / n) * math.pi * 2 + rng.uniform(-0.2, 0.2)
        rr = r + rng.uniform(-6, 14)
        x, z = math.cos(ang) * rr, math.sin(ang) * rr
        structures.append({"type": ring[i % len(ring)], "x": round(x, 1), "z": round(z, 1),
                           "rot": round(math.degrees(ang) + 90 + rng.uniform(-15, 15)), "scale": round(rng.uniform(0.9, 1.25), 2), "variant": rng.randint(0, 3)})
        if i % 2 == 0 and biome not in ("desert", "wasteland"):
            structures.append({"type": "lamp", "x": round(x * 0.78, 1), "z": round(z * 0.78, 1)})
    for i in range(6):
        ang, d = rng.uniform(0, 6.28), rng.uniform(r * 0.4, r * 1.4)
        structures.append({"type": rng.choice(["fence", "bench", "crates", "sign"]), "x": round(math.cos(ang) * d, 1), "z": round(math.sin(ang) * d, 1), "rot": rng.uniform(0, 360)})
    npcs = []
    anchors = [s for s in structures if s["type"] in ("campfire", "well", "stall", "house", "cabin", "tent", "tower", "ruin", "lamp")]
    for i, c in enumerate([c for c in chars if c.get("role") != "player"]):
        a = anchors[(i * 2 + 1) % len(anchors)]
        npcs.append({"id": c["id"], "char": c["id"], "x": round(a["x"] + rng.uniform(-3.5, 3.5), 1), "z": round(a["z"] + rng.uniform(3, 6), 1),
                     "behavior": rng.choice(["wander", "idle", "wander", "patrol"]), "radius": round(rng.uniform(5, 14), 1),
                     "patrol": [[round(a["x"] + rng.uniform(-8, 8), 1), round(a["z"] + rng.uniform(-8, 8), 1)] for _ in range(3)]})
    player_char = next((c["id"] for c in chars if c.get("role") == "player"), "")
    return {
        "title": brief.get("title", ""), "description": brief.get("summary", ""), "language": brief.get("language", "pt-BR"),
        "perspective": gen.get("perspective", "third"), "realism": gen.get("realism", 0.7),
        "environment": {"biome": biome, "size": size, "time_of_day": plan.get("time_of_day", 10), "weather": plan.get("weather", "clear"),
                        "day_cycle": gen.get("day_cycle", True)},
        "structures": structures, "npcs": npcs,
        "player": {"char": player_char, "x": 0, "z": 12, "yaw": 180},
        "gameplay": {"npc_autonomy": gen.get("npc_autonomy", "off"), "interaction_distance": 3.8, "rules": ""},
    }


def sound_ux(inp: Dict[str, Any]) -> Dict[str, Any]:
    brief = inp.get("brief") or {}
    pt = str(brief.get("language", "pt")).startswith("pt")
    mood = brief.get("mood", "calm")
    scale = {"calm": "pentatonic", "tense": "phrygian", "mysterious": "dorian", "epic": "minor", "melancholic": "minor", "joyful": "major"}.get(mood, "minor")
    tempo = {"calm": 62, "tense": 80, "mysterious": 66, "epic": 104, "melancholic": 56, "joyful": 112}.get(mood, 70)
    return {
        "audio": {"ambience": "auto", "ambience_volume": 0.5, "footsteps": True,
                  "music": {"enabled": True, "mood": mood, "tempo": tempo, "root": "D", "scale": scale, "volume": 0.3}},
        "ux": {"theme": {"bg": "#000000", "text": "#ececec", "accent": "#ffffff"},
               "hud": {"crosshair": True, "minimap": True, "compass": True, "clock": True, "hints": True},
               "intro": f"{brief.get('title', '')}" + (" — explore, converse e descubra." if pt else " — explore, talk and discover.")},
    }


def reviewer(inp: Dict[str, Any]) -> Dict[str, Any]:
    return {"approved": True, "score": 7, "issues": [], "summary": "Revisão automática (modo Demo): sem problemas estruturais encontrados."}


# --------------------------------------------------------------------------- conversa de NPC (Demo)

GREET = {
    "pt": ["Olá, viajante! Em que posso ajudar?", "Ah, olá! Não é sempre que vejo alguém por aqui.", "Bem-vindo! Fique à vontade."],
    "en": ["Hello, traveler! How can I help?", "Oh, hello! Not every day I see someone new around here.", "Welcome! Make yourself at home."],
    "es": ["¡Hola, viajero! ¿En qué puedo ayudarte?", "¡Bienvenido! Siéntete como en casa."],
}
GENERIC = {
    "pt": ["Hmm, interessante... conte-me mais.", "Por aqui as coisas andam assim: um dia de cada vez.", "Não sei se entendi tudo, mas gosto de conversar com você.", "Cuidado por aí. Nem tudo é o que parece."],
    "en": ["Hmm, interesting... tell me more.", "Around here we take things one day at a time.", "I'm not sure I got all of that, but I like talking with you.", "Be careful out there. Not everything is as it seems."],
    "es": ["Hmm, interesante... cuéntame más.", "Por aquí vamos día a día.", "Ten cuidado por ahí."],
}


def npc_reply(system: str, user_text: str) -> str:
    lang = detect_lang(user_text)
    lang = lang if lang in GREET else "en"
    t = f" {user_text.lower()} "
    m = re.search(r"^# You are (.+?)\.?$", system, re.M)
    name = (m.group(1).split(",")[0] if m else "").strip()
    rng = _rng("npc", name, user_text)
    weather = (re.search(r"Weather:\s*(\w+)", system) or [None, ""])[1]

    def has(*words: str) -> bool:
        return any(w in t for w in words)

    if has(" siga", " seguir", " segue", " venha comigo", "follow", "come with me", " sígueme", " seguir", "ven conmigo"):
        return {"pt": "Claro, vou com você. [[action:follow]]", "en": "Sure, I'll come with you. [[action:follow]]", "es": "Claro, voy contigo. [[action:follow]]"}[lang]
    if has(" fique", " espere", " aguarde", "stay here", " wait", " quédate", " espera"):
        return {"pt": "Certo, fico por aqui. [[action:stay]]", "en": "All right, I'll stay right here. [[action:stay]]", "es": "Está bien, me quedo aquí. [[action:stay]]"}[lang]
    if has(" dança", " dance", " baila"):
        return {"pt": "Hah! Vamos lá! [[action:dance]]", "en": "Ha! Here goes! [[action:dance]]", "es": "¡Ja! ¡Vamos! [[action:dance]]"}[lang]
    if has(" tchau", " adeus", "goodbye", " bye", " adiós", "até logo", "see you"):
        return {"pt": "Até logo! Volte quando quiser. [[action:wave]]", "en": "See you later! Come back anytime. [[action:wave]]", "es": "¡Hasta luego! [[action:wave]]"}[lang]
    if has(" quem é você", "quem é voce", "who are you", " seu nome", "your name", " quién eres", " cómo te llamas"):
        role = (re.search(r"Role:\s*(.+)", system) or [None, ""])[1].strip()
        return {"pt": f"Eu sou {name}{', ' + role if role else ''}. E você?", "en": f"I'm {name}{', ' + role if role else ''}. And you?", "es": f"Soy {name}{', ' + role if role else ''}. ¿Y tú?"}[lang]
    if has(" obrigad", " thanks", " thank you", " gracias"):
        return {"pt": "Por nada! Fico feliz em ajudar.", "en": "You're welcome! Happy to help.", "es": "¡De nada!"}[lang]
    if has(" oi ", " olá", " ola ", "hello", " hi ", " hey", " hola", "bom dia", "boa noite", "boa tarde", "good morning"):
        return rng.choice(GREET[lang])
    if weather and weather != "clear" and has("tempo", "clima", "weather", "chuva", "rain"):
        return {"pt": f"O clima anda assim ({weather}). Melhor se agasalhar.", "en": f"The weather's been like this ({weather}). Better dress warm.", "es": f"El clima está así ({weather})."}[lang]
    return rng.choice(GENERIC[lang])


def assistant_reply(user_text: str) -> str:
    """Resposta do Chat geral no modo Demo (sem IA): honesta — o Demo não sabe responder perguntas, mas diz como ligar uma IA e o que ainda dá para fazer."""
    lang = detect_lang(user_text or "")
    if lang == "pt":
        return ("Estou no **modo Demo** (sem IA), então não consigo responder de verdade a perguntas como a sua.\n\n"
                "Para conversar com uma IA — nuvem (Claude, ChatGPT, Gemini…), o LM Studio ou um modelo local — escolha um modelo no botão **Modelo** ao lado do Run.\n\n"
                "Mesmo no Demo você pode **criar** mundos 3D, avatares, jogos 2D e canvases: ative uma ferramenta no botão ✦ da caixa de texto e aperte Run.")
    return ("I'm in **Demo mode** (no AI), so I can't really answer questions like yours.\n\n"
            "To chat with an AI — cloud (Claude, ChatGPT, Gemini…), LM Studio or a local model — pick a model with the **Model** button next to Run.\n\n"
            "Even in Demo you can **create** 3D worlds, avatars, 2D games and canvases: turn on a tool with the ✦ button in the message box and press Run.")
