# asta-dev-guide — guia de desenvolvimento do ASTA

> **Leia este arquivo inteiro antes de mexer no projeto** — vale para pessoas e para modelos de IA que desenvolvem o ASTA. Ele diz **como trabalhar**; o *porquê* está em
> [`asta-principles.md`](asta-principles.md), que você também precisa ler e **seguir sempre**. *(English summary at the bottom.)*

## As regras (todas valem em toda mudança)

1. **Sempre atualize os README.** `README.md` (inglês) e `README.pt-BR.md` (português) andam juntos: mesma estrutura, mesmo conteúdo. Mudou comportamento, instalação, comando, tela ou limite? Atualize os dois.
2. **Sempre atualize os changelogs.** `CHANGELOG.md` (pt-BR) e `CHANGELOG.en.md` (inglês): uma entrada por versão, em `## [versão] — AAAA-MM-DD`, com *Adicionado / Alterado / Corrigido / Removido*, dizendo o que o usuário percebe e os **limites honestos** (o que não foi testado, o que depende de terceiros).
3. **Sempre atualize os releases.** A versão vive em `asta/__init__.py` (`__version__`). Subir a versão + empurrar na `main` dispara o workflow `release` (`.github/workflows/release.yml`), que publica a Release `vX.Y.Z` com os instaladores, o núcleo Rust de cada plataforma e `SHA256SUMS.txt`. As notas da Release saem do changelog (`installers/release_notes.py`) — então escreva o changelog **antes**.
4. **Sempre adicione tudo na `main`.** O trabalho só está terminado quando está na `main` (via pull request ou push direto, conforme o dono do repositório autorizar). Trabalhando numa branch de sessão/feature, abra o PR para a `main` ao terminar; a Release só roda depois do merge.
5. **Sempre siga o [`asta-principles.md`](asta-principles.md).** Controle total dos dados do usuário, open source, foco local, cloud opcional, interoperabilidade, IA em tudo, multi-agentes multi-steps e federation. Se a mudança fere um princípio, ela não entra.
6. **Sempre atualize todos os instaladores/executáveis de todas as plataformas.** Windows (`ASTA-X-Y-Win.exe`), macOS (`ASTA-X-Y-macOS.pkg`), Linux (`ASTA-X-Y-Linux.appimage`, + arm64), Android (`ASTA-X-Y-Android.apk`) e o núcleo Rust de cada plataforma. Mexeu em algo que entra no pacote (código, interface, núcleo, `install.sh`/`install.ps1`, app Android)? Confirme que o workflow `release` ainda gera os quatro e que os testes de cada um passam. Um instalador desatualizado é um bug.
7. **Todo modo, seção ou ferramenta tem um sistema multi-agente, multi-step.** Mesmo simples: *planejar → fazer → conferir*, com saída JSON validada, **fallback determinístico** e registro dos agentes. Ferramenta nova sem isso não está pronta. (Chat: *Equipe de agentes*; Mundos/Avatars/Jogos/Studio/Canvas/Rebuild: ver `agents/`, `studio/`, `canvas/`, `rebuild/`.) **Todo modo oferece 1 · 4 · 8 · 12 · 16 agentes e os 8 níveis de esforço (Low … Omni)** — use `asta/team.py`, nunca um seletor próprio.
8. **Todos os sistemas permitem conteúdo SFW e NSFW, livremente.** O ASTA **não adiciona filtros próprios**: o modo *Livre* segue o pedido da pessoa; *SFW* é uma opção do usuário. Toda seção nova respeita a configuração de conteúdo (`generation.content`, `avatars.content`…). Os limites fixos, que não mudam em nenhum modo, são: **nada sexual envolvendo menores** e **nada sexual sobre pessoas reais**. (O provedor escolhido ainda pode ter as regras dele — o ASTA avisa, não contorna.)

## Mapa rápido do código

