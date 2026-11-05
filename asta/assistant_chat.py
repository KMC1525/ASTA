"""Chat geral do ASTA (a tela «Chat»): conversa de uso geral — perguntas, estudo, receitas, texto, código — com o modelo escolhido.

Diferente dos *avatars* (personagens) e dos pipelines de criação (mundos 3D, avatars, jogos 2D, Canvas), aqui há **um modelo só, em conversa**.
Os processos de vários agentes **só rodam quando o usuário ativa uma ferramenta de criação** na caixa de texto (o «ativador»): o chat nunca dispara um
pipeline sozinho. O máximo que ele faz é *sugerir* (`suggest`) a ferramenta quando o pedido parece de criação, e o usuário decide se clica.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import attachments as att
from . import avatars as av
from . import voice
from .agents import prompts
from .providers import resolve_provider
from .util import new_id, now_iso, num, text

CHAT_SCHEMA = "asta.chat.v1"
MAX_MESSAGES = 400
MAX_USER_CHARS = 12000
TOOLS = ("world", "avatar", "game", "canvas")

SYSTEM = (
    "[[ASTA_CHAT:assistant]]\n"
    "You are ASTA's assistant: a helpful, honest, general-purpose AI chat. You can answer questions, explain topics and help people study, plan, "
    "cook (recipes), write, translate, brainstorm and code. Reply in the same language the user writes in, be clear and well organized "
    "(short paragraphs; lists and **bold** only when they help; code in fenced blocks), and say so when you are not sure instead of inventing facts.\n"
    "ASTA can also create 3D worlds, chat avatars, 2D games and Canvas projects, but ONLY when the user turns on a creation tool in the message box "
    "(the ✦ button). You never create those yourself and must never claim you did: if the user asks for one, tell them briefly to turn on the matching tool "
    "(you can help write the prompt for it).\n"
)


# --------------------------------------------------------------------------- documento da conversa


def normalize_message(m: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(m, dict):
        return None
    role = m.get("role")
    body = str(m.get("text") or "")
    if role not in ("user", "assistant") or not body.strip():
        return None
    out: Dict[str, Any] = {"id": text(m.get("id"), "", 40), "role": role, "text": body[:60000], "ts": text(m.get("ts"), "", 40)}
    if role == "user":
        out["attachments"] = [{"name": text(a.get("name"), "", 120), "kind": text(a.get("kind"), "file", 20)} for a in (m.get("attachments") or []) if isinstance(a, dict)][:20]
        out["context"] = str(m.get("context") or "")[:20000]  # texto dos anexos (as próximas mensagens ainda enxergam os documentos)
    else:
        out["model"] = text(m.get("model"), "", 120)
    return out


def normalize_chat(data: Any, keep_id: Optional[str] = None) -> Dict[str, Any]:
    d = data if isinstance(data, dict) else {}
    msgs = [x for x in (normalize_message(m) for m in (d.get("messages") or [])) if x][-MAX_MESSAGES:]
    return {"schema": CHAT_SCHEMA, "id": keep_id or text(d.get("id"), "", 60), "title": text(d.get("title"), "", 80), "messages": msgs,
            "created": text(d.get("created"), "", 40), "updated": text(d.get("updated"), "", 40)}


def title_from(body: str) -> str:
    line = next((l.strip() for l in str(body).splitlines() if l.strip()), "")
    return (line[:57] + "…") if len(line) > 58 else line


# --------------------------------------------------------------------------- ativador: o chat só SUGERE a ferramenta de criação

_VERB = re.compile(r"\b(?:cri(?:e|ar|a)|ger(?:e|ar)|fa[çc]a|fazer|monte|montar|construa|construir|desenvolva|produza|produzir|desenhe|create|generate|make|build|design|produce)\b", re.I)
_QUESTION = re.compile(r"^\s*(?:como|o que|qual|quais|por ?que|quem|quando|onde|how|what|why|who|when|where|which|can you explain|me explique|explique)\b", re.I)
_NOUN = {
    "avatar": re.compile(r"\bavatar(?:es)?\b|companheir[oa]\b|\bnamorad[oa]\b|\besposa\b|\bmarido\b|amig[oa] virtual|\bgirlfriend\b|\bboyfriend\b|\bwife\b|\bhusband\b|\bcompanion\b|\bpersonagem para (?:conversar|chat)", re.I),
    "game": re.compile(r"\bjogo\b|\bjogos\b|\bgame\b|\brpg\b|visual novel|\bplataforma\b|\bshooter\b|platformer|point (?:and|&) click|escape room", re.I),
    "world": re.compile(r"\bmundo\b|\bworld\b|cen[áa]rio 3d|3d (?:scene|environment)|\bvila\b|\bcidade 3d\b", re.I),
    "canvas": re.compile(r"\bcanvas\b|\bimagem\b|\bimagens\b|v[ií]deo|\bimage\b|\bpicture\b|narra[çc][ãa]o|\btrilha sonora\b|\bm[úu]sica\b", re.I),
}


def detect_tool(body: str) -> Optional[str]:
    """Ferramenta de criação que o pedido parece querer (só para SUGERIR; nada roda sem o clique do usuário). None para perguntas e conversa comum."""
    s = str(body or "")[:400]
    if not _VERB.search(s) or _QUESTION.match(s):
        return None
    for tool in ("avatar", "game", "world", "canvas"):
        if _NOUN[tool].search(s):
            return tool
    return None


# --------------------------------------------------------------------------- motor


class AssistantChat:
    def __init__(self, store: Any):
        self.store = store
        self._locks: Dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, chat_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(chat_id, threading.Lock())

    def create(self, title: str = "") -> Dict[str, Any]:
        return self.store.chats.save({"title": title, "messages": []})

    def _get(self, chat_id: str) -> Dict[str, Any]:
        chat = self.store.chats.get(chat_id)
        if not chat:
            raise ValueError("Conversa não encontrada")
        return chat

    def _settings(self) -> Dict[str, Any]:
        s = self.store.get_settings()
        c = s.get("chat") or {}
        return {"turns": int(num(c.get("history_turns"), 20, 1, 100)), "temperature": num(c.get("temperature"), 0.7, 0, 1.5), "max_tokens": int(num(c.get("max_tokens"), 2000, 64, 16000)),
                "content": "sfw" if (s.get("generation") or {}).get("content") == "sfw" else "free", "all": s}

    # ----- montagem do histórico para o modelo
    def _history(self, chat: Dict[str, Any], turns: int, vision: bool, images: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        msgs = chat["messages"][-turns * 2:]
        out: List[Dict[str, Any]] = []
        budget = 120000  # caracteres: o mais antigo sai primeiro
        for i in range(len(msgs) - 1, -1, -1):
            m = msgs[i]
            body = m["text"]
            if m["role"] == "user":
                if m.get("context"):
                    body = f"{body}\n\n[Anexos desta mensagem]\n{m['context']}"
                elif m.get("attachments"):
                    body += "\n\n[Anexos: " + ", ".join(a["name"] for a in m["attachments"]) + "]"
            if budget - len(body) < 0 and out:
                break
            budget -= len(body)
            out.append({"role": m["role"], "content": body})
        out.reverse()
        while out and out[0]["role"] != "user":  # modelos de template estrito exigem começar pelo usuário
            out.pop(0)
        if images and vision and out and out[-1]["role"] == "user":
            out[-1]["content"] = [{"type": "text", "text": out[-1]["content"]}] + [{"type": "image", "media_type": i["media_type"], "data": i["data"]} for i in images]
        return out

    def _attachments(self, ids: List[str], settings: Dict[str, Any]):
        metas = [m for m in (self.store.get_upload(u) for u in (ids or [])[:20]) if m]
        analyzed: List[Dict[str, Any]] = []
        transcribe = voice.transcriber(settings)
        for meta in metas:
            analyzed.append(att.analyze(Path(meta["path"]), meta["name"], meta.get("mime", ""), transcribe=transcribe))
        for meta in metas:
            self.store.delete_upload(meta["id"])  # consumidos: o texto vai junto da mensagem
        return metas, analyzed

    # ----- uma rodada
    def send(self, chat_id: str, body: str, attachment_ids: List[str], emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False) -> None:
        body = (body or "").strip()
        if not body and not attachment_ids:
            raise ValueError("Escreva uma mensagem.")
        with self._lock_for(chat_id):
            chat = self._get(chat_id)
            cfg = self._settings()
            metas, analyzed = self._attachments(attachment_ids, cfg["all"])
            digest = att.build_digest(analyzed)
            images = att.collect_images(analyzed)
            msg = {"id": new_id("m_"), "role": "user", "text": (body or "(anexo)")[:MAX_USER_CHARS], "ts": now_iso(),
                   "attachments": [{"name": a["name"], "kind": a["kind"]} for a in analyzed], "context": digest}
            chat["messages"].append(msg)
            first = not chat["title"]
            if first:
                chat["title"] = title_from(body or (analyzed[0]["name"] if analyzed else "Novo chat"))
            self._save(chat)
            emit({"type": "user", "message": {k: msg[k] for k in ("id", "role", "text", "ts", "attachments")}})
            if first:
                emit({"type": "title", "title": chat["title"]})
            self._answer(chat, cfg, images, emit, cancelled, suggest_from=body)

    def regenerate(self, chat_id: str, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False) -> None:
        """Descarta a última resposta e responde de novo à última mensagem do usuário."""
        with self._lock_for(chat_id):
            chat = self._get(chat_id)
            msgs = chat["messages"]
            idx = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i]["role"] == "user"), -1)
            if idx < 0:
                raise ValueError("Ainda não há uma mensagem sua para responder de novo.")
            dropped = [m["id"] for m in msgs[idx + 1:]]
            chat["messages"] = msgs[:idx + 1]
            self._save(chat)
            emit({"type": "removed", "ids": dropped})
            self._answer(chat, self._settings(), [], emit, cancelled, suggest_from="")

    def _answer(self, chat, cfg, images, emit, cancelled, suggest_from: str) -> None:
        provider, info = resolve_provider(cfg["all"], "generation", self.store.models_dir)
        emit({"type": "provider", **info})
        system = SYSTEM + prompts.POLICY_SFW if cfg["content"] == "sfw" else SYSTEM + prompts.POLICY_FREE
        messages = self._history(chat, cfg["turns"], bool(getattr(provider, "vision", False)), images)
        if images and not getattr(provider, "vision", False):
            emit({"type": "notice", "message": "O modelo escolhido não enxerga imagens: respondi só com o texto. Escolha um modelo com visão no seletor de modelo."})
        emit({"type": "typing"})
        raw, sent = "", 0
        for chunk in provider.chat(messages, system=system, temperature=cfg["temperature"], max_tokens=cfg["max_tokens"], stream=True):  # type: ignore[union-attr]
            if cancelled():
                break
            raw += chunk
            vis = av.strip_reasoning(raw).lstrip()  # o raciocínio (<think>…</think>) de alguns modelos não aparece
            if len(vis) > sent:
                emit({"type": "delta", "text": vis[sent:]})
                sent = len(vis)
        if cancelled():
            emit({"type": "end", "reason": "cancelled"})
            return
        final = av.strip_reasoning(raw).strip()
        if not final:
            emit({"type": "error", "kind": "empty", "message": ("O modelo gastou todo o limite de resposta «pensando» e não respondeu. Escolha outro modelo ou use um sem raciocínio."
                                                               if raw.strip() else "O modelo não devolveu nenhum texto. Confira se ele está carregado (botão de modelo).")})
            emit({"type": "end", "reason": "empty"})
            return
        msg = {"id": new_id("m_"), "role": "assistant", "text": final, "ts": now_iso(), "model": (info.get("label") or "") + (" · " + info["model"] if info.get("model") else "")}
        chat["messages"].append(msg)
        self._save(chat)
        emit({"type": "message", "message": msg})
        tool = detect_tool(suggest_from) if suggest_from else None
        if tool:
            emit({"type": "suggest", "tool": tool, "prompt": suggest_from[:2000]})
        emit({"type": "end", "reason": "done"})

    def _save(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        return self.store.chats.save(chat, chat["id"])
