"""Provedor Demo: funciona 100% offline, sem IA, para testar o fluxo e a interface.

Ele reconhece os agentes do pipeline pelo marcador `[[ASTA_AGENT:nome]]` no prompt de
sistema e responde com o gerador determinístico (agents/rulebased*.py). Nas conversas
de NPC e de avatar (`[[ASTA_CHAT:avatar]]`) responde com falas simples — suficiente para ver tudo funcionando.
"""
from __future__ import annotations

import json
import re
from typing import Iterator, List

from ..agents import rulebased, rulebased_avatars, rulebased_games
from .base import Provider, content_text, split_system

AGENTS = {
    "analyst": rulebased.analyst,
    "planner": rulebased.planner,
    "characters": rulebased.characters,
    "architect": rulebased.architect,
    "sound_ux": rulebased.sound_ux,
    "reviewer": rulebased.reviewer,
    "avatar_analyst": rulebased_avatars.analyst,
    "avatar_designer": rulebased_avatars.designer,
    "avatar_reviewer": rulebased_avatars.reviewer,
    "avatar_prompt_analyst": rulebased_avatars.prompt_analyst,
    "avatar_prompt_writer": rulebased_avatars.prompt_writer,
    "avatar_prompt_reviewer": rulebased_avatars.prompt_reviewer,
    "game_analyst": rulebased_games.analyst,
    "game_designer": rulebased_games.designer,
    "game_reviewer": rulebased_games.reviewer,
}


class DemoProvider(Provider):
    id = "demo"
    label = "Demo (offline)"
    vision = False

    def __init__(self, cfg):
        super().__init__(cfg)
        self.model = "demo"

    def _chat(self, messages, system, temperature, max_tokens, json_mode) -> str:
        sys_text, rest = split_system(messages, system)
        m = re.search(r"\[\[ASTA_AGENT:(\w+)\]\]", sys_text)
        last_user = ""
        for msg in reversed(rest):
            if msg["role"] == "user":
                last_user = content_text(msg.get("content"))
                break
        if m and m.group(1) in AGENTS:
            marker = "INPUT_JSON:"
            idx = last_user.find(marker)
            data = {}
            if idx >= 0:
                try:
                    data = json.loads(last_user[idx + len(marker):].strip())
                except json.JSONDecodeError:
                    data = {}
            return json.dumps(AGENTS[m.group(1)](data), ensure_ascii=False)
        if "[[ASTA_CHAT:avatar]]" in sys_text:
            return rulebased_avatars.avatar_reply(sys_text, last_user)
        return rulebased.npc_reply(sys_text, last_user)

    def _stream(self, messages, system, temperature, max_tokens) -> Iterator[str]:
        text = self._chat(messages, system, temperature, max_tokens, False)
        for i in range(0, len(text), 6):
            yield text[i:i + 6]

    def list_models(self) -> List[str]:
        return ["demo"]