| Pasta / arquivo | O que é |
|---|---|
| `asta/server.py`, `routes_*.py`, `jobs.py` | servidor HTTP local (`127.0.0.1`), rotas por seção, tarefas em segundo plano com eventos (SSE) |
| `asta/providers/` | provedores de IA (OpenAI-compatível, Anthropic, GGUF local, LM Studio, Demo); `limits.py` aprende o teto de tokens; `local_llama.py` carrega modelos locais |
| `asta/agents/`, `studio/`, `canvas/`, `rebuild/`, `games2d/`, `avatars*.py`, `assistant_chat.py` | as seções e suas equipes de agentes |
| `asta/computer/`, `routes_computer.py` | **Computer Use**: `engine.py` (Planejador → Operador → Revisor → Relator), `manager.py` (até 8 tarefas, fila, histórico, aprovações), `tools.py` (catálogo fechado de ações), `guard.py` (limites fixos), `files.py` (lixeira + desfazer), `osdrv.py` (drivers de SO), `rulebased.py` (fallback sem IA), `prompts/*.md` (system prompts internos) |
| `asta/code/`, `routes_code.py` | **Code** (v0.16): `engine.py` (Planejador → trabalhadores em paralelo → testes → Revisor → Relator), `manager.py` (pastas/subpastas, sessões, fila de até 8, eventos, workspaces), `tools.py` (catálogo fechado, risco por classe: `read|write|delete|run|install|git|publish`), `guard.py` (limites fixos, lista de programas, `git` restrito), `workspace.py` (arquivos + diário de desfazer), `github.py` (API: nuvem sem git, PR, issues, releases, CI), `langs.py`, `promptgen.py`, `rulebased.py` (sem IA), `prompts/*.md` |
| `asta/work/`, `routes_work.py`, `web/js/views/work*.js` | **Work** (v0.18): `store.py` (um documento JSON por coisa, «vale a edição mais nova»; arquivos por hash; cofre de senhas), `manager.py` (redes, sessões, permissões, pessoas, quadro, arquivos, pedidos, atividades, avisos, máquinas, backups), `perms.py` (catálogo fechado de permissões, cargo + função + pessoa), `sync.py` (protocolo `/peer/v1` assinado e cifrado, servidor SEPARADO da WebUI, pasta de nuvem cifrada, política de réplica `should_hold`), `crypto.py` (PBKDF2, SHAKE-256+HMAC — só biblioteca padrão), `tailscale.py`, `board.py`, `agents.py` (+ `prompts/*.md`: pedidos, fluxograma, resumo, roteador, todos com fallback). Documento novo = coleção em `schema.COLLECTIONS` + `norm_*`; nunca devolva `pw`/segredo da rede em API ou exportação. |
| `asta/studio/analysis.py`, `captions.py`, `sfx.py`, `library.py`, `transcribe.py` | **Studio v0.17**: análise de mídia (áudio decodificado uma vez + núcleo Rust), legendas SRT/VTT e alinhamento pela fala, efeitos sonoros gerados, navegador de mídia (Canvas/Studio/exportações) e transcrição. `asta/canvas/to_studio.py` leva o fluxo para a timeline |
| `asta/gameengine/`, `routes_engine.py`, `web/js/views/engine*.js` | **Game Engine** (v0.19): `schema.py` (catálogo único de nós, comportamentos, mapas — a tela monta o Inspetor a partir dele; valores escritos pelo autor ficam explícitos, então o padrão do motor e o do catálogo precisam ser iguais), `manager.py` (projetos em pastas, caminhos confinados, histórico, pacote jogável `data.js`+`index.html`), `templates.py` (jogo completo sem IA para 2D/2.5D/3D/VR/AR), `maps.py`, `art.py`, `audio.py` (tudo procedural, só biblioteca padrão), `agents.py` + `prompts/*.md` (um agente por etapa de cada aba, sempre com fallback), `exporter.py` (web/win/macos/linux/android/ios: jogo jogável + projeto Electron/Capacitor + fluxo do GitHub Actions), `runtime/ge_*.js` (motor e modo de edição) |
| `asta/team.py`, `efforts.py`, `web/js/team_ui.js` | **Equipe de agentes de TODA seção** (v0.17.26): 1 · 4 · 8 · 12 · 16 · 20 · 24 · 28 · 32 agentes (mesa em paralelo + revisão entre pares a partir de 20 + Sintetizador, `ensemble_json`; notas privadas nas conversas, `team_notes`) e os 8 níveis de esforço Low … Omni (`efforts.py`, pensamento do provedor via `apply_thinking`). Motor novo: chame `Runner.configure_team(settings["sua_secao"], req, pid)` (ou `team.from_config`) e use `self.team`; ferramenta nova ganha o cartão «Equipe de agentes» em Configuração e o `teamPicker` ao lado do botão de criar |
| `asta/attachments.py`, `archives.py` | leitura de anexos de qualquer tipo; ZIP/RAR/7z/TAR com extração segura |
| `asta/native/` | **núcleo em Rust** (`src/*.rs`) + `__init__.py` com o espelho em Python de cada função |
| `asta/perf.py`, `scheduler.py`, `storage_opt.py` | modos de desempenho, fila com prioridade, otimização de armazenamento |
| `asta/web/` | a WebUI (HTML/CSS/JS puros, sem build); textos em português com tradução em `web/js/en.js` |
| `asta/cli.py`, `termi18n.py`, `term_en.py` | linha de comando e textos do terminal (pt/en) |
| `install.sh`, `install.ps1` | instaladores de terminal |
| `installers/` | geração dos instaladores: `windows/` (Inno Setup), `macos/` (.pkg), `linux/` (AppImage), `release_notes.py` |
| `mobile-app/` | app Android: casca Capacitor + motor Python embutido (Chaquopy) em `android-overlay/` |
| `tests/` | suíte `unittest` (+ testes de navegador com Playwright) |
| `docs/` | este guia, os princípios e imagens do README |

