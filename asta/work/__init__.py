"""Work (v0.18): trabalho em equipe com IA — pessoas e cargos com permissões, quadro de fluxograma, setores com arquivos sincronizados, pedidos, atividades,
notificações em tempo real e sincronização entre várias máquinas (Tailscale, rede local ou pasta de nuvem), com backups escolhidos pelo usuário."""
from .manager import Ctx, WorkError, WorkManager, normalize_config  # noqa: F401
