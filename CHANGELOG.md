# Changelog

Todas as mudanças relevantes do ASTA são registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.2.11] — 2026-11-05

### Adicionado
- **Biblioteca — selecionar vários e apagar.** O botão **Selecionar** (ou *Selecionar vários* no menu ⋯ de um item) liga o modo de seleção: cada cartão ganha uma caixa de marcação, a barra mostra quantos itens estão marcados e oferece **Selecionar os exibidos** (respeita a busca e os filtros), **Apagar selecionados** (com confirmação) e **Cancelar**. Funciona com mundos, jogos 2D, avatars, canvases e modelos. Depois de apagar, o ASTA sai do modo de seleção e informa quantos itens foram apagados (e quanto espaço foi liberado).
- **Modelos de IA locais na Biblioteca.** Os modelos GGUF instalados (texto, imagem, vídeo, som e música, voz e outros — incluindo os pré-instalados) aparecem como cartões, com o tipo, a quantização, o tamanho e a marca *pré-instalado*; há o filtro **Modelos de IA locais**. Os pré-instalados mostram o nome do catálogo (ex.: *Z-Image*), e os arquivos de apoio (VAE, codificador de texto) aparecem junto do modelo principal, não como modelos soltos.
- **Apagar modelos locais**, um de cada vez (botão *Apagar* do cartão) ou vários (modo de seleção). Um modelo dividido em partes é apagado inteiro; ao apagar um pré-instalado, os arquivos de apoio dele vão junto. Se um modelo apagado ainda estiver escolhido nas configurações, o ASTA apenas deixa de achá-lo — basta escolher outro ou baixá-lo de novo.
- API: `GET /api/library/models` (lista) e `POST /api/library/models/delete` (`{"items": [{"kind", "name"}]}`; só apaga `.gguf` dentro da pasta de modelos).
- **Terminal — o ASTA pergunta antes de baixar os modelos pré-instalados.** O instalador (`install.sh`/`install.ps1`) e o `asta update` listam o que falta (com o tamanho) e perguntam **sim ou não** (`[s/N]`, Enter = não) antes de baixar. A pergunta funciona também com `curl … | sh` (lê do terminal de verdade). Responder *não* fica guardado em `~/.asta/preinstalled.json` e não é perguntado de novo; `asta models install` (sem `--ask`) baixa quando você quiser. Sem terminal para perguntar (CI, scripts), nada é baixado e o ASTA avisa como baixar depois.
  - `ASTA_MODELS=all|text|image` responde antecipadamente (baixa sem perguntar) e `ASTA_MODELS=none` pula; antes, o padrão era baixar tudo sem perguntar.
  - Novo `asta models install --ask`; o que já está instalado continua sendo pulado e só o que falta é listado na pergunta.
- Testes: listagem/exclusão de modelos (todos os tipos, partes divididas, arquivos de apoio, proteção contra caminhos fora da pasta), a pergunta (sim, não, lembrar a recusa, sem terminal, só o que falta), a leitura da resposta com um **terminal de verdade (pty)** com o stdin ocupado por um pipe, o `install.sh` real chamando (ou não) `--ask`, e a Biblioteca no navegador (modelos, seleção, apagar em lote e um a um).

### Alterado
- O subtítulo da Biblioteca e o contador (agora "item(ns)") passam a incluir os modelos locais.

### Observação
- O `install.ps1` (Windows) e a leitura de `CONIN$` não puderam ser executados aqui; o caminho Linux/macOS (`/dev/tty`) está testado com um pty.
- Apagar um modelo pré-instalado libera o espaço, mas o instalador só volta a oferecê-lo se você não tiver recusado antes; para baixar de novo: `asta models install` ou o botão em *Configuração → Modelos locais*.

## [0.2.10] — 2026-11-05

### Alterado
- **Terminal — não reinstala o que já está instalado.** O instalador (`install.sh`/`install.ps1`), o `asta update` e o `asta libs` agora descobrem o que já existe e só atualizam se precisar:
  - **Python:** se já está instalado, só pergunta ao gerenciador de pacotes (apt, dnf, yum, pacman, zypper, apk, Homebrew, winget) se há versão mais nova e avisa o resultado (*"já está na versão mais recente"* ou *"atualizado: X → Y"*).
  - **Ambiente (venv):** reaproveitado; só é recriado se o Python mudou de versão (como antes).
  - **ASTA:** o instalador consulta a versão publicada na `main` e **não baixa nem reinstala** se a instalada já é a mesma (ou mais nova). Se a consulta falhar (sem internet) ou a origem for outra (`ASTA_SOURCE`), ele instala normalmente. `ASTA_FORCE=1` (ou `asta update --force`) reinstala mesmo assim.
  - **Bibliotecas (`asta libs`):** mostra o que já está instalado (com a versão) e instala só o que falta; as já instaladas passam por uma checagem silenciosa e o pip só mexe nelas se houver versão mais nova. Sem internet, o que já está instalado vira aviso, não erro. O resumo final diz quais já estavam instaladas.
  - **Modelos pré-instalados:** continuam sem baixar de novo arquivos que já estão na pasta.
  - Novo `ASTA_VERSION_URL`: troca o endereço de onde a versão publicada é lida (usado nos testes e em forks).