## Como trabalhar

1. **Entenda antes de mexer.** Leia o código da seção, os testes dela e o último trecho do changelog. Preserve o que funciona; mudança grande se justifica por um bug ou por um requisito.
2. **Português primeiro na interface.** Textos de tela em português dentro de `t('…')`; toda frase nova precisa de tradução em `asta/web/js/en.js` (o teste `tests/test_i18n.py` falha se faltar). Textos do terminal: `_()` com tradução em `asta/term_en.py`. O instalador usa `L "pt" "en"`.
3. **Rust ↔ Python em paridade** (v0.17: interface 4, `media.rs` — análise de mídia e ordem de grafos; use `native.audio_levels`, `pick_peaks`, `tempo`, `topo`… nunca reimplemente em laços de Python). Toda função do núcleo tem equivalente em Python com a mesma conta; os testes comparam os dois (inclusive casos aleatórios). Mudou o Rust? Mude o Python, rode `cargo test --release --manifest-path asta/native/Cargo.toml` e os testes de paridade. Mudou a interface (ABI)? Suba `ABI` em `asta/native/__init__.py` e `asta_abi_version` em `lib.rs`, e mantenha bibliotecas antigas funcionando.
4. **Segurança de entrada.** Arquivos, pacotes, URLs e respostas de IA são **não confiáveis**: valide caminhos (zip-slip), tamanhos (zip-bomb), tipos (pelo conteúdo, não pelo nome) e JSON. Respostas de IA nunca viram código executado.
5. **Nada de dependência obrigatória nova** no núcleo Python (só biblioteca padrão). Extras opcionais entram em `pyproject.toml` (`[project.optional-dependencies]`).
6. **Teste o que mudou** — e o que depende dele:
   ```bash
   python -m unittest tests.test_<area>                       # rápido, durante o desenvolvimento
   python -m unittest discover -s tests -t .                  # tudo (≈ 10 min); testes de navegador exigem Node + Playwright + Chromium
   cargo test --release --manifest-path asta/native/Cargo.toml
   node tests/js/i18n_check.mjs                                # toda frase de tela tem tradução?
   ```
   Regressão corrigida ganha um teste que a reproduz. Se algo **não pôde ser testado** (aparelho real, certificado de assinatura), escreva isso no changelog.
