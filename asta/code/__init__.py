"""ASTA Code: vibe coding de bases de código longas com equipes de agentes em vários passos (até 16 agentes por sessão, várias sessões em segundo plano), com leitura, revisão, testes,
planejamento, correção e publicação de código — em pastas do computador e em repositórios do GitHub (pela API, também no celular) — usando provedores de IA de nuvem (frontier) ou locais."""
from .manager import CodeError, CodeManager, normalize_config

__all__ = ["CodeError", "CodeManager", "normalize_config"]