### Adicionado
- **Janela de contexto de 32K nos modelos de texto pré-instalados.** O modelo de texto pré-instalado (`empero-ai/Qwen3.8-2B-Distill`, Q8_0) agora roda com **32.768 tokens** de contexto por padrão, em qualquer nível de hardware. Os demais modelos GGUF de texto continuam com 2.048/4.096/8.192 conforme o hardware.
- **Ajustável pelo usuário:** campo **Janela de contexto (tokens)** no provedor *Hugging Face GGUF (embutido)* (*Configuração → Provedores*), com sugestões de 4K a 128K, o botão *Usar o automático* e o valor efetivo mostrado abaixo do campo; o cartão do modelo pré-instalado mostra o chip *Contexto 32K*. Valor mínimo 512, máximo ~1M; valor inválido volta ao automático. O padrão de 32K é calculado na hora e **nunca gravado** nas configurações — então instalar ou atualizar não sobrescreve o que você escolheu. Mudar o valor recarrega o modelo na memória (`settings.providers.local_hf.n_ctx`).
- Testes: o contexto (padrão, ajuste, limites, valores inválidos, recarga do modelo, configuração do usuário preservada), o `asta libs` com bibliotecas já instaladas, o `asta update` que pula o ASTA já atualizado (e `--force`/`ASTA_FORCE`), e o `install.sh` real pulando/baixando o ASTA conforme a versão publicada.

### Observação
- Uma janela de 32K usa mais memória (RAM) do que as de 2K–8K: em computadores com pouca RAM, reduza o valor no campo acima. O carregamento real do modelo com 32K de contexto não foi exercitado neste ambiente de desenvolvimento (sem o `llama-cpp-python` real); o que está testado é o cálculo do valor e o repasse ao `Llama(n_ctx=…)`.
- A checagem de versão compara o número em `asta/__init__.py`: uma correção publicada na `main` sem aumentar a versão não é baixada por quem já tem aquele número (use `ASTA_FORCE=1`).
- O `install.ps1` (Windows) não pôde ser executado aqui; a lógica foi escrita espelhando o `install.sh`, que é testado.

## [0.2.9] — 2026-11-05

### Adicionado
- **Modelos pré-instalados**: o ASTA agora já vem com dois modelos locais, baixados pelo instalador (e pelo `asta update`) com a quantização definida — **somente estes dois, por enquanto**:
  - **texto:** `empero-ai/Qwen3.8-2B-Distill` em **Q8_0** (GGUF oficial `empero-ai/Qwen3.8-2B-Distill-GGUF`, ~1,9 GB);
  - **imagem:** `Tongyi-MAI/Z-Image` em **Q4_K_M** (GGUF `unsloth/Z-Image-GGUF`, ~3,9 GB), junto com o VAE (`ae.safetensors`) e o codificador de texto Qwen3-4B (Q4_K_M) de que ele precisa — ~6,2 GB no total.
- Instalação: `install.sh` e `install.ps1` baixam os dois (`ASTA_MODELS=all`, padrão; `none` pula; `text`/`image` escolhe um); `asta models install` / `asta models list`; cartão **Modelos pré-instalados** em *Configuração → Modelos locais* com instalação por um clique, progresso e cancelamento; `asta update` também verifica. Arquivos já baixados são pulados, partes que faltam voltam sozinhas, o espaço em disco é conferido antes e uma falha vira aviso (o ASTA continua instalado). API: `GET /api/preinstalled` e `POST /api/preinstalled/install`.
- Depois de instalado, o modelo fica pronto: o de texto vira o modelo padrão de geração e de personagens e o de imagem vira o provedor de imagem do Canvas (*GGUF local*) — **só se** você ainda estiver no provedor Demo e a biblioteca que roda o modelo estiver instalada (`asta[local]`); caso contrário a sua escolha é mantida e o ASTA diz o que falta.
- O Z-Image já carrega com o VAE e o codificador de texto certos e com `cfg_scale 4` e `sample_steps 30` (o campo "extra" do nó sobrescreve).
- Testes: catálogo, instalação (com um Hugging Face simulado), configuração automática, retomada, CLI, API, provedor GGUF com os padrões do catálogo e navegador.

