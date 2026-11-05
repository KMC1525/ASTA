"""Motor de conversa dos avatars: single (1 avatar) e multi (grupo).

No modo multi o *diretor de turnos* decide quem fala: quem foi citado pelo nome responde primeiro;
os demais entram por peso (falante/recente) e podem responder uns aos outros — e, com a conversa
livre ligada, continuam conversando entre si sem o usuário pedir (`tick`), até o limite configurado.

O diretor é determinístico (sem chamada extra ao modelo) e recebe um `random.Random` para ser testável.
"""
from __future__ import annotations

import random
import threading
from typing import Any, Callable, Dict, List, Optional

from . import avatars as av
from .agents import rulebased
from .providers import resolve_provider
from .storage import Store
from .util import new_id, now_iso, num


# --------------------------------------------------------------------------- diretor de turnos


def _weights(chat: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[float]:
    """Peso de cada candidato: quem fala mais tem mais; quem está calado há mais tempo ganha impulso."""
    last_seen: Dict[str, int] = {}
    for i, m in enumerate(chat["messages"]):
        if m["role"] == "avatar":
            last_seen[m["avatar_id"]] = i
    n = len(chat["messages"])
    out = []
    for c in candidates:
        idle = n - last_seen.get(c["id"], -1) if c["id"] in last_seen else 8
        out.append(max(0.05, c.get("talkativeness", 0.6)) * (1 + min(idle, 8) * 0.25))
    return out


def _choose(chat, candidates, rng: random.Random) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None
    return rng.choices(candidates, weights=_weights(chat, candidates), k=1)[0]


def first_speaker(chat, avatars, user_text: str, rng) -> Optional[Dict[str, Any]]:
    """Quem responde primeiro à mensagem do usuário: o citado pelo nome, senão sorteio por peso."""
    if len(avatars) == 1:
        return avatars[0]
    by_id = {a["id"]: a for a in avatars}
    mentioned = av.find_mentions(user_text, avatars)
    if mentioned:
        return by_id[mentioned[0]]
    return _choose(chat, avatars, rng)


def follow_up(chat, avatars, last: Dict[str, Any], chain_len: int, max_chain: int, rng) -> Optional[Dict[str, Any]]:
    """Depois que um avatar fala: alguém responde? (citado pelo nome ⇒ quase certo; senão probabilidade decrescente)"""
    if len(avatars) < 2 or chain_len >= max_chain:
        return None
    others = [a for a in avatars if a["id"] != last["avatar_id"]]
    by_id = {a["id"]: a for a in others}
    mentioned = [i for i in av.find_mentions(last["text"], avatars) if i in by_id]
    if mentioned:
        return by_id[mentioned[0]]
    mean_talk = sum(a.get("talkativeness", 0.6) for a in others) / len(others)
    p = 0.78 * (0.55 ** (chain_len - 1)) * (0.5 + mean_talk / 2)
    return _choose(chat, others, rng) if rng.random() < p else None


def autonomous_speaker(chat, avatars, rng) -> Optional[Dict[str, Any]]:
    """Quem fala quando ninguém escreveu: o citado na última fala (se for de outro avatar), senão por peso."""
    msgs = chat["messages"]
    last = msgs[-1] if msgs else None
    pool = [a for a in avatars if not last or last["role"] == "user" or a["id"] != last.get("avatar_id")]
    if last and last["role"] == "avatar":
        by_id = {a["id"]: a for a in pool}
        mentioned = [i for i in av.find_mentions(last["text"], avatars) if i in by_id]
        if mentioned:
            return by_id[mentioned[0]]
    return _choose(chat, pool or avatars, rng)


# --------------------------------------------------------------------------- motor


class ChatEngine:
    def __init__(self, store: Store, rng: Optional[random.Random] = None):
        self.store = store
        self.rng = rng or random.Random()
        self._locks: Dict[str, threading.Lock] = {}
        self._tick_stop: Dict[str, threading.Event] = {}
        self._guard = threading.Lock()

    def _lock_for(self, chat_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(chat_id, threading.Lock())

    # ----- contexto
    def _load(self, chat_id: str):
        chat = self.store.avatar_chats.get(chat_id)
        if not chat:
            raise ValueError("Conversa não encontrada")
        avatars = [a for a in (self.store.avatars.get(i) for i in chat["avatar_ids"]) if a]
        if not avatars:
            raise ValueError("Os avatars desta conversa foram apagados")
        return chat, avatars

    def _settings(self) -> Dict[str, Any]:
        return self.store.get_settings()

    def user_name(self, chat: Dict[str, Any], settings: Dict[str, Any]) -> str:
        if chat.get("user_name"):
            return chat["user_name"]
        if settings["avatars"].get("user_name"):
            return settings["avatars"]["user_name"]
        recent = " ".join(m["text"] for m in chat["messages"][-6:] if m["role"] == "user")
        return av.default_user_name(rulebased.detect_lang(recent) if recent else "")

    def _save(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        return self.store.avatar_chats.save(chat, chat["id"])

    # ----- criação
    def create_chat(self, avatar_ids: List[str], **opts: Any) -> Dict[str, Any]:
        avatars = [a for a in (self.store.avatars.get(i) for i in avatar_ids) if a]
        if not avatars:
            raise ValueError("Escolha pelo menos um avatar existente.")
        avatars = avatars[:av.MAX_CHAT_AVATARS]
        # sem título escolhido, o nome vem dos avatares na hora de mostrar (renomear um avatar atualiza a conversa)
        chat = {"avatar_ids": [a["id"] for a in avatars], "title": opts.get("title") or "",
                "content": opts.get("content", "auto"), "user_name": opts.get("user_name", ""), "user_persona": opts.get("user_persona", ""),
                "auto_talk": opts.get("auto_talk", self._settings()["avatars"].get("auto_talk", True)), "messages": []}
        uname = self.user_name(chat, self._settings())
        for a in avatars[:4]:  # saudações (cada avatar abre com a própria fala; {{user}}/{{char}} dos cards importados são preenchidos)
            if a.get("greeting"):
                chat["messages"].append({"id": new_id("m_"), "role": "avatar", "avatar_id": a["id"], "name": a["name"],
                                         "text": av.fill_macros(a["greeting"], a["name"], uname), "ts": now_iso()})
        return self.store.avatar_chats.save(chat)

    # ----- envio do usuário
    def send(self, chat_id: str, user_text: str, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False) -> None:
        user_text = (user_text or "").strip()
        if not user_text:
            raise ValueError("Escreva uma mensagem.")
        stop = self._tick_stop.get(chat_id)
        if stop:
            stop.set()  # o usuário falou: a conversa livre em andamento cede a vez
        with self._lock_for(chat_id):
            self._send_locked(chat_id, user_text, emit, cancelled)

    def _send_locked(self, chat_id, user_text, emit, cancelled) -> None:
        chat, avatars = self._load(chat_id)
        settings = self._settings()
        uname = self.user_name(chat, settings)
        msg = {"id": new_id("m_"), "role": "user", "avatar_id": "", "name": uname, "text": user_text[:6000], "ts": now_iso()}
        chat["messages"].append(msg)
        chat["autonomous_turns"] = 0
        self._save(chat)
        emit({"type": "user", "message": msg})
        self._respond(chat, avatars, settings, uname, user_text, emit, cancelled)

    def _respond(self, chat, avatars, settings, uname, user_text, emit, cancelled) -> None:
        """A rodada de respostas dos avatars a `user_text` (a mensagem do usuário já está salva no histórico)."""
        provider, info = resolve_provider(settings, "characters", self.store.models_dir)
        emit({"type": "provider", **info})  # a interface mostra qual IA responde (e avisa quando é só o Demo)
        speaker = first_speaker(chat, avatars, user_text, self.rng)
        max_chain = min(3, len(avatars))
        chain, last = 0, None
        while speaker is not None and chain < max_chain:
            if cancelled():
                emit({"type": "end", "reason": "cancelled"})
                return
            last = self._speak(chat, avatars, speaker, provider, settings, uname, emit, cancelled, autonomous=False)
            chain += 1
            if last is None:  # ficou em silêncio → encerra a rodada
                break
            speaker = follow_up(chat, avatars, last, chain, max_chain, self.rng)
        emit({"type": "end", "reason": "done"})

    # ----- refazer a resposta, editar e apagar mensagens
    def regenerate(self, chat_id: str, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False) -> None:
        """Descarta a(s) resposta(s) dos avatars à última mensagem do usuário e responde de novo."""
        stop = self._tick_stop.get(chat_id)
        if stop:
            stop.set()
        with self._lock_for(chat_id):
            chat, avatars = self._load(chat_id)
            msgs = chat["messages"]
            idx = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i]["role"] == "user"), -1)
            if idx < 0:
                raise ValueError("Ainda não há uma mensagem sua para os avatares responderem de novo.")
            dropped = [m["id"] for m in msgs[idx + 1:]]
            chat["messages"], chat["autonomous_turns"] = msgs[:idx + 1], 0
            self._save(chat)
            emit({"type": "removed", "ids": dropped})
            settings = self._settings()
            self._respond(chat, avatars, settings, self.user_name(chat, settings), msgs[idx]["text"], emit, cancelled)

    def _edit_locked(self, chat_id: str, fn: Callable[[Dict[str, Any]], Any]) -> Any:
        lock = self._lock_for(chat_id)
        if not lock.acquire(blocking=False):
            raise ValueError("Espere o avatar terminar de responder para mexer nas mensagens.")
        try:
            chat = self.store.avatar_chats.get(chat_id)
            if not chat:
                raise ValueError("Conversa não encontrada")
            out = fn(chat)
            self._save(chat)
            return out
        finally:
            lock.release()

    def delete_message(self, chat_id: str, message_id: str) -> None:
        def run(chat):
            before = len(chat["messages"])
            chat["messages"] = [m for m in chat["messages"] if m["id"] != message_id]
            if len(chat["messages"]) == before:
                raise KeyError(message_id)
        self._edit_locked(chat_id, run)

    def edit_message(self, chat_id: str, message_id: str, body: str) -> Dict[str, Any]:
        body = (body or "").strip()[:6000]
        if not body:
            raise ValueError("A mensagem não pode ficar vazia (use apagar).")

        def run(chat):
            for m in chat["messages"]:
                if m["id"] == message_id:
                    m["text"] = body
                    return m
            raise KeyError(message_id)
        return self._edit_locked(chat_id, run)

    # ----- conversa livre entre avatars
    def tick(self, chat_id: str, emit: Callable[[dict], None], cancelled: Callable[[], bool] = lambda: False, more: bool = False) -> None:
        """Uma fala autônoma. `more=True` zera o contador (o usuário pediu "deixa eles conversarem mais")."""
        lock = self._lock_for(chat_id)
        if not lock.acquire(blocking=False):  # já há uma fala em andamento nesta conversa
            emit({"type": "end", "reason": "busy"})
            return
        stop = self._tick_stop[chat_id] = threading.Event()
        try:
            self._tick_locked(chat_id, emit, lambda: cancelled() or stop.is_set(), more)
        finally:
            self._tick_stop.pop(chat_id, None)
            lock.release()

    def _tick_locked(self, chat_id, emit, cancelled, more: bool = False) -> None:
        chat, avatars = self._load(chat_id)
        settings = self._settings()
        if more:
            chat["autonomous_turns"] = 0
        if len(avatars) < 2:
            emit({"type": "end", "reason": "disabled"})
            return
        if not chat.get("auto_talk", True) or not settings["avatars"].get("auto_talk", True):
            emit({"type": "end", "reason": "disabled"})
            return
        if chat.get("autonomous_turns", 0) >= int(num(settings["avatars"].get("auto_talk_max"), 10, 0, 1000)):
            emit({"type": "end", "reason": "limit"})
            return
        speaker = autonomous_speaker(chat, avatars, self.rng)
        uname = self.user_name(chat, settings)
        provider, info = resolve_provider(settings, "characters", self.store.models_dir)
        emit({"type": "provider", **info})
        chat["autonomous_turns"] = chat.get("autonomous_turns", 0) + 1
        self._save(chat)  # conta o turno mesmo que o avatar fique em silêncio (evita laço infinito de silêncios)
        self._speak(chat, avatars, speaker, provider, settings, uname, emit, cancelled, autonomous=True)
        emit({"type": "end", "reason": "done"})

    # ----- uma fala
    def _prompt_messages(self, chat, avatars, speaker, uname, settings, autonomous: bool) -> List[Dict[str, Any]]:
        turns = int(num(settings["avatars"].get("history_turns"), 24, 1, 200)) * 2
        msgs = chat["messages"][-turns:]
        group = len(avatars) > 1
        if group:
            body = av.transcript(msgs, uname, limit=turns)
            tail = f"Now write {speaker['name']}'s next message."
            if autonomous:
                tail = ("Nobody has written for a while: keep the conversation going naturally (ask something, share a thought or react to the last message). "
                        + tail)
            return [{"role": "user", "content": f"[Group chat so far]\n{body}\n\n{tail}" if body else tail}]
        out: List[Dict[str, Any]] = []
        for m in msgs:
            role = "user" if m["role"] == "user" else "assistant"
            if out and out[-1]["role"] == role:
                out[-1]["content"] += "\n" + m["text"]
            else:
                out.append({"role": role, "content": m["text"]})
        if not out or out[-1]["role"] != "user":
            out.append({"role": "user", "content": "(…)"})
        if out[0]["role"] == "assistant":  # a conversa começa com a saudação do avatar: modelos com template estrito exigem começar pelo usuário
            out.insert(0, {"role": "user", "content": "(…)"})
        return out

    def _speak(self, chat, avatars, speaker, provider, settings, uname, emit, cancelled, autonomous: bool) -> Optional[Dict[str, Any]]:
        group = len(avatars) > 1
        others = [a for a in avatars if a["id"] != speaker["id"]]
        content = av.effective_content(chat, avatars)
        memories = self.store.get_memories(speaker["id"])
        system = av.build_system_prompt(speaker, others, memories, uname, chat.get("user_persona") or settings["avatars"].get("user_persona", ""),
                                        content, group=group, silence_ok=group)
        messages = self._prompt_messages(chat, avatars, speaker, uname, settings, autonomous)
        emit({"type": "typing", "avatar_id": speaker["id"], "name": speaker["name"]})
        other_names = [o["name"] for o in others] + [uname]
        raw, sent = "", 0
        hold = max([len(n) for n in other_names] + [10]) + 4  # segura o fim do texto (pode ser o início de "Outro: …" ou de uma tag)
        stream = provider.chat(messages, system=system, temperature=num(settings["avatars"].get("temperature"), 0.9, 0, 2),
                               max_tokens=int(num(settings["avatars"].get("max_tokens"), 500, 16, 8000)), stream=True)
        for chunk in stream:  # type: ignore[union-attr]
            if cancelled():
                break
            raw += chunk
            vis = av.clean_group_text(_visible(raw), speaker["name"], other_names)
            safe = vis[:max(0, len(vis) - hold)] if len(vis) > sent else ""
            if len(safe) > sent:
                emit({"type": "delta", "avatar_id": speaker["id"], "text": safe[sent:]})
                sent = len(safe)
        if cancelled():  # o usuário falou (ou pediu para parar) no meio da fala: não guarda uma frase cortada no histórico
            emit({"type": "silence", "avatar_id": speaker["id"]})
            return None
        parsed = av.parse_reply(raw, speaker["name"], other_names)
        if parsed["silence"] and not parsed["say"]:
            emit({"type": "silence", "avatar_id": speaker["id"]})
            return None
        if not parsed["say"]:
            if group:  # num grupo, um avatar sem nada a dizer simplesmente fica quieto
                emit({"type": "silence", "avatar_id": speaker["id"]})
            else:  # numa conversa a dois, ficar mudo é um problema do modelo/provedor: avisa em vez de não fazer nada
                emit({"type": "error", "kind": "empty", "avatar_id": speaker["id"], "message": _empty_reason(raw)})
            return None
        if len(parsed["say"]) > sent:
            emit({"type": "delta", "avatar_id": speaker["id"], "text": parsed["say"][sent:]})
        message = {"id": new_id("m_"), "role": "avatar", "avatar_id": speaker["id"], "name": speaker["name"], "text": parsed["say"][:6000],
                   "mood": parsed["mood"], "ts": now_iso()}
        chat["messages"].append(message)
        self._save(chat)
        if parsed["remember"]:
            self.store.add_memories(speaker["id"], parsed["remember"], int(num(settings["avatars"].get("memory_limit"), 40, 5, 500)))
        emit({"type": "message", "message": message, "remembered": parsed["remember"]})
        return message


def _empty_reason(raw: str) -> str:
    if raw.strip():  # veio texto, mas era só raciocínio (<think>…</think>) ou só tags
        return ("O modelo gastou todo o limite de resposta «pensando» (raciocínio) e não chegou a responder. Aumente o «Máximo de tokens por resposta» em "
                "Configuração → Avatars e jogos, ou use um modelo sem raciocínio.")
    return "O provedor não devolveu nenhum texto. Confira se o modelo está carregado e funcionando (Configuração → Provedores → Testar)."


def _visible(raw: str) -> str:
    """Texto visível durante o streaming: corta a partir da primeira tag [[…]] (ainda incompleta ou não)."""
    raw = av.strip_reasoning(raw)
    i = raw.find("[[")
    return (raw if i < 0 else raw[:i]).lstrip()
