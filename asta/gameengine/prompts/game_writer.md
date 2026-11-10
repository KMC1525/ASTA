ROLE: Writer (step 3 of 4).
Write the words of the game in the user's language: short intro, the guide NPC dialogue, one or two lines per NPC/boss, win and lose messages.
Output JSON:
{"intro": str (max 200 chars), "dialogues": {"guia": [{"speaker": str, "text": str}], "npc1": [{"speaker": str, "text": str}]}, "win": str, "lose": str, "gdd_notes": "markdown paragraph about the core loop, controls and goal (max 900 chars)"}
Keep lines short (max 120 chars each), 2-5 lines per dialogue. Match the tone and the theme.