### Observação
- Ao contrário dos demais modelos locais (em que o ASTA pergunta a quantização antes de baixar), nos pré-instalados a quantização vem definida pelo catálogo; outras quantizações continuam disponíveis na busca da mesma aba.
- O ASTA **não consegue rodar o Z-Image neste ambiente de desenvolvimento** (sem GPU nem a `stable-diffusion-cpp-python` real): o download e a configuração estão testados, mas os nomes dos argumentos de carregamento (`llm_path` etc.) e os parâmetros de geração seguem a documentação da stable-diffusion.cpp e podem precisar de ajuste conforme a versão da biblioteca — use o campo "extra" do nó.

## [0.2.8] — 2026-11-05

### Adicionado
- **Avatars a partir de foto ou arte.** No modo Avatar da tela Principal, a opção **Foto/arte como base** usa as imagens anexadas como base visual: dá para enviar **só a imagem** ou somar prompt de texto e outros anexos (documentos, conversas…). Escolha *um avatar por imagem* ou *uma pessoa com todas as imagens*.
  - A imagem define o visual (`looks`, cor do cabelo, aparência) — descrito pelo modelo de visão configurado, ou pelas cores dominantes no modo Demo — e **vira o retrato** do avatar; o texto só acrescenta nome, personalidade e história. O número de avatares segue as imagens, não o palpite do modelo.
  - O ASTA **não identifica pessoas reais pelo rosto**: o nome vem do texto ou, se não houver, do nome do arquivo (`luna_azul-01.png` → "Luna Azul").
  - **Segurança:** foto de pessoa real, ou imagem que não dá para identificar como arte, fica **sempre SFW** (com aviso); NSFW só vale quando o modelo de visão classifica a imagem como arte de personagem fictício (`source_kind: "art"`). Uma imagem que pareça mostrar um menor segue a regra fixa dos menores (SFW e platônico, sem "envelhecer").
  - API: `POST /api/avatars/generate` aceita `from_images` e `images_mode` (`each`|`one`).
- **Modelos GGUF por tipo** (*Configuração → Modelos locais*): abas **Texto, Imagem, Vídeo, Som e música, Voz e Outros**, cada uma com busca própria no Hugging Face (filtrada pela tarefa do repositório), pasta própria (`models/` para texto — como sempre —, `models/image`, `models/video`, `models/sound`, `models/voice`, `models/other`), o mesmo seletor de quantização e lista de baixados própria. API: `kind` em `/api/hf/search`, `/api/hf/local` (também `all`), `/api/hf/download` e `DELETE /api/hf/local/<nome>`; sem `kind`, tudo continua valendo para texto.
- **Provedor "GGUF local" no Canvas** (imagem e vídeo): roda GGUF quantizados (FLUX, Stable Diffusion, Wan…) pela `stable-diffusion.cpp` (`stable-diffusion-cpp-python`, agora no extra `local`/`all`). Botão *Usar no Canvas* nos arquivos baixados; opções de carregamento (VAE, codificadores…) no campo "extra" do nó (`{"load": {"diffusion_model_path": "@model", "vae_path": "ae.safetensors"}}`).
- Testes: avatars a partir de imagem (um por imagem, uma pessoa, texto somado, regra de SFW, validação), tipos de GGUF (busca, pastas, lista, exclusão), provedor GGUF com a biblioteca simulada e testes de navegador dos três fluxos.

### Observação
- Para **Som, Voz e Outros** o ASTA só baixa e organiza os arquivos GGUF: não há motor embutido para rodá-los. A geração de vídeo por GGUF depende de a versão instalada da `stable-diffusion-cpp-python` oferecer essa função (senão o nó explica). O provedor GGUF só foi testado com a biblioteca simulada (não há GPU nem a biblioteca real neste ambiente de desenvolvimento).

## [0.2.7] — 2026-11-05

