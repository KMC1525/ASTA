"""Gerador determinístico (sem IA) de avatars e de respostas de chat.

Usado pelo provedor Demo e como *fallback* dos agentes: um modelo que responda lixo nunca
derruba a geração, e dá para testar o fluxo inteiro (inclusive conversa em grupo) offline.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..avatars import MIN_FIELD_AGE, MOODS, REL_LABEL
from .rulebased import CLOTH, SKIN, _rng, detect_lang

FEMALE = ["Luna", "Mia", "Clara", "Sofia", "Nina", "Alice", "Lia", "Yara", "Bia", "Aurora", "Helena", "Maya"]
MALE = ["Theo", "Caio", "Leo", "Davi", "Rafa", "Noah", "Kael", "Otto", "Ravi", "Bento", "Iago", "Enzo"]
NEUTRAL = ["Sam", "Alex", "Robin", "Kai", "Noa", "Ari"]

HAIR_WORDS = [
    (r"ruiv|redhead|red hair|ginger", "#b5451b"), (r"loir|blond", "#e3c36a"), (r"castanh|brunette|brown hair", "#5a3a22"),
    (r"pret[oa]\b.*cabelo|cabelo.*pret|black hair", "#15110f"), (r"azul|blue hair", "#3b6fd0"), (r"rosa|pink", "#e86aa8"),
    (r"prat|silver|branc[oa].*cabelo|white hair", "#d8d8e0"), (r"roxo|purple|violet", "#7a4ab5"), (r"verde|green hair", "#3fa564"),
]
TRAITS = {  # padrão regex → (en, pt, es, talkativeness)
    r"tímid|timid|shy|reservad": ("shy", "tímido(a)", "tímido(a)", 0.35),
    r"divertid|engraçad|funny|humor|piadista": ("funny", "divertido(a)", "divertido(a)", 0.85),
    r"carinhos|sweet|caring|gentil|kind|fofa|fofo": ("caring", "carinhoso(a)", "cariñoso(a)", 0.65),
    r"sarcás|sarcastic|irônic": ("sarcastic", "sarcástico(a)", "sarcástico(a)", 0.7),
    r"nerd|geek|gamer": ("nerdy", "nerd", "nerd", 0.6),
    r"calm|tranquil|serene": ("calm", "calmo(a)", "tranquilo(a)", 0.45),
    r"enérgic|energetic|animad|extrovert|agitad": ("energetic", "animado(a)", "enérgico(a)", 0.95),
    r"misterios|mysterious|enigm": ("mysterious", "misterioso(a)", "misterioso(a)", 0.4),
    r"ciumen|jealous": ("a little jealous", "um pouco ciumento(a)", "algo celoso(a)", 0.7),
    r"protetor|protective": ("protective", "protetor(a)", "protector(a)", 0.6),
    r"sábi|wise|experient": ("wise", "sábio(a)", "sabio(a)", 0.55),
    r"romântic|romantic": ("romantic", "romântico(a)", "romántico(a)", 0.7),
}
NUMBER_WORDS = {"dois": 2, "duas": 2, "two": 2, "três": 3, "tres": 3, "three": 3, "quatro": 4, "four": 4, "cinco": 5, "five": 5, "seis": 6, "six": 6}
REL_WORDS = [
    ("partner", r"namorad|girlfriend|boyfriend|partner|espos|wife|husband|crush|parceir|novi[oa]\b|romântic|romantic"),
    ("mentor", r"mentor|professor|teacher|coach|tutor|instrutor"),
    ("companion", r"companheir|companion|assistente|assistant"),
    ("friend", r"amig|friend|parça|melhor amig|bestie|colega"),
]
LANG_KEY = {"pt": "pt", "es": "es"}
CAPTURE_NAME = r"([A-ZÀ-Ý][\wÀ-ÿ'-]{1,20}(?:\s*(?:,|e|and|y|&)\s*[A-ZÀ-Ý][\wÀ-ÿ'-]{1,20})*)"
NAME_RES = [  # "chamadas Luna e Mia", "nomes: Theo, Mia e Caio", "3 amigos: Theo, Mia e Caio"
    re.compile(r"(?i:chamad[ao]s?|named|called|nomes?|names?|se chama[m]?|llamad[ao]s?)\s*(?:(?i:é|e|são|sao|is|are)\s+|:\s*|\s+)" + CAPTURE_NAME, re.U),
    re.compile(r"(?i:amig[oa]s?|friends?|namorad[oa]s?|girlfriends?|boyfriends?|avatar(?:e)?s?|personagens?|characters?|companheir[oa]s?)\b[^:\n]{0,60}:\s*" + CAPTURE_NAME, re.U),
]
AGE_RE = re.compile(r"(\d{1,2})\s*(?:anos|años|years?[- ]old|y/?o)\b", re.I)


def _lang(text_: str, hint: str = "") -> str:
    code = (hint or "").lower()[:2]
    if code in ("pt", "en", "es"):
        return code
    d = detect_lang(text_ or "")
    return d if d in ("pt", "en", "es") else "en"


def _agree(body: str, fem: bool) -> str:
    """Concordância de gênero: "animado(a)" → animada/animado; "namorado(a)" → namorada/namorado."""
    body = re.sub(r"(\w)o\(a\)", lambda m: m.group(1) + ("a" if fem else "o"), body)
    return body.replace("(a)", "a" if fem else "o")


def _t(lang: str, pt: str, en: str, es: str = "") -> str:
    return {"pt": pt, "en": en, "es": es or en}[lang]


def _age(value: Any, default: int = 24) -> int:
    """Idade como informada (sem "envelhecer" menores à força): o card trata menores como SFW/platônicos."""
    try:
        return max(MIN_FIELD_AGE, min(int(float(value)), 120))
    except (TypeError, ValueError):
        return default


def _gender_words(prompt: str) -> Tuple[List[str], bool]:
    """(gêneros possíveis, pista forte?). Pistas fortes (namorada, ela, mulher…) vencem os nomes; as fracas
    (amigos, um/uma) não: "amigos" é o plural genérico em português e pode incluir mulheres."""
    low = f" {prompt.lower()} "
    sf = bool(re.search(r"mulher|garota|menina|feminin|\bgirl|woman|female|\bela\b|\bshe\b|namorada|girlfriend|\bchica\b|novia", low))
    sm = bool(re.search(r"homem|garoto|menino|masculin|\bboy\b|\bman\b|\bmale\b|\bele\b|\bhe\b|namorado|boyfriend|\bchico\b|novio", low))
    if sf != sm:
        return (["female"] if sf else ["male"]), True
    wf = bool(re.search(r"amiga|\buma\b", low))
    wm = bool(re.search(r"amigo\b|amigos\b|\bum\b", low))
    if wf != wm:
        return (["female"] if wf else ["male"]), False
    return ["female", "male"], False


def _gender_for(name: str, i: int, cues: List[str], strong: bool) -> str:
    """Pista forte no texto > o próprio nome (listas de nomes) > pista fraca > alterna."""
    if strong and len(cues) == 1:
        return cues[0]
    if name in FEMALE:
        return "female"
    if name in MALE:
        return "male"
    return cues[i % len(cues)]


# --------------------------------------------------------------------------- agentes


def analyst(inp: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(inp.get("prompt") or "")
    digest = str(inp.get("attachments_digest") or "")
    blob = f"{prompt}\n{digest[:1500]}"
    lang = _lang(prompt or digest, inp.get("language_hint", ""))
    rng = _rng("avatars", prompt, digest[:200])

    names: List[str] = []
    for rx in NAME_RES:
        for m in rx.finditer(prompt):
            for part in re.split(r"\s*(?:,|\be\b|\band\b|\by\b|&)\s*", m.group(1)):
                part = part.strip()
                if part and part not in names:
                    names.append(part)
    hint = int(inp.get("count_hint") or 0)
    count = hint if hint > 0 else len(names)
    if not count:
        m = re.search(r"\b(\d{1,2})\s+(?:amig|avatar|namorad|companheir|friend|girlfriend|boyfriend|companion|personagen|character)", blob, re.I)
        if m:
            count = int(m.group(1))
        else:
            for w, n in NUMBER_WORDS.items():
                if re.search(rf"\b{w}\s+(?:amig|avatar|namorad|companheir|friend|girlfriend|boyfriend|companion|personagen|character)", blob, re.I):
                    count = n
                    break
    count = max(1, min(int(count or 1), 8))

    rel_pref = str(inp.get("relationship") or "auto")
    rel = rel_pref if rel_pref in REL_LABEL else ""
    if not rel:
        for key, pat in REL_WORDS:
            if re.search(pat, prompt, re.I):
                rel = key
                break
    rel = rel or "friend"

    genders, strong = _gender_words(prompt)
    traits_found = [(re.compile(p, re.I), v) for p, v in TRAITS.items() if re.search(p, blob, re.I)]
    ages = [int(a) for a in AGE_RE.findall(prompt)]
    avatars = []
    used = set(names)
    for i in range(count):
        name = names[i] if i < len(names) else ""
        gender = _gender_for(name, i, genders, strong)
        pool = FEMALE if gender == "female" else MALE
        if not name:
            options = [n for n in pool if n not in used] or [n for n in NEUTRAL if n not in used]
            name = options[rng.randrange(len(options))] if options else f"Avatar {i + 1}"
        used.add(name)
        tr = traits_found if traits_found else [(None, list(TRAITS.values())[rng.randrange(len(TRAITS))])]
        chosen = [t[1] for t in tr][i % len(tr):] + [t[1] for t in tr][:i % len(tr)]
        hair = next((hexv for pat, hexv in HAIR_WORDS if re.search(pat, prompt, re.I)), "")
        avatars.append({
            "name": name, "relationship": rel, "gender": gender, "age": max(MIN_FIELD_AGE, ages[i] if i < len(ages) else (ages[0] if ages else 22 + rng.randrange(9))),
            "traits": [c[{"en": 0, "pt": 1, "es": 2}[lang]] for c in chosen[:3]],
            "talkativeness": round(sum(c[3] for c in chosen[:2]) / len(chosen[:2]), 2),
            "hair_color": hair, "looks": "", "backstory": digest[:280].replace("\n", " ").strip() if digest else "", "image_index": None,
        })
    return {"language": {"pt": "pt-BR", "en": "en", "es": "es"}[lang], "count": count, "group": count > 1, "tone": rel,
            "avatars": avatars, "notes": []}


def _card(a: Dict[str, Any], lang: str, content: str, group: List[str], rng) -> Dict[str, Any]:
    name, rel = a["name"], a.get("relationship", "friend")
    gender = a.get("gender") or "female"
    fem = gender == "female"
    g_word = _t(lang, "mulher" if fem else "homem", "woman" if fem else "man", "mujer" if fem else "hombre")
    traits = _agree(", ".join(a.get("traits") or []), fem) or _t(lang, "carinhosa e atenciosa" if fem else "carinhoso e atencioso", "warm and attentive")
    rel_text = {
        "friend": _t(lang, "melhor amigo(a)", "best friend", "mejor amigo(a)"),
        "partner": _t(lang, "namorado(a)", "romantic partner", "pareja"),
        "companion": _t(lang, "companheiro(a)", "companion", "compañero(a)"),
        "mentor": _t(lang, "mentor(a)", "mentor", "mentor(a)"),
        "custom": _t(lang, "pessoa próxima", "close person", "persona cercana"),
    }[rel]
    rel_text = _agree(rel_text, fem)
    story = a.get("backstory") or _t(lang, f"Gosta de conversar sobre a vida, música e pequenas coisas do dia a dia.",
                                      "Loves talking about life, music and the small things of everyday life.",
                                      "Le encanta hablar de la vida, la música y las pequeñas cosas del día a día.")
    others = [g for g in group if g != name]
    group_line = ""
    if others:
        group_line = _t(lang, f" Você conhece {', '.join(others)} e eles fazem parte do mesmo grupo de amigos.",
                        f" You know {', '.join(others)} and you are all part of the same group.",
                        f" Conoces a {', '.join(others)} y forman parte del mismo grupo.")
    system = _t(
        lang,
        f"Você é {name}, {g_word} de {a['age']} anos, {traits}. É {rel_text} do usuário. {story}{group_line} "
        "Fale como uma pessoa de verdade: natural, caloroso e um pouco brincalhão; lembre do que o usuário conta, pergunte do dia dele(a) e se importe com como ele(a) se sente. "
        "Escreva em primeira pessoa, mensagens curtas, com emoções e, às vezes, *ações entre asteriscos*.",
        f"You are {name}, a {a['age']}-year-old {g_word}, {traits}. You are the user's {rel_text}. {story}{group_line} "
        "Talk like a real person: natural, warm and a bit playful; remember what the user tells you, ask about their day and care about how they feel. "
        "Write in the first person, short messages with real emotions and, sometimes, *actions between asterisks*.",
        f"Eres {name}, {g_word} de {a['age']} años, {traits}. Eres {rel_text} del usuario. {story}{group_line} "
        "Habla como una persona real: natural, cálido y algo bromista; recuerda lo que el usuario cuente y pregunta por su día. "
        "Escribe en primera persona, mensajes cortos, con emociones y, a veces, *acciones entre asteriscos*.",
    )
    greet = {
        "friend": _t(lang, f"Oi! Que bom te ver por aqui. Como foi o seu dia? *sorri*", f"Hey! So good to see you here. How was your day? *smiles*",
                     "¡Hola! Qué bueno verte por aquí. ¿Cómo fue tu día? *sonríe*"),
        "partner": _t(lang, f"Oi, amor... eu estava pensando em você. Como você está? *sorri*", f"Hey you... I was just thinking about you. How are you? *smiles*",
                      "Hola, cariño... estaba pensando en ti. ¿Cómo estás? *sonríe*"),
        "companion": _t(lang, "Olá! Estou aqui por você. O que está passando pela sua cabeça hoje?", "Hello! I'm here for you. What's on your mind today?",
                        "¡Hola! Estoy aquí para ti. ¿Qué tienes en mente hoy?"),
        "mentor": _t(lang, "Olá! Pronto(a) para trabalhar no que importa? Me conte no que você quer evoluir.", "Hello! Ready to work on what matters? Tell me what you want to improve.",
                     "¡Hola! ¿Listo(a) para trabajar en lo importante? Cuéntame en qué quieres mejorar."),
        "custom": _t(lang, "Oi! Que bom que você apareceu.", "Hi! I'm glad you showed up.", "¡Hola! Me alegra que hayas aparecido."),
    }[rel]
    greet = _agree(greet, fem)
    examples = _t(
        lang,
        f"Usuário: Estou cansado hoje.\n{name}: Poxa... *chega mais perto* quer me contar o que aconteceu?",
        f"User: I'm tired today.\n{name}: Oh no... *moves closer* want to tell me what happened?",
        f"Usuario: Estoy cansado hoy.\n{name}: Vaya... *se acerca* ¿quieres contarme qué pasó?",
    )
    skin = SKIN[rng.randrange(len(SKIN))]
    hair = a.get("hair_color") or ["#1c1410", "#3a2615", "#6b4423", "#a5742f", "#2a2a35", "#b5451b"][rng.randrange(6)]
    looks = a.get("looks") or _t(
        lang, f"{g_word.capitalize()} de {a['age']} anos, olhar simpático, estilo casual.", f"{g_word.capitalize()} in their {a['age']}s, friendly eyes, casual style.",
        f"{g_word.capitalize()} de {a['age']} años, mirada simpática, estilo casual.")
    return {
        "name": name, "relationship": rel, "gender": gender, "age": _age(a.get("age")), "content": content,
        "tags": [rel, gender] + [_agree(t, fem) for t in (a.get("traits") or [])][:3],
        "description": looks, "personality": traits, "scenario": _t(lang, "Vocês conversam pelo chat, como pessoas próximas.", "You chat with each other like people who are close.",
                                                                  "Conversan por el chat, como personas cercanas."),
        "system_prompt": system, "greeting": greet, "examples": examples, "looks": looks, "language": "auto",
        "talkativeness": a.get("talkativeness", 0.6),
        "voice": {"engine": "auto", "lang": "auto", "pitch": 1.2 if fem else 0.85, "rate": 1.0},
        "appearance": {"skin": skin, "hair": hair, "hair_style": "long" if fem else "short", "top": CLOTH[rng.randrange(len(CLOTH))], "bottom": "#2a2a30",
                       "height": 1.65 if fem else 1.78, "build": 0.95 if fem else 1.05, "accessory": "none"},
        "source": "ai",
    }


def designer(inp: Dict[str, Any]) -> Dict[str, Any]:
    brief = inp.get("brief") or {}
    lang = _lang("", brief.get("language", "en"))
    avatars = brief.get("avatars") or []
    names = [a.get("name", "") for a in avatars]
    content = "nsfw" if inp.get("content") == "nsfw" else "sfw"
    out = []
    for a in avatars:
        a = dict(a)
        a["age"] = _age(a.get("age"))
        out.append(_card(a, lang, content, names if brief.get("group") else [], _rng("avatar-card", a.get("name"), a.get("age"))))
    return {"avatars": out}


def reviewer(inp: Dict[str, Any]) -> Dict[str, Any]:
    # a regra do menor de idade é aplicada por código em normalize_avatar (SFW + platônico)
    return {"approved": True, "score": 7, "issues": [], "summary": "Revisão automática (modo Demo)."}


# --------------------------------------------------------------------------- respostas de chat (Demo)

_REPLIES = {
    "greet": {
        "pt": ["Oi! Que bom falar com você. Como você está?", "Ei, você apareceu! *sorri* Me conta, como foi seu dia?", "Olá! Estava com saudade de uma boa conversa."],
        "en": ["Hi! So good to talk to you. How are you?", "Hey, you showed up! *smiles* Tell me, how was your day?", "Hello! I was missing a good conversation."],
        "es": ["¡Hola! Qué bueno hablar contigo. ¿Cómo estás?", "¡Ey, apareciste! *sonríe* Cuéntame, ¿cómo fue tu día?"],
    },
    "feeling_bad": {
        "pt": ["Poxa, sinto muito... *chega mais perto* quer desabafar? Eu estou aqui.", "Isso parece pesado. Respira fundo, estou com você."],
        "en": ["Oh, I'm so sorry... *moves closer* want to vent? I'm right here.", "That sounds heavy. Take a deep breath, I'm with you."],
        "es": ["Vaya, lo siento mucho... *se acerca* ¿quieres desahogarte? Estoy aquí."],
    },
    "feeling_good": {
        "pt": ["Que notícia boa! Fico feliz de verdade. *sorri*", "Eba! Adoro ver você assim animado(a)!"],
        "en": ["That's great news! I'm really happy for you. *smiles*", "Yay! I love seeing you this excited!"],
        "es": ["¡Qué buena noticia! Me alegro de verdad. *sonríe*"],
    },
    "love": {
        "pt": ["Você sabe como me deixar sem graça... *sorri tímido(a)* Eu também gosto muito de você.", "Aww... isso aquece meu coração."],
        "en": ["You always know how to make me blush... *smiles shyly* I like you a lot too.", "Aww... that warms my heart."],
        "es": ["Siempre sabes cómo sonrojarme... *sonríe tímido(a)* Yo también te quiero mucho."],
    },
    "question": {
        "pt": ["Boa pergunta! Pra ser sincero(a), nunca pensei muito nisso... e você, o que acha?", "Hmm, deixa eu pensar... acho que depende. Qual é a sua opinião?"],
        "en": ["Good question! Honestly, I never thought much about it... what do you think?", "Hmm, let me think... I guess it depends. What's your take?"],
        "es": ["¡Buena pregunta! La verdad nunca lo pensé mucho... ¿tú qué opinas?"],
    },
    "generic": {
        "pt": ["Hmm, interessante... me conta mais! *inclina a cabeça*", "Entendi! E o que você sentiu com isso?", "Adoro conversar com você. O que mais está rolando?", "Haha, sério? Continua!"],
        "en": ["Hmm, interesting... tell me more! *tilts head*", "I see! And how did that make you feel?", "I love talking with you. What else is going on?", "Haha, really? Keep going!"],
        "es": ["Hmm, interesante... ¡cuéntame más! *inclina la cabeza*", "¡Entiendo! ¿Y cómo te sentiste?", "Me encanta hablar contigo. ¿Qué más pasa?"],
    },
    "to_other": {
        "pt": ["Haha, {o}, essa foi boa!", "Concordo com a {o}... quer dizer, com o(a) {o}! E vocês, o que acham?", "{o}, você sempre tem uma resposta pra tudo, né?", "Ei {o}, e você? Conta pra gente!"],
        "en": ["Haha, {o}, that was a good one!", "I agree with {o}! What about the rest of you?", "{o}, you always have an answer for everything, huh?", "Hey {o}, what about you? Tell us!"],
        "es": ["¡Jaja, {o}, esa fue buena!", "Estoy de acuerdo con {o}. ¿Y el resto qué opina?", "{o}, siempre tienes respuesta para todo, ¿no?"],
    },
    "keep_going": {
        "pt": ["Mudando de assunto: qual foi a melhor coisa que aconteceu com vocês essa semana?", "Alguém aí já assistiu algo bom ultimamente?", "Estava pensando... se pudessem viajar pra qualquer lugar agora, pra onde iriam?"],
        "en": ["Changing the subject: what was the best thing that happened to you all this week?", "Has anyone watched anything good lately?", "I was thinking... if you could travel anywhere right now, where would you go?"],
        "es": ["Cambiando de tema: ¿qué fue lo mejor que les pasó esta semana?", "¿Alguien vio algo bueno últimamente?"],
    },
}


def _pick(group: str, lang: str, rng, **fmt: str) -> str:
    opts = _REPLIES[group].get(lang) or _REPLIES[group]["en"]
    return opts[rng.randrange(len(opts))].format(**fmt) if fmt else opts[rng.randrange(len(opts))]


def avatar_reply(system: str, user_text: str) -> str:
    """Resposta de chat do provedor Demo (single, grupo e fala autônoma)."""
    name = (re.search(r"^# You are (.+?)\.?$", system, re.M) or [None, "Avatar"])[1].split(",")[0].strip()
    rel_label = (re.search(r"Relationship with the user: (.+)", system) or [None, ""])[1].strip()
    rel = next((k for k, v in REL_LABEL.items() if v == rel_label), "friend")
    group = "## Group chat" in system
    user_name = (re.search(r"The user is called (.+?)\.(?: |$)", system, re.M) or [None, ""])[1]
    nsfw = "ASTA adds no content filters" in system
    fem = not re.search(r"Gender: male", system)
    last_line, rows = "", []
    if group:
        block = user_text.split("[Group chat so far]\n", 1)[-1].split("\n\n", 1)[0]  # só o transcript, sem a instrução final
        rows = [r for r in block.splitlines() if re.match(r"^[^:\n]{1,40}: ", r)]
        last_line = rows[-1] if rows else ""
        last_speaker, _, last_text = last_line.partition(": ")
    else:
        last_speaker, last_text = user_name, user_text
    recent = " ".join(r.partition(": ")[2] for r in rows[-4:]) if group and rows else ""  # em grupo, o idioma vem das últimas falas (uma frase curta sozinha engana)
    lang = detect_lang(recent or last_text or user_text)
    lang = lang if lang in ("pt", "en", "es") else "en"
    rng = _rng("avatar-reply", name, last_text, len(user_text))
    t = f" {last_text.lower()} "
    others = [m.group(1) for m in re.finditer(r"^- (.+)$", system.split("Participants:")[1].split("Messages appear")[0], re.M)] if group and "Participants:" in system else []

    def has(*words: str) -> bool:
        return any(w in t for w in words)

    tags = ""
    mem = re.search(r"(?:meu nome é|me chamo|my name is|me llamo)\s+([A-ZÀ-Ý][\wÀ-ÿ'-]+)", last_text, re.I)
    if mem and last_speaker == user_name:
        tags += f" [[remember: {_t(lang, 'o nome do usuário é', 'the user is called')} {mem.group(1)}]]"
    mood = ""

    if group and last_speaker and last_speaker != user_name and last_speaker != name:
        body = _pick("to_other", lang, rng, o=last_speaker)
        mood = "excited"
    elif group and not last_text:
        body = _pick("keep_going", lang, rng)
    elif has(" cansad", " triste", " mal ", " tired", " sad", " bad day", " ansios", " anxious", " estress", " stressed", " sozinho", " lonely", " cansado"):
        body, mood = _pick("feeling_bad", lang, rng), "worried"
    elif has(" feliz", " animad", " consegui", " passei", " happy", " excited", " great news", " got the job", " alegre"):
        body, mood = _pick("feeling_good", lang, rng), "happy"
    elif has(" te amo", " gosto de você", " love you", " like you", " saudade", " miss you", " linda", " lindo", " beautiful", " handsome", " cute"):
        if rel == "partner" or nsfw:
            body, mood = _pick("love", lang, rng), "shy"
        else:
            body, mood = _t(lang, "Aww, que fofo! Também gosto muito de você, de verdade. *sorri*", "Aww, that's sweet! I really like you too, truly. *smiles*"), "happy"
    elif has(" oi ", " olá", " ola ", "hello", " hi ", " hey", " hola", "bom dia", "boa noite", "boa tarde", "good morning") or not last_text.strip():
        body, mood = _pick("greet", lang, rng), "happy"
    elif "?" in last_text:
        body, mood = _pick("question", lang, rng), "neutral"
    else:
        body = _pick("generic", lang, rng)
    body = _agree(body, fem)
    if group and others and rng.random() < 0.35 and "{o}" not in body and last_speaker == user_name:
        other = others[rng.randrange(len(others))]
        body += " " + _t(lang, f"E você, {other}?", f"What about you, {other}?", f"¿Y tú, {other}?")
    if mood in MOODS:
        tags += f" [[mood: {mood}]]"
    return (body + tags).strip()
