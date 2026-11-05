# Contribuindo com o ASTA

Obrigado por querer ajudar! O ASTA é pensado para ser **simples, leve e livre**. Antes de abrir um PR, vale conhecer os princípios:

1. **Sem dependências obrigatórias.** O núcleo usa só a biblioteca padrão do Python. Dependências extras entram como *extras opcionais* (`pip install "asta[local]"`, `"asta[media]"`) e são importadas só quando usadas, com uma mensagem clara de como instalar.
2. **Sem etapa de build.** A WebUI (`asta/web`) e os motores dos mundos 3D (`asta/runtime`) e dos jogos 2D (`asta/runtime2d`) são HTML/CSS/JS puros, sem bundler.
3. **Leveza de hardware vem primeiro.** Todo recurso 3D novo precisa respeitar os orçamentos em `asta/agents/schema.py` (`BUDGETS`) e funcionar no nível `low`.
4. **A IA escreve dados, não código.** Os agentes produzem JSON validado (`normalize_world`, `normalize_game`, `normalize_avatar`, `normalize_canvas`); os motores são código revisado. Não execute código gerado por modelos — as condições dos jogos usam uma gramática própria, sem `eval`.
5. **Segurança local.** Nada de CORS aberto, nada de expor chaves ao navegador, valide caminhos e `Host`/`Origin`.
6. **Conteúdo livre, com uma linha fixa:** sem filtros próprios do ASTA, mas nenhum conteúdo sexual envolvendo menores. Nos avatars isso está no código (`asta/avatars.py`): quem descreve um menor fica SFW e platônico, sem ser "envelhecido" — não enfraqueça essa regra.

## Ambiente

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data --no-browser              # dados isolados para desenvolvimento
python -m unittest discover -s tests -t .         # roda tudo (sem rede)
```

Os testes dos motores em JavaScript e os de navegador (Chromium via Playwright, em `tests/browser`) rodam quando o Node.js e o Playwright existem e são pulados caso contrário; o `ffmpeg` habilita os testes de vídeo do Canvas. O CI instala o Node 22.

**Núcleo Rust (`asta/native`):** opcional e só com a biblioteca padrão (sem crates). Toda função precisa ter um equivalente em Python em `asta/native/__init__.py` com o mesmo resultado. `cargo test --manifest-path asta/native/Cargo.toml` roda os testes do Rust; `asta native build` compila; `ASTA_NATIVE_LIB=<caminho>` faz `tests/test_perf_native.py` comparar Rust × Python. **Rebuild (`asta/rebuild`):** nunca leia nem copie arte/áudio do jogo original, só a estrutura; mantenha o aviso legal.

Python 3.9 é o mínimo: não use `match`, `X | Y` em tempo de execução, etc. (use `from __future__ import annotations`).

## Onde mexer

| Quero… | Arquivo |
|---|---|
| Adicionar um provedor de IA | `asta/providers/registry.py` (preset) — APIs compatíveis com OpenAI já funcionam |
| Mudar o que os agentes fazem | `asta/agents/prompts.py`, `pipeline.py` |
| Novo tipo de estrutura/bioma | `schema.py` (listas) + `runtime/scene.js` (construtor) + `rulebased.py` (Demo) |
| Comportamento/ações dos NPCs | `runtime/actors.js`, `runtime/agent.js` |
| Telas da WebUI | `web/js/views/*.js` (a frase em português é a chave de tradução; adicione em `web/js/en.js` — `tests/test_i18n.py` falha se faltar alguma) |
| Chat (conversa geral, histórico, ativador das ferramentas) | `assistant_chat.py`, `routes_chat.py`, `websearch.py` (busca na web), `providers/thinking.py` (tempo de pensamento por provedor/modelo), `web/js/views/chat.js`, `web/js/modelpicker.js`, `web/js/markdown.js` (as ferramentas de criação ficam em `web/js/views/home.js`) |
| Avatars (cards, diretor da conversa, voz) | `avatars.py`, `avatar_chat.py`, `routes_avatars.py`, `agents/avatar_pipeline.py`, `web/js/views/avatar*.js` |
| Jogos 2D (um gênero novo ou uma regra) | `games2d/schema.py` (spec e validação), `agents/rulebased_games.py` (gerador offline), `runtime2d/*.js` (motor); mantenha a gramática de condições igual em Python (`parse_cond`) e JS (`G2.cond`) |
| Canvas: novo tipo de nó | `canvas/schema.py` (`NODE_TYPES`, parâmetros), `canvas/engine.py` (execução), `web/js/canvas_nodes.js` (controles) |
| Modelos pré-instalados (catálogo) | `asta/preinstalled.py` (`CATALOG`: repositório, arquivo, quantização, tamanho, arquivos auxiliares) + tradução do `hint` em `web/js/en.js` |
| Canvas: novo provedor de mídia | classe em `canvas/media.py` + entrada em `MEDIA_PRESETS` + teste com servidor simulado em `tests/test_canvas.py` (veja `MediaMock`) |
| Editor de vídeo do Canvas | `canvas/render.py` (ffmpeg) e `web/js/canvas_timeline.js` (linha do tempo e prévia) |

## Testes e PRs

- Toda correção/recurso precisa de teste em `tests/` quando possível.
- Descreva **o que** mudou e **por quê**; registre no `CHANGELOG.md` em *Não lançado*. O `README.md` é em inglês e o `README.pt-BR.md` em português: mantenha os dois em sincronia.
- Adaptadores de APIs de terceiros: siga a documentação pública do serviço e teste contra um servidor simulado — não dá para testar serviços pagos no CI; diga no PR o que você verificou de verdade.
- Mudanças no motor 3D: anexe um screenshot (antes/depois) — o Chromium headless funciona (`--use-angle=swiftshader`).

## Versões e atualização dos mundos

Cada mundo guarda um *snapshot* do motor na hora em que foi gerado (por isso o ZIP é portátil). Após atualizar o ASTA, use **Biblioteca → ⋯ → Reconstruir com o motor mais recente**.