### Alterado
- **O ASTA sempre pergunta qual quantização você quer antes de baixar qualquer modelo local.**
  - **Modelos GGUF** (*Configuração → Modelos locais*): nenhuma quantização vem pré-selecionada (a recomendada só aparece destacada); o botão fica desativado até você escolher e, ao clicar, uma confirmação mostra a quantização, o tamanho e se cabe na sua RAM. A API `POST /api/hf/download` agora **exige o campo `quant`** (ex.: `"Q4_K_M"`) e responde 400 sem ele — nada é baixado sem uma escolha explícita.
  - **Modelos locais do Canvas** (*Configuração → Mídia → Hugging Face local*): antes, o primeiro uso baixava o modelo padrão em silêncio. Agora você escolhe o modelo de cada tipo e a **precisão (quantização): fp32, fp16 ou bf16**, vendo o tamanho do download de cada uma (com a recomendada para o seu computador: fp16 com placa de vídeo, fp32 sem). Só os arquivos da precisão escolhida são baixados (variantes `.fp16`, sem pesos duplicados em outros formatos), com progresso e cancelamento entre arquivos.
  - O provedor local do Canvas **só carrega modelos que você baixou** (sempre com `local_files_only` e na precisão escolhida); para um modelo não baixado, o erro do nó explica como baixá-lo.

### Adicionado
- Rotas `GET /api/media/local/state`, `GET /api/media/local/options?model=` e `POST /api/media/local/download` (exige `precision`).
- Testes: escolha obrigatória no GGUF e na API, seleção de arquivos por precisão, recusa de modelo não baixado e testes de navegador dos dois fluxos.

### Observação
- Quem já usava o provedor local do Canvas precisa baixar o modelo uma vez pelo novo fluxo (a escolha da precisão é registrada junto ao download).

## [0.2.6] — 2026-11-05

### Corrigido
- **Windows:** depois de instalar, digitar `asta` dava *"O termo 'asta' não é reconhecido como nome de cmdlet…"*. Duas causas no `install.ps1`:
  - o instalador só gravava o PATH do usuário e pedia para abrir um novo terminal; agora o comando também vale **já no terminal atual** (quando se usa `irm … | iex`);
  - numa conta com o PATH do usuário vazio, `$userPath.TrimEnd(';')` falhava e, desde a 0.2.5 (`$ErrorActionPreference = 'Continue'`), essa falha passava em silêncio — o PATH nunca era configurado. O código agora aceita PATH vazio e compara as pastas sem diferenciar maiúsculas/minúsculas nem barra final.
- O PATH agora é configurado **antes** da instalação das bibliotecas (que é demorada), então o comando existe mesmo que o instalador seja interrompido nessa etapa.
- Se `asta` ainda não for reconhecido no terminal atual, o instalador mostra o comando com o caminho completo (`& '…\asta.exe'`) e explica o que fazer. O `install.sh` (Linux e macOS) também mostra o caminho completo quando a pasta do comando não está no PATH.

## [0.2.5] — 2026-11-05

### Corrigido
- **Windows:** o comando de instalação/atualização (`install.ps1`) falhava no Windows PowerShell 5.1 com `NativeCommandError` logo depois de criar o ambiente (`python.exe : Traceback (most recent call last)` na linha `$old = & $venvPy -I -c "import asta; …" 2>$null`). Nessa versão do PowerShell, com `$ErrorActionPreference = 'Stop'`, qualquer texto que um programa externo escreve no stderr vira uma exceção — até com `2>$null` — e, na primeira instalação, o `import asta` falha de propósito (o ASTA ainda não está instalado). O instalador agora usa `'Continue'` e checa os erros que importam por `$LASTEXITCODE` e `-ErrorAction Stop`; o mesmo vale para as chamadas ao `pip`, ao `winget` e à detecção do Python. Um teste garante que o `Stop` global não volte.

## [0.2.4] — 2026-11-05

### Alterado
- **Instalar e atualizar agora também instala e atualiza o Python e os derivados dele.** O `install.sh` (Linux e macOS) e o `install.ps1` (Windows):
  - instalam o **Python 3.9+** se ele faltar e **o atualizam** a cada execução, usando o gerenciador de pacotes do sistema — `apt`, `dnf`/`yum`, `pacman`, `zypper`, `apk` ou Homebrew; `winget` no Windows. No Linux isso inclui `python3-venv` e `python3-pip`. Pode pedir a senha (`sudo`);
  - recriam o ambiente privado do ASTA quando o Python novo é de uma versão mais nova (as bibliotecas são reinstaladas em seguida) ou quando o ambiente antigo está quebrado;
  - atualizam o `pip`, o `setuptools` e o `wheel` do ambiente antes de instalar o ASTA e suas bibliotecas.
