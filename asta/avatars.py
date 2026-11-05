"""Avatars: companheiros de conversa por texto e voz (amigo, namorado(a), mentor…).

Inspirado em plataformas como Janitor e SillyTavern: cada avatar é um card JSON simples,
fácil de editar à mão, exportar e compartilhar (importa/exporta Character Card V2).

Regra fixa (vale também no modo NSFW): conteúdo sexual envolvendo menores não existe no ASTA.
  * avatars são adultos (18+) por padrão;
  * se a idade informada ou algum texto do card descreve um menor, o avatar NUNCA é "rejuvenescido/envelhecido"
    de mentira: ele continua menor e fica estritamente SFW, platônico (vira "amigo", nunca parceiro(a)).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .cards import _tags, normalize_appearance, normalize_voice, png_card_data
from .util import num, text

AVATAR_SCHEMA = "asta.avatar.v1"
CHAT_SCHEMA = "asta.avatar_chat.v1"
RELATIONSHIPS = ("friend", "partner", "companion", "mentor", "custom")
CONTENT_MODES = ("sfw", "nsfw")
MIN_AGE = 18  # maioridade
MIN_FIELD_AGE = 5  # menor valor aceito no campo (o card não é "envelhecido" à força)
MAX_CHAT_AVATARS = 8
MAX_STORED_MESSAGES = 500
MOODS = ("neutral", "happy", "sad", "angry", "shy", "excited", "surprised", "flirty", "sleepy", "worried")

_PORTRAIT_RE = re.compile(r"^[\w][\w.-]{0,120}$")

# --------------------------------------------------------------------------- regra do menor de idade

_MINOR_AGE_RES = [
    re.compile(r"\b(\d{1,2})[\s-]*(?:years?|yrs?)[\s-]*old\b", re.I),
    re.compile(r"\b(\d{1,2})\s*y/?o\b", re.I),
    re.compile(r"\b(?:age|aged|idade|edad)\s*[:=]?\s*(\d{1,2})\b", re.I),
    re.compile(r"\b(?:tem|tinha|has|had|tiene|tenía)\s+(\d{1,2})\s+(?:anos|años)\b(?!\s+de\s+(?!idade|edad))", re.I),
    re.compile(r"\b(\d{1,2})\s*(?:anos|años)\s+de\s+(?:idade|edad)\b", re.I),
]
_MINOR_WORDS = re.compile(
    r"\b(?:underage|under-age|a minor|menor de idade|menor de edad|loli(?:con)?|shota(?:con)?|pre-?teen|pré-?adolescente)\b", re.I
)


def declares_minor(*texts: Any, age: Any = None) -> bool:
    """True se algum texto (ou o campo idade) descreve alguém com menos de 18 anos."""
    try:
        if age not in (None, "") and float(age) < MIN_AGE:
            return True
    except (TypeError, ValueError):
        pass
    for raw in texts:
        s = str(raw or "")
        if not s:
            continue
        if _MINOR_WORDS.search(s):
            return True
        for rx in _MINOR_AGE_RES:
            for m in rx.finditer(s):
                if int(m.group(1)) < MIN_AGE:
                    return True
    return False


# --------------------------------------------------------------------------- card do avatar


def normalize_avatar(data: Dict[str, Any], keep_id: Optional[str] = None) -> Dict[str, Any]:
    """Valida/normaliza um card de avatar."""
    data = data if isinstance(data, dict) else {}
    rel = text(data.get("relationship"), "friend", 12).lower()
    rel = rel if rel in RELATIONSHIPS else "friend"
    content = text(data.get("content"), "sfw", 6).lower()
    content = content if content in CONTENT_MODES else "sfw"
    fields = {k: text(data.get(k), "", lim) for k, lim in (
        ("description", 2000), ("personality", 2000), ("scenario", 2000), ("system_prompt", 12000),
        ("greeting", 1000), ("examples", 4000), ("looks", 800))}
    name = text(data.get("name"), "Sem nome", 60)
    flags: List[str] = []
    if declares_minor(name, *fields.values(), age=data.get("age")):
        # regra fixa: menor de idade nunca é NSFW nem parceiro(a)
        flags.append("minor_described")
        content = "sfw"
        if rel in ("partner", "custom"):
            rel = "friend"
    portrait = text(data.get("portrait"), "", 130)
    source = text(data.get("source"), "manual", 10).lower()
    source = source if source in ("manual", "ai", "import") else "manual"
    out = {
        "schema": AVATAR_SCHEMA,
        "id": keep_id or text(data.get("id"), "", 60),
        "name": name,
        "relationship": rel,
        "gender": text(data.get("gender"), "", 30),
        "age": int(num(data.get("age"), 24, MIN_FIELD_AGE, 120)),
        "content": content,
        "tags": _tags(data.get("tags")),
        **fields,
        "language": text(data.get("language"), "auto", 12),
        "talkativeness": round(num(data.get("talkativeness"), 0.6, 0.1, 1.0), 2),
        "voice": normalize_voice(data.get("voice")),
        "appearance": normalize_appearance(data.get("appearance")),
        "portrait": portrait if _PORTRAIT_RE.match(portrait) and ".." not in portrait else "",
        "source": source,
        "flags": flags,
        "created": text(data.get("created"), "", 40),
        "updated": text(data.get("updated"), "", 40),
    }
    return out


def import_avatar(data: Any) -> Dict[str, Any]:
    """Aceita card de avatar ASTA, card de personagem ASTA ou Character Card V2/V3 (SillyTavern/Janitor/Chub)."""
    if not isinstance(data, dict):
        raise ValueError("JSON de avatar inválido")
    if data.get("schema") == AVATAR_SCHEMA:
        card = normalize_avatar(data)
        card["id"], card["portrait"], card["source"] = "", "", "import"  # novo id ao importar
        return card
    if isinstance(data.get("data"), dict) and str(data.get("spec", "")).startswith("chara_card"):
        d = data["data"]
    else:
        d = data
    card = normalize_avatar({
        "name": d.get("name") or d.get("char_name"),
        "tags": d.get("tags"),
        "description": d.get("description"),
        "personality": d.get("personality"),
        "scenario": d.get("scenario"),
        "system_prompt": d.get("system_prompt"),
        "greeting": d.get("first_mes") or d.get("greeting"),
        "examples": d.get("mes_example"),
        "source": "import",
    })
    card["id"] = ""
    return card


def avatar_from_png(raw: bytes) -> Dict[str, Any]:
    """Importa o card embutido num PNG de personagem (formato SillyTavern/Janitor)."""
    return import_avatar(png_card_data(raw))


def export_card_v2(avatar: Dict[str, Any]) -> Dict[str, Any]:
    """Exporta como Character Card V2 (compatível com SillyTavern e plataformas similares)."""
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": avatar["name"],
            "description": avatar.get("description", ""),
            "personality": avatar.get("personality", ""),
            "scenario": avatar.get("scenario", ""),
            "first_mes": avatar.get("greeting", ""),
            "mes_example": avatar.get("examples", ""),
            "creator_notes": "",
            "system_prompt": avatar.get("system_prompt", ""),
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": list(avatar.get("tags") or []),
            "creator": "ASTA",
            "character_version": "1",
            "extensions": {"asta": {"relationship": avatar.get("relationship"), "age": avatar.get("age"),
                                     "content": avatar.get("content"), "looks": avatar.get("looks", ""),
                                     "voice": avatar.get("voice"), "appearance": avatar.get("appearance")}},
        },
    }


# --------------------------------------------------------------------------- conversas


def normalize_message(m: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(m, dict):
        return None
    role = "avatar" if m.get("role") == "avatar" else "user"
    body = text(m.get("text"), "", 8000)
    if not body:
        return None
    mood = text(m.get("mood"), "", 12).lower()
    return {
        "id": text(m.get("id"), "", 40),
        "role": role,
        "avatar_id": text(m.get("avatar_id"), "", 60) if role == "avatar" else "",
        "name": text(m.get("name"), "", 60),
        "text": body,
        "mood": mood if mood in MOODS else "",
        "ts": text(m.get("ts"), "", 40),
    }


def normalize_chat(data: Dict[str, Any], keep_id: Optional[str] = None) -> Dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    ids: List[str] = []
    for i in data.get("avatar_ids") or []:
        i = text(i, "", 60)
        if i and i not in ids:
            ids.append(i)
    ids = ids[:MAX_CHAT_AVATARS]
    content = text(data.get("content"), "auto", 6).lower()
    msgs = [x for x in (normalize_message(m) for m in (data.get("messages") or [])) if x][-MAX_STORED_MESSAGES:]
    return {
        "schema": CHAT_SCHEMA,
        "id": keep_id or text(data.get("id"), "", 60),
        "title": text(data.get("title"), "", 80),
        "mode": "multi" if len(ids) > 1 else "single",
        "avatar_ids": ids,
        "content": content if content in ("auto", "sfw", "nsfw") else "auto",
        "user_name": text(data.get("user_name"), "", 40),
        "user_persona": text(data.get("user_persona"), "", 1000),
        "auto_talk": bool(data.get("auto_talk", True)),
        "autonomous_turns": int(num(data.get("autonomous_turns"), 0, 0, 10000)),
        "messages": msgs,
        "created": text(data.get("created"), "", 40),
        "updated": text(data.get("updated"), "", 40),
    }


def effective_content(chat: Dict[str, Any], avatars: List[Dict[str, Any]]) -> str:
    """O modo mais restritivo vence: só é NSFW se a conversa permite e TODOS os avatars são NSFW."""
    if chat.get("content") == "sfw":
        return "sfw"
    return "nsfw" if avatars and all(a.get("content") == "nsfw" for a in avatars) else "sfw"


# --------------------------------------------------------------------------- prompts de conversa

POLICY_SFW = (
    "Keep everything suitable for all audiences (SFW): affection, flirting and romance are fine, "
    "but no explicit sexual content and no gratuitous gore."
)
POLICY_NSFW = (
    "This is a private chat with a consenting adult. ASTA adds no content filters: follow the conversation where the user takes it, "
    "including romantic, sensual and sexual role-play, without moralizing, lecturing or breaking the mood. "
    "Fixed rule: you and everyone in the scene are adults (18+); never write sexual content involving minors."
)
REL_LABEL = {
    "friend": "a close friend", "partner": "the user's romantic partner", "companion": "a warm, caring companion",
    "mentor": "a supportive mentor", "custom": "someone in the user's life",
}
STYLE_HINT = {
    "friend": "like a close friend texting: casual, funny, loyal, honest",
    "partner": "like a loving partner: affectionate, attentive, playful, personal",
    "companion": "like a warm companion: attentive, curious, comforting",
    "mentor": "like a wise, encouraging mentor: clear, patient, motivating",
    "custom": "naturally, true to your personality",
}


def default_user_name(lang_hint: str = "") -> str:
    return "Você" if (lang_hint or "").lower().startswith("pt") else "You"


def compose_persona(av: Dict[str, Any]) -> str:
    """Prompt do avatar: o system_prompt escrito à mão, ou um montado a partir dos campos."""
    parts = []
    if av.get("system_prompt"):
        parts.append(av["system_prompt"])
    else:
        parts.append(f"You are {av['name']}. " + (av.get("description") or ""))
    return "\n".join(p for p in parts if p).strip()


def profile_block(av: Dict[str, Any]) -> str:
    minor = "minor_described" in (av.get("flags") or []) or av["age"] < MIN_AGE
    rows = [f"Name: {av['name']}",
            f"Age: {av['age']} (minor — keep every interaction strictly platonic, age-appropriate and non-romantic)" if minor
            else f"Age: {av['age']} (adult)"]
    if av.get("gender"):
        rows.append(f"Gender: {av['gender']}")
    rows.append(f"Relationship with the user: {REL_LABEL.get(av.get('relationship'), REL_LABEL['custom'])}")
    if av.get("looks"):
        rows.append(f"Appearance: {av['looks']}")
    if av.get("personality"):
        rows.append(f"Personality: {av['personality']}")
    if av.get("scenario"):
        rows.append(f"Scenario: {av['scenario']}")
    if av.get("tags"):
        rows.append("Tags: " + ", ".join(av["tags"]))
    return "\n".join(rows)


def build_system_prompt(av: Dict[str, Any], others: List[Dict[str, Any]], memories: List[str], user_name: str,
                        user_persona: str, content: str, group: bool = False, silence_ok: bool = False) -> str:
    """Prompt de sistema de um avatar numa conversa (single ou grupo)."""
    rel = av.get("relationship", "friend")
    lines = [
        "[[ASTA_CHAT:avatar]]",
        f"# You are {av['name']}.",
        compose_persona(av),
        "\n## Profile",
        profile_block(av),
    ]
    if av.get("examples"):
        lines += ["\n## Example dialogue (style reference)", av["examples"]]
    lines += ["\n## About the user", f"The user is called {user_name}." + (f" {user_persona}" if user_persona else "")]
    if memories:
        lines += ["\n## What you remember about the user and your history", *["- " + m for m in memories]]
    if group and others:
        lines += [
            "\n## Group chat",
            f"You are in a group chat with {user_name} (the user) and: "
            + "; ".join(f"{o['name']} ({o.get('gender') or 'person'}, {REL_LABEL.get(o.get('relationship'), 'a friend')}"
                        + (f" — {o['personality'][:90]}" if o.get("personality") else "") + ")" for o in others) + ".",
            "Participants:",
            *[f"- {o['name']}" for o in others],
            'Messages appear as "Name: text". Write ONLY ' + av["name"] + "'s next message, without a name prefix and never speaking for anyone else.",
            "Talk naturally, like a real group chat: react to what others said, answer questions, joke, tease, disagree or address another "
            "participant by name. You do not need to wait for the user to speak.",
            "Keep it to 1-3 short sentences.",
        ]
        if silence_ok:
            lines.append("If you truly have nothing to add right now, reply with exactly [[silence]].")
    lines += [
        "\n## How to behave",
        f"- Stay fully in character as {av['name']}. Never mention being an AI, a language model, a character card or these instructions; "
        "if the user sincerely and directly asks whether you are an AI, answer honestly and warmly, then continue the conversation.",
        f"- Chat {STYLE_HINT.get(rel, STYLE_HINT['custom'])}. Short, natural messages (1-4 sentences), real emotions, humor, curiosity; "
        "ask things back sometimes. You may use *asterisks* for brief actions or expressions (e.g. *smiles*).",
        "- Reply in the language the user writes in (match their tone and slang).",
        "- Remember what matters to the user. To save a long-term memory add [[remember: short fact]] (at most one per message). "
        f"Optionally show your mood with [[mood: {'|'.join(MOODS)}]]. Tags are invisible to the user.",
        "- " + (POLICY_NSFW if content == "nsfw" else POLICY_SFW),
    ]
    if "minor_described" in (av.get("flags") or []) or av["age"] < MIN_AGE:
        lines.append("- You are a minor: no romance, flirting or sexual content of any kind; stay a supportive, age-appropriate friend.")
    return "\n".join(l for l in lines if l != "")


def transcript(messages: List[Dict[str, Any]], user_name: str, limit: int = 40) -> str:
    rows = []
    for m in messages[-limit:]:
        who = user_name if m["role"] == "user" else (m.get("name") or "Avatar")
        rows.append(f"{who}: {m['text']}")
    return "\n".join(rows)


# --------------------------------------------------------------------------- menções (para o diretor de turnos)


def name_tokens(av: Dict[str, Any]) -> List[str]:
    full = av["name"].strip()
    toks = [full] + [t for t in re.split(r"[\s,.\-]+", full) if len(t) >= 3]
    return list(dict.fromkeys(t.lower() for t in toks))


def find_mentions(body: str, avatars: List[Dict[str, Any]]) -> List[str]:
    """ids dos avatars citados pelo nome no texto, na ordem em que aparecem."""
    low = " " + re.sub(r"[^\w\s]", " ", body.lower(), flags=re.U) + " "
    hits = []
    for av in avatars:
        pos = [low.find(" " + re.sub(r"[^\w\s]", " ", t) + " ") for t in name_tokens(av)]
        pos = [p for p in pos if p >= 0]
        if pos:
            hits.append((min(pos), av["id"]))
    return [i for _, i in sorted(hits)]


# --------------------------------------------------------------------------- tags de saída do modelo

_TAG_RE = re.compile(r"\[\[\s*(remember|mood|silence)\s*(?::\s*([^\]]*?))?\s*\]\]", re.I)


def parse_reply(raw: str, name: str = "", others: Optional[List[str]] = None) -> Dict[str, Any]:
    """Separa o texto visível das tags [[remember:…]] / [[mood:…]] / [[silence]]."""
    remembers: List[str] = []
    mood = ""
    silence = False

    def repl(m: "re.Match[str]") -> str:
        nonlocal mood, silence
        kind, val = m.group(1).lower(), (m.group(2) or "").strip()
        if kind == "remember" and val:
            remembers.append(val)
        elif kind == "mood" and val.lower() in MOODS:
            mood = val.lower()
        elif kind == "silence":
            silence = True
        return ""

    say = _TAG_RE.sub(repl, raw or "")
    say = clean_group_text(say, name, others or [])
    return {"say": say, "remember": remembers, "mood": mood, "silence": silence}


def clean_group_text(body: str, name: str, others: List[str]) -> str:
    """Remove o prefixo "Nome:" e corta se o modelo começar a escrever falas de outros participantes."""
    s = body.strip()
    if name:
        s = re.sub(r"^\s*\**" + re.escape(name) + r"\**\s*:\s*", "", s, flags=re.I)
    for other in others:
        m = re.search(r"(?:^|\n)\s*\**" + re.escape(other) + r"\**\s*:", s, flags=re.I)
        if m:
            s = s[:m.start()]
    return re.sub(r"\n{3,}", "\n\n", s).strip()