7. **Diga a verdade nos documentos.** Não prometa o que não foi verificado: marque como "gerado pelo CI e não executado em aparelho real", "estimativa", "depende do provedor".

## Checklist de uma versão

- [ ] `asta/__init__.py` com a versão nova (e `asta/native/Cargo.toml` se o núcleo mudou).
- [ ] `CHANGELOG.md` e `CHANGELOG.en.md` com a seção `## [X.Y.Z] — data`.
- [ ] `README.md` e `README.pt-BR.md` atualizados (instalação, comandos, seções, limites).
- [ ] Testes: suíte completa, `cargo test`, `node tests/js/i18n_check.mjs`.
- [ ] Instaladores: `installers/`, `mobile-app/`, `install.sh`, `install.ps1` coerentes com a versão; workflow `release` verde.
- [ ] PR para a `main`, merge, e conferir a Release `vX.Y.Z` com `ASTA-X-Y-Win.exe`, `-macOS.pkg`, `-Linux.appimage`, `-Android.apk`, `asta-core-*` e `SHA256SUMS.txt`.

## Armadilhas conhecidas

- **Work:** o servidor de sincronização é **separado** da WebUI (que fica só em 127.0.0.1) e só atende `/peer/v1/…` com pedido assinado, mensagem cifrada, relógio ±5 min e *nonce* único; a escuta é **desligada por padrão** e uma importação de configurações nunca a liga. A chave da rede (`secret.json`) e o hash de senhas (`vault/`) nunca entram em documentos sincronizados, exportações ou respostas da API (exceto `pw` do modo «synced», que é só o hash e nunca sai pela API). Documentos vindos de outra máquina são entrada não confiável: passam por `OrgStore.merge` (id, tamanho, forma de `_m`). Arquivo servido ao navegador: só tipos da lista `INLINE_OK` aparecem inline, sempre com `Content-Security-Policy: sandbox`; HTML/SVG sempre baixam. Mudou o protocolo? Suba `proto` em `sync._dispatch` (`hello`) e mantenha o antigo funcionando. Não afirme no changelog que o Tailscale real ou outros sistemas foram testados se não foram.
- **Game Engine:** a IA escreve **dados validados** (`schema.norm_scene`/`norm_map`), nunca código fora do jogo; a aba Code é a exceção deliberada e o código dela só roda no **iframe isolado** (`CSP` com `sandbox` sem `allow-same-origin`, sem rede) — não afrouxe a CSP em `manager.CSP`. Toda escrita passa por `manager.write_file` (caminho confinado, tipo conferido pelo conteúdo, tamanho). O jogo não usa `fetch`: dados, imagens e sons entram por `<script>`/`<img>`/`<audio>` para funcionar em `file://` e nas exportações. Etapa nova de IA = `EngineAI.step(...)` com `validate` **e** `fallback`. VR/AR e as exportações nativas **não foram testados em aparelho real** — diga isso no changelog quando mexer neles.

- **Computer Use:** a IA só devolve JSON que o `tools.py` valida; **nunca** adicione uma ferramenta que execute texto escrito pela IA (shell, `eval`, script). Toda ferramenta nova declara uma **classe de risco** (`read|write|delete|run|input|screen`) — é ela que o modo Ask usa para perguntar — e todo caminho passa por `guard.check_path`. A pasta de dados do ASTA fica fora do alcance da IA (ela guarda as chaves de API e o modo do próprio Computer Use). Tela/teclado/mouse têm **uma trava única** (`GuiLease`): não ignore. Mudou um prompt em `computer/prompts/`? Ele vai no pacote (`pyproject.toml`, `package-data`); o teste `test_computer` confere. Os drivers de Windows/macOS/Android não são exercitados no CI: diga isso no changelog quando mexer neles.