- `asta update` passa a rodar o instalador oficial (baixado do repositório), então atualiza **Python, ASTA e bibliotecas** de uma vez; no Windows o instalador continua numa nova janela. Em instalações manuais (`pip`, modo editável) ou sem internet, atualiza o `pip`/`setuptools`/`wheel`, o ASTA e as bibliotecas e avisa que o Python do sistema não é gerenciado pelo ASTA.
- `ASTA_PYTHON=keep` (e `asta update --no-python`) mantém o Python do sistema como está; `asta update --core` atualiza só o ASTA e as ferramentas do Python.
- `asta doctor` mostra também as versões do `pip` e do `setuptools`.
- Metadados do pacote no formato atual do setuptools (licença SPDX, `setuptools>=77`), sem o aviso de descontinuação durante a instalação.

### Adicionado
- `sh install.sh --python-only` (ou `ASTA_STEP=python`, e `$env:ASTA_STEP = "python"` no Windows): só instala/atualiza o Python e as ferramentas dele.
- Testes do instalador com gerenciador de pacotes simulado (Python ausente, atualização, modo `keep`, ambiente recriado) e do `asta update`; o CI usa `ASTA_PYTHON=keep` no job do instalador.

## [0.2.3] — 2026-11-05

### Alterado
- **Instalar e atualizar agora também instala e atualiza todas as bibliotecas do ASTA.** O `install.sh`, o `install.ps1` e o `asta update` passam a instalar/atualizar, por padrão, os três grupos de bibliotecas opcionais — `docs` (PDFs mais precisos), `media` (modelos locais de imagem, vídeo, som e voz do Canvas) e `local` (modelos GGUF embutidos) —, sempre junto com as dependências delas (`--upgrade-strategy eager`). Antes, isso só acontecia com `ASTA_EXTRAS` definido e o `asta update` não tocava nas bibliotecas.
- Uma biblioteca que falhe (por exemplo, `llama-cpp-python` sem compilador) vira um aviso com a dica de como tentar de novo: o ASTA e as outras bibliotecas continuam sendo instalados.
- `ASTA_EXTRAS` agora aceita `all` (padrão), `none` (só o ASTA, sem dependências) ou uma lista (`docs,media,local`).

### Adicionado
- Comando `asta libs [--extras …]`: instala/atualiza só as bibliotecas, lendo a lista da versão do ASTA instalada (então bibliotecas novas de versões futuras entram sozinhas).
- `asta update --core` (só o ASTA) e `asta update --extras …` (escolher as bibliotecas).
- Extra `asta[all]` no pacote (todas as bibliotecas de uma vez).
- Testes da linha de comando e dos instaladores; o CI instala com uma biblioteca opcional leve e também só o núcleo.

## [0.2.2] — 2026-11-05

### Adicionado
- **Escolha da quantização** dos modelos locais do Hugging Face (*Configuração → Modelos locais*): o ASTA identifica a quantização de cada arquivo GGUF (Q2_K … Q8_0, IQ*, F16/BF16…), mostra a qualidade esperada, marca quais cabem na sua RAM e **recomenda** uma opção equilibrada (em geral Q4_K_M); você escolhe qual baixar e o botão mostra o tamanho.
- Modelos divididos em partes (`-00001-of-00003.gguf`) são baixados juntos, com progresso somado, e aparecem como uma só opção; partes já baixadas são aproveitadas ao retomar. Repositórios com partes faltando e arquivos de projetor de visão (`mmproj`) não entram na lista de quantizações.
- A lista **Baixados** mostra a quantização e o número de partes de cada modelo; apagar um modelo dividido remove todas as partes. Antes de baixar, o ASTA confere o espaço livre em disco.
- API: `GET /api/hf/files` devolve `quant`, `bits`, `quality`, `parts`, `files`, `sizes`, `fits` e `recommended`; `POST /api/hf/download` aceita `files` (e `sizes`), mantendo o campo antigo `file`.

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

[Não lançado]: https://github.com/KMC1525/ASTA/compare/v0.2.11...HEAD
[0.2.11]: https://github.com/KMC1525/ASTA/compare/v0.2.10...v0.2.11
[0.2.10]: https://github.com/KMC1525/ASTA/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/KMC1525/ASTA/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/KMC1525/ASTA/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/KMC1525/ASTA/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/KMC1525/ASTA/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/KMC1525/ASTA/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/KMC1525/ASTA/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/KMC1525/ASTA/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/KMC1525/ASTA/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/KMC1525/ASTA/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/KMC1525/ASTA/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/KMC1525/ASTA/releases/tag/v0.1.0
