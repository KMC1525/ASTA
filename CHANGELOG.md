# Changelog

Todas as mudanças relevantes do ASTA são registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.2.1] — 2026-11-05

### Alterado
- As seções **Personagens** e **Worldbuilding** saíram da barra lateral e agora ficam dentro de **Mundos**, como abas (`Mundos`, `Personagens`, `Worldbuilding`; rotas `#/worlds`, `#/worlds/characters` e `#/worlds/worldbuilding`). Os links antigos (`#/characters` e `#/worldbuilding`) continuam funcionando e abrem a aba correspondente.
- A barra lateral fica com sete itens: Principal, Mundos, Avatars, Jogos 2D, Canvas, Biblioteca e Configuração.
- README (inglês e português) atualizados com a nova organização.

## [0.2.0] — 2026-11-05

Reformulação do projeto: além de mundos 3D com NPCs-agentes, o ASTA agora é uma **central open source de criação com IA** com quatro modos — mundos 3D, **avatars**, **jogos 2D** e **Canvas** de mídia — todos a partir da mesma caixa de prompt e salvos na mesma biblioteca.

### Adicionado

**Avatars** (conversa por texto e voz, inspirada em Janitor e SillyTavern)
- Cards de avatar completos (`asta.avatar.v1`): relação (amigo, namorado(a), companheiro(a), mentor, outro), idade, gênero, personalidade, aparência, cenário, primeira mensagem, exemplos de fala, system prompt opcional, voz, quanto fala em grupo e retrato (envio de imagem ou rosto desenhado que muda com o humor). Importa/exporta Character Card V2 (JSON e PNG).
- Criação por IA a partir de texto, imagens ou qualquer arquivo anexado — um avatar ou vários de uma vez (pipeline Analista → Designer de avatares → Revisor → Salvar).
- Conversas **single** (você ↔ 1 avatar) e **em grupo** (você ↔ até 8 avatars) com *diretor* de turnos: menções, quanto cada um fala e **conversa livre**, em que os avatars continuam conversando entre si sem você pedir (com limite de falas seguidas e pausa).
- Respostas em *streaming*; respostas faladas, ditado e conversa por voz com as mãos livres (voz do navegador ou servidores STT/TTS compatíveis com OpenAI); memória de curto e longo prazo que o próprio avatar anota.
- SFW ou NSFW por avatar. Regra fixa: avatars são adultos; um card que descreva um menor de idade nunca é "envelhecido" — fica estritamente SFW e platônico (amigo, nunca parceiro(a)).