- **Code:** é a **exceção deliberada** à regra do Computer Use (a IA nunca vira código executado): rodar testes e programas do projeto é o propósito da seção. As barreiras são fixas e não se afrouxam: tudo dentro da pasta do projeto (`guard.check_path`), comandos como **lista de argumentos** de uma lista de programas (`guard.check_program`, sem shell), `.git/` só pela ferramenta `git` (`guard.check_git`), ambiente sem chaves (`guard.clean_env`), token do GitHub só em `settings.json` (`SECRET_PATHS`) e sempre redigido (`guard.redact`). Ferramenta nova do Code declara a classe de risco (`tools.py`) e, se o risco depender dos argumentos, entra em `risk_of`. **Publicar não se desfaz**: só acontece depois de testes e revisão limpos (`engine._publish_tail`), e o resumo final leva sempre as provas do motor (`agents.evidence_lines`). Os fluxos do GitHub são testados com `FakeGitHub` (`tests/test_code.py`): diga no changelog que não rodaram contra o github.com. Prompts do Code vão no pacote (`pyproject.toml`, `package-data`).

- **Camadas do Studio (v0.17):** há cinco tipos — `video`, `image`, `audio`, `text`, `fx` — e a ordem entre grupos é fixa (texto, efeitos, vídeo/imagem, áudio; a nova camada entra no topo do grupo: `schema.add_track` e `addLayer` em `studio_timeline.js` fazem a mesma conta). Mídia nova nunca se mistura: `accepts()`/`pickTrack()` criam uma camada do tipo certo em vez de empilhar. Clipes `fx` não têm mídia e **não contam na duração**. Filtro novo? Acrescente em `schema.FILTERS`, `render.GRADES`, `studio_tools.FILTERS`/`FILTER_CSS` e `en.js`.
- **Camadas do Studio:** a primeira trilha da lista é a de **cima** (V2 sobre V1) na prévia *e* na exportação (`render_timeline(..., top_first=True)`); o Editor do Canvas usa a ordem contrária. Não unifique sem migrar os projetos.
- **Janela de contexto escolhida pelo usuário nunca é contrariada** (só se avisa). Respostas cortadas pelo limite de tokens continuam sozinhas (`last_stop == "length"`); o teto de saída de cada modelo é **aprendido** do erro do provedor (`providers/limits.py`).
- **Modelo local embutido:** uma geração por vez, por uma fila com prioridade (`scheduler.PriorityLock`); tarefas em segundo plano têm prioridade baixa.
- **Dedupe de armazenamento** só cria links físicos em `models/`, `canvases/`, `studio/`, `projects/` (arquivos que nunca são reescritos no lugar); nunca em anexos nem retratos.
- **Android:** o servidor do app roda em modo estrito (`ASTA_STRICT_LOOPBACK=1`): até o endereço local exige o cookie de pareamento do app.
- **macOS:** o Python do python.org vem sem certificados raiz; o ASTA usa os do Chaveiro (`util.ssl_context`) — não desligue a verificação TLS.

---

## English summary

Read this before changing ASTA, then follow [`asta-principles.md`](asta-principles.md). **Always:** update both READMEs; update both changelogs; update the releases (bump `__version__`, push to `main`, the `release` workflow publishes the installers); put everything on `main` (PR/merge); follow the principles; keep **every installer/executable of every platform** (Windows `.exe`, macOS `.pkg`, Linux AppImage, Android APK, plus the Rust core per platform) up to date; give **every mode/section/tool a multi-agent, multi-step system** (plan → do → check, validated JSON, deterministic fallback); allow **SFW and NSFW content freely** (no ASTA-added filters; the only fixed limits are no sexual content involving minors or real people).
Keep Rust and Python in parity, treat files/packages/AI output as untrusted, add no mandatory dependency to the Python core, test what you change, and be honest in the docs about what could not be verified.
