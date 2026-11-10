# Contribuindo com o ASTA

*English: [CONTRIBUTING.md](CONTRIBUTING.md) — mantenha os dois arquivos em sincronia.*

Obrigado por querer ajudar! O ASTA é pensado para ser **simples, leve e livre**. Antes de abrir um PR, vale conhecer os princípios:

1. **Sem dependências obrigatórias.** O núcleo usa só a biblioteca padrão do Python. Dependências extras entram como *extras opcionais* (`pip install "asta[local]"`, `"asta[media]"`) e são importadas só quando usadas, com uma mensagem clara de como instalar.
2. **Sem etapa de build.** A WebUI (`asta/web`) e os motores dos mundos 3D (`asta/runtime`), dos jogos 2D (`asta/runtime2d`) e do Game Engine (`asta/gameengine/runtime`) são HTML/CSS/JS puros, sem bundler.
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

**Núcleo Rust (`asta/native`):** opcional e só com a biblioteca padrão (sem crates). Toda função precisa ter um equivalente em Python em `asta/native/__init__.py` com o mesmo resultado. `cargo test --manifest-path asta/native/Cargo.toml` roda os testes do Rust; `asta native setup` instala/atualiza o Rust e compila o núcleo (`asta native build` só compila); `ASTA_NATIVE_LIB=<caminho>` faz `tests/test_perf_native.py` comparar Rust × Python. **Rebuild (`asta/rebuild`):** nunca leia nem copie arte/áudio do jogo original, só a estrutura; mantenha o aviso legal.

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
| Work (pessoas, cargos/permissões, quadro, arquivos por setor, pedidos, atividades, avisos, sincronização entre máquinas, backups) | `work/` (`perms.py`, `schema.py`, `store.py`, `manager.py`, `sync.py`, `agents.py`, `prompts/*.md`), `routes_work.py`, `web/js/views/work*.js`, `web/js/work_ui.js`; testes: `tests/test_work.py`, `tests/browser/work_ui.js` |
| Game Engine (projetos, árvore de cena/catálogo, gerador por regras, mapas, arte, áudio, exportação, agentes, o motor 2D/2.5D/3D/VR/AR e o modo de edição) | `gameengine/` (`schema.py` é a fonte única de verdade de tipos de nó/comportamentos/mapas — o Inspetor é montado a partir dele; `templates.py`, `maps.py`, `art.py`, `audio.py`, `manager.py`, `exporter.py`, `agents.py`, `prompts/*.md`, `runtime/ge_*.js`), `routes_engine.py`, `web/js/views/engine*.js`, `web/js/engine_ui.js`, `web/js/editor_core.js`, `web/css/engine.css`; testes: `tests/test_engine.py`, `tests/browser/engine_ui.js`. Propriedade/comportamento novo: acrescente em `schema.py`, implemente em `runtime/ge_2d.js`/`ge_3d.js` com o **mesmo padrão** (o esquema guarda os valores explícitos) e traduza os rótulos em `web/js/en.js` / `engine_labels.js` |
| Scriber (tipos de escrita, modelo do documento, escritor/leitor de `.docx`, lorebooks, ortografia, IA para gerar/editar um trecho, as duas abas) | `scriber/` (`schema.py` é a fonte única dos tipos de escrita, idiomas e modelos de formatação — as telas são montadas a partir dele; `docmodel.py` blocos ⇄ HTML/Markdown com sanitizador por **lista de permissões**; `docx.py`; `lore.py`; `spell.py`; `manager.py`; `agents.py` + `prompts/*.md`), `routes_scriber.py`, `web/js/views/scriber*.js`, `web/js/scriber_ui.js`, `web/js/scriber_text.js` (funções puras), `web/css/scriber.css`; testes: `tests/test_scriber.py`, `tests/browser/scriber_ui.js`, `tests/browser/scriber_ai_ui.js`. Tipo de escrita novo: acrescente em `schema.WRITING_TYPES` (guia em inglês para o agente, seções padrão, modelo) e traduza os rótulos em `web/js/en.js`. O editor é um `contenteditable` que só recebe HTML que o servidor montou a partir de blocos validados; **nunca** salve o HTML do editor sem passar por `docmodel.html_to_blocks` |
| Modelos pré-instalados (catálogo) | `asta/preinstalled.py` (`CATALOG`: repositório, arquivo, quantização, tamanho, arquivos auxiliares) + tradução do `hint` em `web/js/en.js` |
| Canvas: novo provedor de mídia | classe em `canvas/media.py` + entrada em `MEDIA_PRESETS` + teste com servidor simulado em `tests/test_canvas.py` (veja `MediaMock`) |
| Editor de vídeo do Canvas | `canvas/render.py` (ffmpeg) e `web/js/canvas_timeline.js` (linha do tempo e prévia) |
| Equipe de agentes (1/4/8/12/16/20/24/28/32 agentes, esforço Low → Omni) em cada seção | `team.py` (contagens, níveis, mesa de agentes + Sintetizador, notas privadas), `efforts.py` (os 8 níveis), `agents/runner.py` (`configure_team`, `_agent`), a chamada `configure_team`/`team_chat` de cada motor, `web/js/team_ui.js` (seletores), um cartão «Equipe de agentes» em `web/js/views/config.js`; testes: `tests/test_team.py`, `tests/browser/team_ui.js` |