**Jogos 2D** (cinco gêneros, gerados como dados validados — `asta.game2d.v1`)
- Visual novel (estilo Ren'Py), RPG (estilo RPG Maker), plataforma, side scroller (shooter e runner) e point & click.
- Pipeline Anexos → Analista de jogo → Game designer → Revisor → Empacotador, com geradores de regras como reserva (sempre sai um jogo jogável).
- Motores 2D em JS puro (`asta/runtime2d`): arte vetorial procedural, áudio sintetizado, controles de toque, salvar/carregar; condições com gramática segura (sem `eval`), idêntica em Python e JavaScript.
- Garantias por teste nos geradores embutidos: as fases de plataforma são completadas por um robô, o RPG é vencível e as visual novels têm ramificações e finais; tudo que a IA escreve passa por validação e reparo (início, objetivo, chão, checkpoints, referências quebradas, finais alcançáveis).
- Entrega em ZIP (`Game.html`, `code/`, `data/`, `ui/`, `prompts/`), jogo direto no ASTA, atualização do mesmo jogo e reconstrução com o motor mais recente.

**Canvas** (fluxo simples de nós para imagens, vídeos, sons e vozes)
- Editor de nós com pan/zoom, conexões tipadas, resultados nos próprios nós, execução com acompanhamento ao vivo e cache por hash (só o que mudou é gerado de novo). Vários canvases, um por projeto; download em ZIP.
- Nós: Texto, Texto IA, Mídia, Imagem (gerar/editar), Vídeo, Som, Voz, Transcrever, **Style Prompt**, **Style Folder** e **Editor**.
- **Style Prompt** e **Style Folder** valem para o projeto todo (ou só onde ligados); o Style Folder é descrito pelo modelo de visão configurado ou pelas cores dominantes.
- **Editor** (simula um editor de vídeo): trilhas de vídeo/áudio/texto, bandeja de mídias, prévia ao vivo, dividir/cortar/mover, fades, opacidade, posição, legendas e exportação em MP4 via `ffmpeg`; clipes ligados a nós acompanham a saída mais recente deles.
- Provedores de mídia: OpenAI (inclui edição de imagem, TTS, Whisper e Sora), servidores compatíveis com OpenAI, ElevenLabs, Google (Gemini/Veo), Stability AI, Replicate, Hugging Face Inference, Stable Diffusion WebUI (local), modelos do Hugging Face locais (`pip install "asta[media]"`) e **Demo** offline (imagens procedurais, sons sintetizados, vídeo Ken Burns).
- Modelos de partida (Texto → Imagem, → Vídeo, Com estilo, Cena completa) e anexos do compositor viram nós ao criar um canvas pelo hub.

**Hub e interface**
- Tela Principal com os quatro modos; biblioteca unificada (mundos 3D, avatars, jogos 2D e canvases) com filtro por tipo, busca e tags.
- Configuração: abas **Mídia** (provedor padrão por tipo, chaves, endereços, modelos, teste de conexão) e **Avatars e jogos**.
- Interface traduzida para inglês por completo; um teste garante que nenhuma frase fique sem tradução.
- Navegação no celular; suporte a *Range* HTTP para vídeo e áudio.

**Testes**
- Suíte ampliada de 40 para mais de 130 testes: avatars, jogos 2D (inclui motores em Node e robô de plataforma), Canvas (esquema, armazenamento, adaptadores com servidor simulado, motor, Editor com `ffmpeg`, API), traduções e testes de navegador opcionais (Chromium via Playwright).

### Alterado
- O **README agora é em inglês** (`README.md`); a versão em português está em `README.pt-BR.md` (o antigo `README.en.md` foi removido).
- Os pipelines de geração passam a compartilhar um executor (`Runner`) e as rotas ganharam módulos próprios por recurso.
- Projetos da biblioteca ganham o campo `kind` (`world`, `game2d`); projetos da v0.1 continuam funcionando como mundos 3D.
- `asta doctor` informa também os componentes opcionais do Canvas.

### Segurança
- Mídias enviadas ao Canvas são identificadas pelo **conteúdo**, nunca pelo nome ou pelo `Content-Type`; arquivos servidos têm o caminho validado.
- Chaves de provedores de mídia usam o mesmo cofre das demais (`settings.json`, permissão `600`) e nunca voltam ao navegador.

## [0.1.0] — 2026-11-04

Primeira versão: o ASTA completo, de ponta a ponta.

### Adicionado

**WebUI** (preta, minimalista, inspirada no Grok; PT-BR e inglês)
- Barra lateral esquerda com `Principal`, `Mundos`, `Personagens`, `Worldbuilding`, `Biblioteca` e `Configuração`.
- Prompt multimodal: texto + anexos de qualquer tipo (arrastar-e-soltar, colar, upload com progresso).
- Acompanhamento ao vivo dos agentes (SSE); a geração continua se você sair da tela.
- Cards de personagens (nome, tags, system prompt, voz, aparência) e de worldbuilding (nome, system prompt), com criar/duplicar/importar/exportar e criação assistida por IA. Importa Character Card V2/V3 (JSON e PNG).
- Biblioteca com busca, tags automáticas e personalizadas, versões e atualização do mesmo jogo várias vezes.
- Editor de mundos (bioma, clima, hora, NPCs, áudio, interface, qualidade) que gera novas versões sem gastar IA.

**Geração multi-agentes**
- Pipeline multi-etapas: Analista → Planejador → Personagens → Arquiteto → Som & UX → Revisor (com rodadas de revisão) → Empacotador.
- Validação determinística de tudo que os modelos produzem e orçamento de hardware (baixo/médio/alto); fallback por agente para sempre entregar um mundo jogável.
- Anexos: texto/código, `docx`, `odt`, `pdf`, `xlsx`, `ods`, `csv`, `pptx`, `odp`, imagens (visão), áudios (transcrição via STT) e vídeos (quadros + áudio via `ffmpeg`).
- Entrega em ZIP: `code/`, `chars/`, `sound/`, `prompts/`, `ui/ux/`, `Game.html`, além de `README.md` e `CHANGELOG.md` do mundo.

**Motor dos mundos** (HTML + CSS + JS + three.js r159, funciona direto de `file://`)
- Terreno procedural com 10 biomas, água, céu com ciclo dia/noite, estrelas, nuvens, chuva/neve/névoa/tempestade, vegetação e pedras instanciadas, capim ao redor do jogador, 17 tipos de estruturas com colisão e iluminação noturna.
- Primeira e terceira pessoa, minimapa, bússola, controles de toque.
- Qualidade adaptativa: detecta o hardware e ajusta resolução, sombras e distância em tempo real.
- Áudio 100% procedural: ambiente por bioma/clima, música generativa por humor, passos e trovões.
- Persistência: posição, hora, memórias e conversas salvas e restauradas.

**Personagens com IA**
- Conversa por texto (clique ou `E`) com *streaming*, memória de curto e longo prazo, e ações (`seguir`, `ficar`, `ir até`, `acenar`, `dançar`, `fugir`).
- Conversa por voz em qualquer idioma: Web Speech do navegador ou servidores STT/TTS compatíveis com OpenAI (inclui modelos locais).
- Autonomia opcional: NPCs decidem sozinhos o que fazer.

**Provedores**
- Claude (API nativa), ChatGPT, Grok, Gemini, OpenRouter, Hugging Face Inference, Ollama, LM Studio, llama.cpp server e qualquer endpoint compatível com OpenAI.
- Modelos GGUF do Hugging Face: busca, download com progresso/retomada e execução embutida (`asta[local]`).
- Provedor Demo offline para testar sem chave.

**Instalação e plataformas**
- Windows, macOS e Linux. Um único comando instala **e** atualiza (`install.sh` / `install.ps1`); `asta update` também atualiza.
- Núcleo sem dependências além da biblioteca padrão do Python (3.9+).

**Segurança**
- Escuta apenas em `127.0.0.1` por padrão; proteção contra DNS rebinding e CSRF; chaves de API nunca expostas ao navegador; validação de caminhos.

[Não lançado]: https://github.com/KMC1525/ASTA/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/KMC1525/ASTA/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/KMC1525/ASTA/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/KMC1525/ASTA/releases/tag/v0.1.0
