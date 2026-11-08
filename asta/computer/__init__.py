"""ASTA Computer Use: uma equipe de agentes de IA que faz tarefas no computador do usuário (arquivos, programas, jogos, pesquisa, escrita), até 8 ao mesmo tempo.

* `manager.py` — fila, histórico, aprovações, desfazer · `engine.py` — a equipe Planejador → Operador → Revisor → Relator
* `tools.py` — o catálogo fechado de ações · `guard.py` — limites fixos · `files.py` — arquivos com lixeira e diário · `osdrv.py` — drivers de cada sistema
* `prompts/*.md` — os system prompts internos (em texto simples, abertos) · `rulebased.py` — o fallback sem IA
"""
from .manager import ComputerError, ComputerManager, normalize_config  # noqa: F401