## Testes e PRs

- Toda correção/recurso precisa de teste em `tests/` quando possível.
- Leia antes [docs/asta-principles.md](docs/asta-principles.md) e [docs/asta-dev-guide.md](docs/asta-dev-guide.md): definem os princípios (open source, foco local, controle dos dados, interoperabilidade, IA em tudo, sistemas multi-agentes, federation) e as regras de toda mudança (atualizar os dois READMEs e os dois changelogs, manter todos os instaladores em dia, dar a toda ferramenta um fluxo multi-agente, permitir SFW e NSFW livremente).
- Descreva **o que** mudou e **por quê**; registre no `CHANGELOG.md` em *Não lançado*. Registre também no `CHANGELOG.en.md`. O `README.md` é em inglês e o `README.pt-BR.md` em português; o `CONTRIBUTING.md` (inglês) é o gêmeo deste arquivo: mantenha cada par em sincronia.
- Adaptadores de APIs de terceiros: siga a documentação pública do serviço e teste contra um servidor simulado — não dá para testar serviços pagos no CI; diga no PR o que você verificou de verdade.
- Mudanças no motor 3D: anexe um screenshot (antes/depois) — o Chromium headless funciona (`--use-angle=swiftshader`).

## Versões e atualização dos mundos

Cada mundo guarda um *snapshot* do motor na hora em que foi gerado (por isso o ZIP é portátil). Após atualizar o ASTA, use **Biblioteca → ⋯ → Reconstruir com o motor mais recente**.

## Studio (`asta/studio`)

- O documento do projeto (`asta.studio.v1`) é do servidor: cenas, ativos e episódios só mudam por jobs/rotas; o navegador salva só os metadados e a timeline (`PUT .../timeline`), assim o autosave do editor nunca apaga o que um job acabou de gerar.
- Todo agente de IA do Studio (`pipeline.py`, `autoedit.py`) precisa de um equivalente determinístico (`rulebased.py` / `plan_edl`): o modo Demo e as respostas inválidas não podem impedir a entrega.
- O renderizador é o do Canvas (`canvas/render.py`) com os campos extras `speed`/`mute`/`filter` e o parâmetro `mode` (`full|video|audio`); mantenha o comportamento antigo quando essas chaves não existem.
- Testes: `tests/test_studio.py` (usa `ffmpeg` e é pulado sem ele) e `tests/browser/studio_ui.js`. Mídias sintéticas vêm de `make_media()`.

## Textos do terminal (`asta/termi18n.py`, `asta/term_en.py`)

- Todo texto que o terminal mostra (CLI e mensagens do `preinstalled`/`native`) usa `_("frase em português {campo}", campo=...)`; a tradução inglesa fica em `asta/term_en.py` (mesma chave, mesmos `{campos}`). Um teste confere que nenhuma mensagem ficou sem tradução. Não use `_` como variável de laço nesses módulos.
- Os instaladores (`install.sh`, `install.ps1`) têm o seu próprio `L pt en`; toda mensagem `say/note/die` (`Say/Note/Die`) precisa ser bilíngue — o teste confere.
- O Rust vive em `asta native setup` (`asta/native/__init__.py`): o padrão é automático (`ASTA_RUST=yes`, sem pergunta); `ask` pergunta e `no` pula.
