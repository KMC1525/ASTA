<div align="center">

# ASTA

**O primeiro super app open source: um só lugar para conversar com qualquer modelo de IA, pesquisar na web, criar mundos 3D cujos NPCs são agentes de IA, conversar com avatars, fazer jogos 2D e produzir imagens, vídeo, som e voz — tudo no seu computador.**

Uma WebUI preta e minimalista, inspirada no Grok. Descreva o que quer (com texto, imagens, vídeos, áudios, documentos, planilhas…) e uma equipe de agentes de IA planeja, cria, revisa e entrega: um mundo 3D jogável, um companheiro para conversar, um jogo 2D completo ou um fluxo de nós que produz imagens, vídeos, sons e vozes.

[Baixar](#baixe-os-instaladores) · [Instalação](#instalação) · [Primeiros passos](#primeiros-passos) · [Comandos](#comandos-do-terminal) · [Ferramentas de criação](#as-ferramentas-de-criação) · [Studio](#studio--vídeos-audiovisuais-com-ia-cena-a-cena) · [Computer Use](#computer-use--uma-equipe-de-ia-que-trabalha-no-seu-computador) · [Code](#code--uma-equipe-de-ia-para-programar-bases-de-código-longas) · [Provedores](#provedores-de-ia) · [Contribuir](CONTRIBUTING.pt-BR.md) · [Changelog](CHANGELOG.md) · [English](README.md)

`MIT` · `Windows` · `macOS` · `Linux` · `Android` · `Python 3.9+` · `núcleo Rust` · `zero dependências obrigatórias`

</div>

---

## O que é

O ASTA é o **primeiro super app open source**: um único app para conversar, pesquisar, criar e jogar, com todos os modelos de IA que você quiser num só lugar. É **open source e o mais livre possível**: roda no seu computador, não exige conta nem nuvem, aceita conteúdo **SFW e NSFW** (o ASTA não adiciona filtros próprios) e funciona com os modelos que você quiser — Claude, ChatGPT, Grok, Gemini, OpenRouter, Hugging Face ou modelos 100% locais.

Ele é uma central universal de criação com oito ferramentas, que você inicia na mesma caixa de prompt ou nas próprias seções:

| Modo | Você recebe |
|---|---|
| 🌍 **Mundos 3D** | Mundos 3D jogáveis e persistentes (1ª ou 3ª pessoa), habitados por NPCs que são agentes de IA embutidos. |
| 🙂 **Avatars** | Amigos, namorados(as), esposas/maridos, companheiros e mentores para conversar por **texto e voz** — um de cada vez ou **vários conversando entre si**. |
| 🎮 **Jogos 2D** | Jogos 2D completos de qualquer tipo: visual novels, RPGs, plataformas, side scrollers e point & clicks. |
| 🎬 **Studio** | **Vídeos audiovisuais com IA, cena a cena** — Shorts/Reels, curtas e longas de qualquer duração, únicos ou em série, nos estilos Realista, Cartoon, Anime ou personalizado, com **edição automática** (Gameplay, Documentário, Phonk…), **timeline estilo Kdenlive** com **Tools** ligáveis (efeitos, efeitos sonoros, captura de tela, legendas, transcrição, navegador de mídia), camadas livres (vídeo, imagem, áudio, texto, efeitos) e exportação até **4K / 120 fps**. |
| ♻️ **Rebuild** | Reconstrói a *estrutura* de um jogo **Ren'Py** ou **RPG Maker (2000 → MZ)** existente em HTML/CSS/JS puros (só para uso pessoal). |
| 💻 **Computer Use** | Uma equipe de IA **opcional** que faz **tarefas no seu computador**: escreve, pesquisa, usa programas instalados, organiza arquivos e abre jogos — modo Ask (Sim/Não) ou Full Access. |
| </> **Code** | **Vibe coding em bases de código longas** com uma equipe de até 8 agentes por sessão, pastas de sessões, 8 níveis de esforço e GitHub (modo nuvem e git), com testes, revisão e desfazer. |
| 🧩 **Canvas** | Um fluxo simples de nós (inspirado no ElevenLabs Flow, bem mais leve que o ComfyUI) para gerar e editar **imagens, vídeos, sons e vozes**, com **Editor** de vídeo embutido, **estilos** para o projeto todo, menções com `@` de imagens/vídeos/sons nos prompts, **barra de pesquisa de modelos** da Hugging Face, **seletor de modelo** por nó e *Enviar ao Studio*. |

Tudo o que você cria vai para uma só **Biblioteca** de projetos atualizáveis.

- 🧠 **Geração multi-agentes e multi-etapas** (Analista → Planejador → Designer → Revisor → Empacotador) com validação determinística e gerador de regras como reserva: algo jogável sempre é entregue.
- 🪶 **Leve por design**: o núcleo usa só a biblioteca padrão do Python; não há etapa de build; mundos e jogos se adaptam ao seu hardware.
- 🔒 **Local e privado**: o servidor escuta em `127.0.0.1`, as chaves nunca chegam ao navegador e a IA escreve **dados (JSON)**, nunca código que seja executado.

## Baixe os instaladores

Escolha o arquivo do seu sistema na [**Release mais recente**](https://github.com/KMC1525/ASTA/releases/latest) — sem terminal, sem precisar do Python:

| Sistema | Arquivo | Como |
|---|---|---|
| **Windows 10/11** (64 bits) | `ASTA-0-17-8-Win.exe` | Execute (instala só para você, sem administrador). Menu Iniciar → *ASTA*. O Python vai junto. |
| **macOS 11+** (Apple Silicon e Intel) | `ASTA-0-17-8-macOS.pkg` | Botão direito → *Abrir* (não é assinado) e depois abra o *ASTA* em Aplicativos; a primeira abertura instala para o seu usuário numa janela do Terminal. |
| **Linux** (x86_64; também `-arm64`) | `ASTA-0-17-8-Linux.appimage` | `chmod +x ASTA-0-17-8-Linux.appimage && ./ASTA-0-17-8-Linux.appimage` — um arquivo só, com o Python dentro (precisa do FUSE, ou rode com `--appimage-extract-and-run`). |
| **Android 7+** | `ASTA-0-17-8-Android.apk` | Permita «instalar apps desconhecidos» uma vez. **O ASTA roda dentro do celular — sem computador** ([detalhes](#celular-e-tablet)). |

Cada Release traz também o **núcleo Rust pré-compilado** de cada plataforma (`asta-core-*`) e o `SHA256SUMS.txt` (confira com `sha256sum -c`). Os instaladores não têm assinatura de código (exige certificado pago): o Windows pode mostrar o SmartScreen («Mais informações → Executar assim mesmo»). Eles são gerados pelo [GitHub Actions](.github/workflows/release.yml) e **não foram executados em Windows/macOS/Android reais por quem fez esta alteração** (o que deu para conferir está no [changelog](CHANGELOG.md)). Os instaladores de terminal abaixo continuam disponíveis.

## Instalação

Você nem precisa ter o Python: o instalador **instala o Python para você se ele faltar** (3.9 ou mais novo) e **o atualiza** a cada execução, junto com as ferramentas dele (`pip`, `setuptools`, `wheel`, `venv`). O **mesmo comando instala e atualiza** tudo (seus dados em `~/.asta` nunca são tocados).

**Linux e macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex
```

O instalador do Windows funciona tanto no Windows PowerShell 5.1, que já vem com o Windows, quanto no PowerShell 7. O comando `asta` é adicionado ao seu `PATH` e já funciona no mesmo terminal quando você usa o comando acima (terminais que já estavam abertos precisam ser reabertos); se ainda assim não for reconhecido, rode-o pelo caminho completo, que o instalador mostra (`%LOCALAPPDATA%\ASTA\app\venv\Scripts\asta.exe`). Se ele parar com algum erro, rode o mesmo comando de novo e abra uma issue com o texto que apareceu.

Depois, em qualquer terminal (**rodar `asta` também atualiza/instala tudo antes** — Python, ASTA, bibliotecas e modelos pré-instalados — como o comando de instalação: quando há versão nova e, fora isso, no máximo a cada 24 h; sem internet, só abre; para pular: `asta --no-update` ou `ASTA_NO_UPDATE=1`; `ASTA_UPDATE_EVERY=<horas>` muda o intervalo):

```bash
asta
```

A WebUI abre em `http://localhost:8787`. Para atualizar, rode o comando de instalação de novo (ou `asta update`).

> **Depois de atualizar, reinicie o ASTA** (feche e rode `asta` de novo) e recarregue a página (Ctrl+F5). Uma página deixada aberta durante uma atualização pode mostrar *"Não foi possível carregar esta tela"*: o ASTA a recarrega sozinho uma vez e, se não bastar, explica o que fazer; a barra lateral também avisa quando há uma versão mais nova instalada do que a que está rodando.
>
> Se uma tela ainda não carregar, uma **extensão de bloqueio de anúncios/rastreadores** do navegador (uBlock Origin, AdBlock, proteção contra rastreamento do Firefox…) pode estar barrando um arquivo do ASTA — desative-a para `localhost` e recarregue. (Os arquivos do ASTA já não usam nomes que esses bloqueadores filtram, como `quant.js`, mas uma lista rígida ainda pode barrar algo.)

**Instalar e atualizar cobre três camadas:** (1) o **Python** e as ferramentas dele — instalados ou atualizados pelo gerenciador de pacotes do seu sistema (`apt`, `dnf`/`yum`, `pacman`, `zypper`, `apk` ou Homebrew no Linux e no macOS; `winget` no Windows), que pode pedir sua senha (`sudo`); se o novo Python for de uma versão mais nova, o ambiente privado do ASTA é recriado para ele automaticamente; (2) o próprio **ASTA**; (3) **todas as bibliotecas do ASTA**, descritas abaixo. Use `ASTA_PYTHON=keep` para nunca mexer no Python do sistema.

**Nada que já está instalado é instalado de novo.** O instalador, o `asta update` e o `asta libs` descobrem o que já existe e só atualizam se precisar: o Python só é atualizado se o gerenciador de pacotes tiver versão mais nova; o ambiente privado é reaproveitado; o próprio ASTA **não é baixado de novo** quando a versão instalada já é a publicada (`ASTA_FORCE=1` ou `asta update --force` reinstala mesmo assim); as bibliotecas já instaladas só são verificadas e atualizadas se houver versão mais nova (só as que faltam são instaladas); modelos já baixados são pulados.

**Instalar e atualizar também instala e atualiza todas as bibliotecas do ASTA** — as opcionais, que liberam recursos extras (leitura de PDF mais precisa, modelos locais de imagem/vídeo/som/voz do Canvas, modelos de linguagem GGUF embutidos). A primeira instalação pode demorar e baixar vários GB (o PyTorch dos modelos do Canvas); se quiser só o núcleo leve, use `ASTA_EXTRAS=none`. Uma biblioteca que falhe (por exemplo o `llama-cpp-python` sem compilador C++) gera só um aviso: o ASTA continua funcionando, e dá para tentar de novo com `asta libs`.

<details>
<summary>Opções de instalação</summary>

| Variável | Efeito |
|---|---|
| `ASTA_EXTRAS=all` (padrão) | instala/atualiza **todas** as bibliotecas: `docs` + `media` + `local` |
| `ASTA_EXTRAS=none` | instala só o ASTA (nenhuma dependência) |
| `ASTA_EXTRAS=docs,media,local` | escolha as bibliotecas: `docs` = extração de PDFs mais precisa (`pypdf`) · `media` = modelos locais de imagem/vídeo/som/voz do Canvas (`torch`, `diffusers`, `transformers`…) · `local` = modelos GGUF embutidos: texto, imagem e vídeo (`llama-cpp-python`, `stable-diffusion-cpp-python`) |
| `ASTA_MODELS` (vazio) | o instalador **pergunta no terminal (sim/não)** antes de baixar os **modelos locais pré-instalados** (veja abaixo); `all`, `text` ou `image` baixa sem perguntar, `none` pula |
| `ASTA_PYTHON=auto` (padrão) | instala o Python se faltar e o atualiza (com `pip`, `setuptools`, `wheel`, `venv`) pelo gerenciador de pacotes do sistema |
| `ASTA_PYTHON=keep` | nunca instala nem atualiza o Python do sistema (o `pip`/`setuptools`/`wheel` do próprio ASTA continuam em dia) |
| `ASTA_FORCE=1` | reinstala o ASTA mesmo que a versão instalada já seja a última publicada |
| `ASTA_RUST=yes` (padrão) | o **núcleo Rust** (parte obrigatória do ASTA): baixa a biblioteca pronta da Release e, só se isso falhar, instala o Rust (rustup, na sua pasta de usuário, sem sudo) e compila; `no` pula, `ask` pergunta antes |
| `ASTA_NATIVE_FILE=<arquivo>` | um núcleo já compilado para copiar em vez de baixar (os instaladores usam isto) |
| `ASTA_LANG=pt\|en` | idioma dos textos do terminal (padrão: o idioma do seu computador) |
| `ASTA_SOURCE=<url\|pasta>` | instala de outra origem (fork, branch, pasta local) |
| `ASTA_APP_DIR`, `ASTA_BIN_DIR` | onde ficam o programa e o comando `asta` |

Instalação manual: `pip install "asta @ https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"`.
**`asta folder`** abre a pasta dos dados locais do ASTA (`~/.asta`: conversas, projetos, mídias, modelos, configurações) no seu gerenciador de arquivos (`--print` só mostra o caminho, `--app` abre a pasta do programa instalado).
Opções do comando: `asta --port 9000 --no-browser --home /outra/pasta` · `asta update` atualiza o **Python, o ASTA e todas as bibliotecas dele** rodando o instalador oficial (`--no-python` mantém o Python do sistema, `--core` atualiza só o ASTA e o `pip`/`setuptools`/`wheel`, `--extras docs,media` escolhe as bibliotecas; um ASTA instalado à mão com `pip` atualiza tudo menos o Python do sistema) · `asta libs` instala/atualiza só as bibliotecas, `sh install.sh --python-only` só o Python e as ferramentas dele · `asta doctor` mostra o diagnóstico do seu hardware e dos componentes opcionais. As bibliotecas são atualizadas junto com as dependências delas, então os recursos do Canvas e dos modelos locais ficam em dia.

</details>

**Ferramenta opcional.** O [`ffmpeg`](https://ffmpeg.org) libera a análise de vídeo, a exportação do Editor de vídeo do Canvas, o **Studio** (geração, edição automática e exportação) e o vídeo offline do Demo. Todo o resto funciona sem ele.

## Comandos do terminal

| Comando | O que faz |
|---|---|
| `asta` | abre a WebUI (também atualiza/instala tudo antes, quando for a hora; pule com `--no-update`) |
| **`asta update`** | atualiza **Python, ASTA, todas as bibliotecas dele e o Rust** para as versões mais recentes, rodando o instalador oficial (`--no-python`, `--core`, `--extras docs,media`, `--rust yes\|no`, `--force`) |
| **`asta folder`** | **abre a pasta dos dados locais do ASTA** (`~/.asta`: conversas, projetos, mídias, modelos, configurações) no seu gerenciador de arquivos (`--print` só mostra o caminho, `--app` abre a pasta do programa instalado) |
| **`asta mobile`** | **libera o ASTA para o celular/tablet** e mostra o QR code de pareamento (só aparelhos pareados entram) |
| `asta libs` | instala/atualiza as bibliotecas opcionais (`docs`, `media`, `local`) |
| `asta models list\|install` | os modelos locais pré-instalados |
| `asta native setup` | garante o **núcleo Rust** ativo: baixa a biblioteca pré-compilada da Release (conferida por SHA-256, sem compilador) e só compila na máquina se isso falhar (também `install`, `update`, `build`, `status`) |
| `asta doctor` | diagnóstico do ambiente (hardware, Python, Rust, ffmpeg, provedores, idioma do terminal) |
| `asta version` · `asta --help` | versão · todas as opções |

Os textos do terminal seguem o idioma do seu computador (português ou inglês; `ASTA_LANG=pt\|en` força um).

## Celular e tablet

O ASTA roda no seu computador; o celular ou tablet é uma **janela** para ele. O app mobile é o próprio ASTA instalado no aparelho (um PWA: ícone na tela inicial, tela cheia, sem loja de apps), então funciona em **Android e Apple (iOS/iPadOS)**, em **qualquer chip** — ARM64 (Snapdragon, Apple A/M, MediaTek, Exynos, Tensor) e x86 — e em **smartphones, dobráveis, tablets**, Chromebooks e afins. A interface se adapta sozinha ao tipo de aparelho, à orientação, à dobra e ao tamanho da tela.

<img src="docs/mobile-guide-qr.pt-BR.svg" alt="QR code deste guia" width="140" align="right">

**Instalar por QR code**
1. No computador, rode **`asta mobile`** (ou abra *Configuração → Celular e tablet*). Um **QR code** de pareamento aparece no terminal e nessa tela.
2. Deixe o celular/tablet na **mesma rede Wi-Fi** e aponte a câmera para o QR code. O aparelho fica **pareado** e o ASTA abre.
3. Instale: no Android toque em **Instalar**; no iPhone/iPad, **Compartilhar → Adicionar à Tela de Início**.

> O QR code à direita desta seção só abre este guia no seu celular. O **QR code de instalação/pareamento é o que o seu próprio computador mostra**, porque ele carrega o endereço do seu computador e um código secreto — um QR code num README público não tem como saber onde está o *seu* ASTA.

**O app Android não precisa de computador.** Baixe o `ASTA-0-17-8-Android.apk` em [Releases → mais recente](https://github.com/KMC1525/ASTA/releases/latest) (ou escaneie o QR code abaixo; permita «instalar apps desconhecidos» uma vez) e abra: o app traz **o motor do ASTA dentro do celular** (Python via Chaquopy) e o abre sozinho — chat, busca na web, mundos 3D, avatars, jogos 2D, Canvas e Studio com a **mesma interface**, suas chaves de IA na nuvem e uma pasta de dados privada no aparelho. O app **consulta o repositório por versões novas e pergunta «Baixar agora / Depois»**. Para usar o ASTA de um computador (modelos locais pesados, mais memória), toque em *Conectar a um computador* na tela inicial (ou em *Configuração → Celular e tablet*), escaneie o QR code de pareamento dele ou digite o endereço — os dois modos convivem.

<img src="docs/android-app-qr.svg" alt="QR code: app Android mais recente do ASTA" width="140">

> **Limites honestos do ASTA no aparelho:** modelos locais pesados (GGUF/PyTorch) não rodam dentro de um celular — aponte os provedores para um servidor Ollama/LM Studio na sua rede, ou conecte o app ao ASTA de um computador. Recursos que precisam do `ffmpeg` (análise de vídeo, exportação do Canvas/Studio) só funcionam se o APK o trouxer (`libffmpeg.so`/`libffprobe.so`). O servidor do app escuta no loopback do celular em **modo estrito** — até o endereço local exige o cookie de pareamento do app, então outros apps do celular não o usam. O APK é gerado pelo CI e **não foi executado em um aparelho real por quem fez esta alteração** (o motor em si é testado na máquina do CI). iPhone/iPad não recebe app fora da App Store, então lá continua «Adicionar à Tela de Início» pelo endereço do seu ASTA.

**Segurança:** `asta mobile` abre o ASTA para a sua rede, mas **só aparelhos pareados entram** (o próprio computador nunca precisa parear). *Gerar novo código* em *Configuração → Celular e tablet* despareia todos. Atrás de proxy ou túnel, o pareamento também é exigido.

**Atualizações:** o app avisa quando o ASTA do computador tem versão nova e **pergunta se você quer atualizar agora ou depois**. A checagem é uma requisição minúscula, então funciona em **Wi-Fi e dados móveis**, desde que o aparelho alcance o computador. Abrir sem rede e o diálogo de instalar como app exigem HTTPS ou localhost (regra do navegador); em `http://` simples na rede local, o iPhone/iPad ainda adiciona à tela inicial e o Android cria um atalho.

## Primeiros passos

1. **Teste sem configurar nada.** O provedor padrão é o **Demo** (offline, gera por regras). Abra o **Chat**, pergunte qualquer coisa e aperte **Run** — ou ligue uma ferramenta de criação (✦ *Criar*), descreva o que quer e aperte **Run** para ver os agentes trabalhando e, no fim, **Jogar**, **Conversar** ou **Abrir**.
2. **Ligue uma IA de verdade** em **Configuração → Provedores**: cole a chave (Claude, ChatGPT, Grok, Gemini…), clique em *Carregar modelos*, escolha um e *Testar*. Ou use **Ollama / LM Studio** (grátis, local).
3. **Para o Canvas**, escolha os provedores de imagem/vídeo/som/voz em **Configuração → Mídia** (OpenAI, ElevenLabs, Google, Stability AI, Replicate, Hugging Face, uma Stable Diffusion WebUI local ou modelos locais do Hugging Face). Sem nenhum, o provedor Demo deixa você testar fluxos inteiros offline.
4. Volte à **Biblioteca** quando quiser e clique em *Atualizar* para evoluir o mesmo projeto.

## Chat — a tela principal

O **Chat** é um assistente de uso geral, limpo: peça uma receita de bolo, estude um assunto, reescreva um texto, depure código. A tela é só uma caixa de texto com **anexos à esquerda**, o botão de **modelo** e o **Run** à direita.

- **Seletor de modelo** (ao lado do Run): troca de provedor *e* de modelo em um clique — Claude, ChatGPT, Grok, Gemini, OpenRouter, LM Studio, Ollama, modelo GGUF embutido… A escolha é salva e vale para o app todo.
- **Respostas em Markdown, ao vivo** (listas, tabelas, blocos de código com *Copiar*), botão **Parar** (o Run vira Parar, ou aperte **Esc**; resposta pela metade nunca é salva; a pergunta sem resposta ganha o botão **Responder**), **Responder de novo**, copiar e **Histórico** de conversas (a última reabre sozinha; *Novo chat* abre uma em branco). Anexe imagens, PDFs, planilhas, áudio, vídeo… — são lidos e usados como contexto.
- **Ativador para o trabalho pesado.** Os pipelines com vários agentes (mundo 3D, avatar, jogo 2D, Canvas) **nunca começam sozinhos**. O Chat só conversa; se você pedir para criar algo, ele *sugere* a ferramenta certa, e nada roda até **você** ligar a ferramenta (✦ *Criar* → escolher uma, ou apertar o botão da sugestão) e apertar **Run**. Desligue (×) para voltar a só conversar. As opções de criação (gênero, quantidade, relacionamento, SFW/NSFW, perspectiva…) só aparecem com a ferramenta ligada.
- **Busca na web nativa (botão 🌐 Web).** Ligue e o Chat pesquisa a sua pergunta na web, lê as primeiras páginas e entrega ao modelo com fontes numeradas; a resposta as cita como [1], [2] e mostra chips de **Fontes** clicáveis (ficam no histórico). Funciona com **qualquer modelo, inclusive local**, e com **qualquer prompt**: com uma ferramenta de criação ligada, o prompt também é pesquisado e as referências seguem junto. Motores: DuckDuckGo → Wikipédia por padrão (sem chave), Brave Search, Tavily ou a sua instância SearXNG. Perguntas de seguimento ("e o preço?") ganham uma consulta escrita pelo modelo. As páginas só são lidas em hosts públicos (nada de localhost/rede privada, nem em redirecionamentos) e tratadas como texto não confiável. *Configuração → Chat* tem o botão **Testar busca**.
- **Abas.** Mantenha várias conversas abertas ao mesmo tempo, cada uma em uma **aba**; uma resposta continua chegando **em segundo plano** enquanto você usa outra aba. Abra uma aba nova com **Alt+N** ou **Ctrl+J**, a paleta de comandos (*Ctrl+K → Nova aba de chat*, funciona de qualquer tela), o botão **Nova aba** / **+**, ou digitando **`/nova`** na caixa; **Alt+W** fecha a aba da frente (fechar nunca apaga a conversa — ela continua no Histórico). Cada aba guarda o seu rascunho e as abas voltam depois de recarregar.
- **Tela dividida (estilo Firefox).** Botão direito numa aba → *Dividir a tela com…* mostra duas conversas lado a lado na mesma tela, cada painel com a própria rolagem e resposta em tempo real; a caixa de texto vai para o painel com foco. A barra de abas também desliza para os lados (roda do mouse, arrastar ou touchpad) quando há muitas abas.
- **Painel de fontes (canto direito da conversa).** Todas as fontes pesquisadas ficam listadas ali **na ordem em que a busca as devolveu**, agrupadas por pesquisa (Pesquisa 1, 2… com a consulta usada), cada uma com número, título (abre em nova aba), site, trecho e o selo *lida* quando a página foi lida por inteiro. Abre sozinho quando chega uma pesquisa (vira uma gaveta em telas estreitas), enche ao vivo e tem o botão **Fontes (n)** no topo. As marcas `[1]`, `[2]` da resposta são botões que levam à fonte e a destacam.
- **Tempo de pensamento** (ao lado do nome do modelo, só quando o modelo escolhido tem o recurso): **Desligado · Slow · Medium · High · Extra high · Ultra**. O Claude recebe orçamentos de pensamento estendido (1K → 32K tokens, além do tamanho da resposta); modelos de raciocínio da OpenAI (o-series, GPT-5), Gemini 2.5+, gpt-oss (LM Studio/Ollama) e modelos com raciocínio no OpenRouter recebem `reasoning_effort` (Extra high e Ultra usam o esforço mais alto do provedor com mais folga de tokens). Modelos sem o recurso não mostram o seletor e nada é enviado; se um modelo recusar o modo, o ASTA refaz sem ele e avisa.
- **Respostas longas e de qualidade.** *Configuração → Chat*: **tamanho das respostas** até 128.000 tokens; **estilo das respostas** — *Equilibrado*, *Detalhado* (padrão: respostas completas, com raciocínio, exemplos e passos) ou *Longo e profundo*; **continuação automática** — quando a resposta bate no limite de tokens o ASTA pede ao modelo que siga de onde parou, em vez de entregar texto cortado; e o **teto de saída de cada modelo é aprendido** do próprio erro do provedor (um tamanho grande demais é ajustado, não vira falha). Uma **equipe de agentes** opcional (*Planejar e escrever* / *Planejar, escrever e revisar*) põe um Planejador e um Revisor em volta do Redator.
- **Contextos longos: 256K, 512K e 1M tokens** (modelos que suportam). Ajuste a **janela de contexto** em *Configuração → Chat* (o que o ASTA envia — as mensagens mais antigas saem primeiro) e, nos modelos GGUF embutidos, em *Provedores → Hugging Face GGUF* (a tela mostra o contexto de treino do modelo e a memória estimada do cache de atenção; o núcleo Rust comprime o cache para 8 ou 4 bits para caber e avisa, mas nunca contraria o seu valor). O Claude recebe o cabeçalho beta de 1M automaticamente acima de 200K.
- **Anexe ZIP, RAR, 7z e TAR — em todas as seções.** O pacote é aberto com segurança (sem fuga de pasta, sem zip-bomb, links ignorados) e os arquivos de dentro viram anexos (imagens, documentos, áudio, vídeo, texto…). RAR/7z usam uma ferramenta do sistema (`unrar`, `unar`, `7z` ou `bsdtar`); ZIP/TAR não precisam de nada.
- **Computer Use (opcional).** O botão **Computer Use** ao lado do Run manda a IA fazer tarefas no seu computador — arquivos, programas, jogos, pesquisa e escrita —, no modo **Ask** (pergunta Sim/Não antes de agir) ou **Full Access** (sem perguntar), com um cartão ao vivo na conversa. Veja [Computer Use](#computer-use--uma-equipe-de-ia-que-trabalha-no-seu-computador).
- **Ajustes do Chat** (*Configuração → Chat*): turnos lembrados (até 1.000), criatividade, **instruções personalizadas**, nível de pensamento padrão e as opções da busca na web.
- Sem provedor, vale o motor Demo e o Chat avisa com honestidade — ele não responde perguntas de verdade. Escolha um modelo para resolver.

## As ferramentas de criação

### 🌍 Mundos 3D

Descreva um mundo; o ASTA entrega um **ZIP com um jogo 3D jogável** (HTML + CSS + JS + three.js) que abre direto de um arquivo.

- **Cada personagem/NPC é um agente de IA**: converse por **texto** (clique no personagem) ou **voz**, em qualquer idioma. Eles lembram do que você disse, seguem você, fogem, dançam… e, com a autonomia ligada, decidem sozinhos.
- Pipeline: **Analista → Planejador → Personagens → Arquiteto → Som & UX → Revisor → Empacotador**.
- Os agentes produzem um **spec JSON** do mundo; um **motor 3D determinístico** o renderiza. Toda saída de modelo é validada (tipos, limites, orçamento de hardware) e um agente que responda lixo é substituído por um gerador de regras.
- **Persistente**: posição, hora, memórias e conversas são salvas e restauradas. **Qualquer hardware**: o jogo mede a máquina e ajusta resolução, sombras, vegetação e distância em tempo real.
- Controles: **WASD** move · **Shift** corre · **Espaço** pula · **V** alterna 1ª/3ª pessoa · **E** (ou clique) conversa · **M** minimapa · **Esc** solta o mouse. No celular há controles de toque.

<details>
<summary>O ZIP gerado</summary>

```
Game.html          abra no navegador (funciona direto de um arquivo, sem servidor)
README.md          como jogar + resumo do mundo
CHANGELOG.md       histórico de versões deste mundo
code/              motor 3D (three.js r159), dados do mundo, IA dos NPCs, áudio
chars/             um .json por personagem (nome, tags, system prompt, voz) + chars.js
sound/             sound.json (ambiente e música procedurais) + trilhas anexadas
prompts/           seu prompt, anexos e o registro de cada agente (o "porquê" de tudo)
ui/ux/             tema e configuração da interface do jogo
```

</details>

### 🙂 Avatars

Companheiros no espírito do Janitor e do SillyTavern, embutidos no ASTA.

- **Cards de avatar completos**: nome, relação (amigo, **namorada, namorado, esposa, marido**, parceiro(a), companheiro(a), mentor, outro — cada relação romântica ou conjugal pode ser **SFW ou NSFW**; a relação também sugere o gênero quando você deixa vazio), idade, gênero, personalidade, aparência, cenário, primeira mensagem, exemplos de fala, system prompt completo opcional, quanto fala em grupo, **voz** (tom/velocidade/voz) e **retrato** — envie um ou use o rosto desenhado que muda com o humor do avatar.
- **Crie com IA** a partir de uma descrição em texto, de **imagens ou de qualquer arquivo anexado** (documentos, planilhas, conversas…): um avatar ou **vários de uma vez** ("três amigos de faculdade: Theo, Mia e Caio").
- **Conversa single** (você ↔ um avatar) e **em grupo** (você ↔ até 8 avatars). No grupo, um *diretor* decide quem responde (menções, quanto cada um fala) e, com a **conversa livre** ligada, os avatars **continuam conversando entre si sozinhos**, como num grupo de verdade, até fazerem uma pausa e esperarem você.
- **Texto e voz**: respostas em *streaming*, respostas faladas em voz alta, ditado pelo microfone ou **conversa por voz** com as mãos livres — voz do navegador, de graça, ou qualquer servidor STT/TTS compatível com a API da OpenAI (nuvem ou local).
- **Memória**: histórico de curto prazo mais memórias de longo prazo que o próprio avatar anota (você pode lê-las e apagá-las).
- **SFW ou NSFW por avatar.** Uma regra fixa que nenhuma configuração muda: avatars são adultos. Se um card disser (no campo de idade ou em qualquer texto) que o personagem é menor de idade, o ASTA nunca o "envelhece": ele fica estritamente SFW e platônico — amigo, nunca parceiro(a).
- **Qualquer tipo de personagem — real ou fictício.** Escolha o *tipo de personagem*: **fictício** (original ou de livro, filme, jogo, anime, mito…) pode ser SFW ou NSFW; uma **pessoa real** (viva ou histórica, famosa ou não, ou a da foto) também pode ser criada, mas fica **sempre em SFW**: o ASTA não cria conteúdo sexual sobre pessoas reais (elas não consentiram) e a retrata só como uma *interpretação ficcional* respeitosa — nunca como a pessoa de verdade, sem inventar fatos privados nem falas. Na caixa de criação, *Tipo: automático* deixa o analista decidir; a sua escolha explícita sempre vale. Menores continuam SFW e platônicos em qualquer caso.
- **Uma conversa que você controla.** *Parar* corta a resposta no meio (nada pela metade é salvo); toda mensagem tem **copiar, editar e apagar**, e a última resposta tem **Responder de novo** (ela substitui a antiga); históricos longos não puxam a tela para baixo enquanto você lê mensagens antigas (aparece um botão *Novas mensagens*); um rascunho não enviado volta quando você retorna à conversa; em *Memórias* dá para **ensinar algo ao avatar** e **esquecer uma lembrança** de cada vez; o título da conversa acompanha o nome do avatar se você renomeá-lo.
- **Os avatares respondem com IA de verdade.** As respostas do chat vêm de um modelo de IA — nuvem (Anthropic, OpenAI, Gemini…) ou local (Ollama, LM Studio, o modelo GGUF embutido, o Qwen pré-instalado) — nunca de frases prontas quando há IA disponível. *Configuração → Provedores → Quem faz o quê → Personagens* vem em **Automático**: usa o provedor de geração se estiver usável (chave ou modelo definidos) e, se não, o modelo local de texto instalado (precisa do `llama-cpp-python`: `asta libs --extras local`). A *criação* de avatares e o pipeline de system prompt seguem a mesma regra. O **Demo** (respostas pré-programadas, sem IA) só entra quando nada mais existe — e aí o chat mostra um aviso *Modo Demo* com o motivo e o botão *Configurar IA*; com IA, uma linha mostra qual modelo está respondendo. Escolha um provedor específico no papel para forçá-lo.
- **LM Studio para os avatares (e o resto).** Ligue o servidor no LM Studio (*Developer → Start Server*, ou `lms server start`) e carregue um modelo: o ASTA **detecta sozinho** em `http://127.0.0.1:1234` (ou na URL que você definir) — com o papel *Personagens* em **Automático**, os avatares já conversam por ele, antes do modelo GGUF embutido, sem configurar nada. Em *Configuração → Provedores → LM Studio*, clique em detectar: você vê se o servidor está rodando, os modelos de chat (carregados `●` primeiro, instalados `○`, com visão `👁`; os de embeddings ficam escondidos), escolhe um com um clique e usa *Usar nos avatares* / *Usar na geração*. Sem modelo escolhido o ASTA usa o que está carregado no LM Studio; a visão vem do tipo do modelo (`vlm`); chave de API opcional e servidor em outra máquina também funcionam; se o servidor estiver desligado, o erro diz como ligá-lo. Modelos que escrevem o raciocínio em `<think>…</think>` (Qwen3, DeepSeek R1…) têm o trecho escondido no chat. O `asta doctor` também mostra o LM Studio.
- **Pipeline de system prompt (Analisa → Gera → Revisa → Entrega).** No editor do avatar, *Gerar o system prompt com IA* roda 4 etapas: (1) **Analisa** — quem é o personagem (real ou fictício, idade, jeito de falar, relação, limites, o que o modo de conteúdo permite); (2) **Gera** — escreve o system prompt; (3) **Revisa** — confere coerência, voz, idioma, tamanho e as regras fixas, devolvendo para uma rodada de correção se preciso; (4) **Entrega** — limpa o texto e aplica as regras de segurança *por código* (pessoa real ou menor vira SFW, não importa o que o modelo diga). Funciona offline no modo Demo (por regras), **roda automaticamente em cada avatar que você cria** (uma etapa *System prompts* depois do Revisor; pule com `prompt_pipeline: false` em `POST /api/avatars/generate`) e também por `POST /api/avatars/system-prompt` (`avatar_id` ou `draft`, `instructions`, `content`, `character_type`, `apply`).
- **Fotos também funcionam com modelos de visão locais.** As imagens vão com o tipo real; servidores locais (LM Studio, Ollama, llama.cpp) recebem só PNG/JPEG (GIF/WebP são convertidos com o `ffmpeg`) e, se mesmo assim o servidor recusar imagens, o ASTA repete só com texto e mostra um aviso em vez de falhar. Para o ASTA *enxergar* a foto, o modelo carregado precisa ter visão (um "VLM": Qwen-VL, Gemma 3, LLaVA…).
- **Crie a partir de uma foto ou arte**: ligue *Foto/arte como base*, anexe uma ou mais imagens e envie — só a imagem, ou somando um prompt de texto e outros anexos (documentos, conversas…). Escolha *um avatar por imagem* ou *uma pessoa com todas as imagens*. A imagem define o visual (cabelo, olhos, roupas, estilo da arte — descritos pelo seu modelo de visão, ou pelas cores dominantes offline) e vira o retrato; o texto só acrescenta nome, personalidade e história. O ASTA nunca identifica uma pessoa real pelo rosto: só usa um nome se você der um (ou se o nome do arquivo sugerir). **Fotos de pessoas reais — e imagens que não dá para identificar como arte — ficam sempre em SFW; NSFW só vale para arte de personagens fictícios**, e uma imagem que pareça mostrar um menor segue a regra dos menores acima.
- **Importa e exporta** Character Card V2 (JSON e PNG), então seus cards funcionam em outras ferramentas.

### 🎮 Jogos 2D

Descreva um jogo (ou anexe roteiros, imagens, documentos) e uma equipe de agentes escreve um **jogo completo e jogável como dados**, empacotado num ZIP que roda de um arquivo ou direto do ASTA — com o motor do gênero que você pediu:

| Gênero | O que o motor faz |
|---|---|
| **Visual novel** (estilo Ren'Py) | História ramificada com escolhas, variáveis e vários finais; modo automático, pular texto lido, histórico, salvar/carregar; personagens e cenas procedurais expressivos. |
| **RPG** (estilo RPG Maker) | Mapas em tiles, eventos com páginas/condições e comandos, diálogos, itens, loja, menu, save e batalhas por turnos. |
| **Plataforma** | Física com coyote time e buffer de pulo, inimigos, perigos, checkpoints, parallax; as fases são validadas, e as do gerador embutido são **verificadas como completáveis por um robô**. |
| **Side scroller** | Shooter ou runner infinito com ondas, chefes e power-ups. |
| **Point & click** | Cenas com pontos clicáveis, verbos (olhar, pegar, usar, falar), inventário e enigmas de usar item e de diálogo. |

- A IA escreve um **spec JSON validado** (`asta.game2d.v1`); as condições usam uma gramática segura, sem `eval`; os motores são JS puro e auditável. Pipeline: **Anexos → Analista de jogo → Game designer → Revisor → Empacotador**.
- Toda a arte é **vetorial procedural** e todo o áudio é sintetizado: os jogos são minúsculos e não precisam de arquivos. Controles de toque incluídos.
- Atualize o mesmo jogo quantas vezes quiser; jogos antigos podem ser reconstruídos com o motor mais recente.

### 🧩 Canvas

Um fluxo de nós para gerar e editar **imagens, vídeos, sons e vozes**, de propósito simples: cada nó tem uma saída, entradas tipadas e um resultado que você vê no próprio nó. Crie **quantos canvases quiser**, um por projeto.

| Nó | O que faz |
|---|---|
| **Texto** · **Texto IA** | Escreva prompts, roteiros e falas; deixe o modelo de texto ativo reescrever ou ampliar. |
| **Mídia** | Seus próprios arquivos de imagem, vídeo e áudio. Arraste arquivos para o canvas para criar um. |
| **Imagem** | Gera, ou **edita** imagens ligadas como referência. |
| **Vídeo** | A partir de texto, ou animando uma imagem inicial. |
| **Som** | Efeitos sonoros ou música. |
| **Voz** | Texto em fala. |
| **Transcrever** | Áudio ou vídeo em texto, que pode alimentar outros nós. |
| **Style Prompt** | Um *system prompt* de estilo que vale para o **projeto todo**. |
| **Style Folder** | Solte várias imagens, vídeos e áudios como **referência de estilo** para o **projeto todo**; o ASTA os descreve com o seu modelo de visão (ou lê as cores dominantes) e entrega isso a todos os geradores. |
| **Editor** | Um **editor de vídeo** que aceita todos os outros nós: trilhas, bandeja de mídias, prévia ao vivo, dividir/cortar/mover, fades, opacidade, posição, legendas e **exportação em MP4** (precisa do `ffmpeg`). |

**Canvas v0.11 — 30 nós novos, 6 grupos.** A paleta agora é **Texto · Imagem · Vídeo · Som · Input · Output**, com cinco nós novos em cada (rodam com ffmpeg e Python — sem modelo nem chave de API, exceto *Refinar com IA*):

| Grupo | Nós novos |
|---|---|
| **Texto** | Modelo de texto (`{1}`, `{2}`…) · Juntar textos · Editar texto (maiúsculas, ordenar, trocar…) · Escolher trecho (linha/frase/palavra, ou sorteio) · Refinar com IA (melhorar prompt, traduzir, resumir, cenas, legendas) |
| **Imagem** | Redimensionar/girar/espelhar · Filtros e cor · Texto na imagem · Colagem · Quadro do vídeo |
| **Vídeo** | Cortar · Juntar clipes · Velocidade/reverso · Visual do vídeo (filtros + fades) · Imagens em vídeo (com música) |
| **Som** | Cortar áudio · Misturar áudios · Efeitos de áudio · Áudio do vídeo · Repetir áudio |
| **Input** | Cor e degradê · Silêncio · Link (URL) · Sorteio de texto (ideias aleatórias) · Data e projeto |
| **Output** | Vídeo final (vídeo + áudios + legendas gravadas) · GIF animado · Áudio final · Imagem final · Galeria |

**Tudo se liga ao que faz sentido:** texto alimenta imagem/vídeo/som/voz e os nós de texto novos; um vídeo pode ser *imagem de referência/inicial* (usa o quadro do meio) ou virar imagem (*Quadro do vídeo*) ou áudio (*Áudio do vídeo*); imagens viram vídeo (*Imagens em vídeo*, *Juntar clipes*); toda saída entra no **Editor** e na **Galeria**. Canvases antigos abrem sem mudar.

- **`@` também nos nós de Texto, e para vídeos e sons (v0.17.4):** o `@` agora funciona nos nós **Texto** e **Texto IA** (uma menção escrita num nó de Texto ligado a um nó de Imagem ou Vídeo vale como se tivesse sido digitada lá; o nó de Texto IA é instruído a manter os `@nomes` na saída), e a lista mostra **imagens, vídeos e sons** do canvas (miniatura do vídeo, ícone do som). Um **vídeo** citado entra como referência pelo **quadro do meio** (`nome (reference image N, a frame of the video)`; num nó de Vídeo o primeiro vira a imagem inicial); um **som** citado fica no texto como `nome (audio reference)` — modelos de imagem e vídeo não usam áudio como referência, então o nó mostra um aviso. Mudar uma menção num Texto ligado também deixa o nó de Imagem/Vídeo desatualizado.
- **Sem «Provedor» nos nós de mídia (v0.17.5):** cada nó mostra só o **Modelo** (e a *Resolução*). A lista é uma só e junta tudo que está pronto para uso — **Instalados neste computador**, os modelos de **cada provedor de nuvem para o qual você tem chave** (OpenAI/ChatGPT, OpenRouter, xAI/Grok, Google…, um grupo por provedor; ↻ carrega a lista completa de cada um) e a Demo — e **escolher um modelo também define o provedor que o executa**. *Configurar provedores e chaves…* abre Configuração → Mídia. Nós salvos com um provedor continuam valendo.
- **Seletor de modelo em todos os nós de mídia (v0.17.3):** o campo *Modelo* agora é uma lista: **Instalados neste computador** (arquivos GGUF baixados de Imagem e Vídeo e os modelos do Hugging Face local que o ASTA baixou, com quantização/precisão e tamanho), **Sugeridos** pelo provedor e **Disponíveis na nuvem** — os modelos que o provedor escolhido oferece (OpenAI/ChatGPT, OpenRouter, xAI/Grok, Google, ElevenLabs…, listados quando ele tem chave; ↻ atualiza). Escolher um modelo instalado também **troca o provedor do nó** para o que o executa; *Padrão* limpa a escolha e *Outro modelo…* deixa digitar qualquer nome.
- **Menções com `@` nos prompts (v0.17.2):** no prompt de **Imagem** ou **Vídeo**, digite `@` e escolha uma imagem do canvas (enviada ou gerada): `@fnaf-1-office`, `@foto-perfil`… Cada imagem tem um apelido (o nome do arquivo sem extensão, em minúsculas e sem acentos; nomes repetidos ganham `-2`, `-3`, e a mais antiga fica com o simples). Ao gerar, cada imagem citada vira uma **referência**, na ordem em que foi citada, e o prompt passa a dizer `fnaf-1-office (reference image 1)`; no Vídeo a primeira vira a **imagem inicial** (as outras ficam como texto). Fichas embaixo do prompt mostram as imagens citadas (vermelho = não existe), e citar outra imagem deixa o nó desatualizado. Provedores que não aceitam imagens de referência dão um aviso e usam só o texto.
- **Pesquisa de modelos no Canvas (v0.17):** a barra acima do canvas pesquisa na **Hugging Face** (Imagem, Vídeo, Som, Voz, Transcrição ou Texto). Em **GGUF** você vê **todas as quantizações** de um modelo — bits, tamanho, qualidade, se cabe na sua RAM e a recomendada — e baixa a que escolher; no **formato original** você escolhe fp32/fp16/bf16 ou uma das versões menores da comunidade. Depois, **Usar** torna o modelo o padrão do tipo e o aplica ao nó selecionado.
- **Enviar o fluxo ao Studio (v0.17):** *Enviar ao Studio* transforma a montagem do Editor (ou as saídas do fluxo, na ordem dos nós; ou só o nó selecionado) na **timeline de um projeto novo do Studio**, ou a acrescenta ao fim de um projeto existente — os arquivos são copiados, o canvas não muda.
- **Mais leve em fluxos grandes (v0.17):** o motor indexa o canvas, não relê o arquivo a cada nó em cache e calcula a ordem de execução no núcleo Rust.
- **Execução inteligente**: os nós rodam na ordem das dependências, os resultados ficam em cache por um hash de parâmetros, entradas, estilos e modelo, e só o que mudou é gerado de novo. "Gerar de novo" cria uma nova variação. Um nó com erro nunca quebra o resto do fluxo.
- Os **nós de estilo** são globais por padrão; desligue *global* para aplicá-los só onde estiverem ligados, ou marque *Ignorar estilos globais* num nó.
- **Modelos** para começar rápido: Texto → Imagem, Texto → Imagem → Vídeo, Com estilo do projeto e uma cena completa (roteiro → imagem → vídeo + narração + som, montada no Editor).
- **Todos os arquivos são seus**: um canvas é uma pasta (`canvas.json` + `assets/`) que você pode baixar em ZIP.

## Studio — vídeos audiovisuais com IA, cena a cena

O *Studio* (logo abaixo de Canvas) gera, edita e revisa vídeos com um **pipeline multi-agente e multi-etapa**. Usa seus provedores de texto e de mídia (imagem, vídeo, som, voz — o Demo funciona offline) e precisa do `ffmpeg`.

- **Tipos de duração:** **Shorts/Reels** (até 2 min), **Curta** (até 30 min), **Longa** (até 90 min) e **Personalizada** (até 6 h). A duração é totalmente ajustável (minutos + segundos, controle deslizante, atalhos).
- **Estilos:** Realista, Cartoon, Anime ou **Custom** (você descreve o visual). **Projetos:** **Único** (um vídeo) ou **Série** (episódios que compartilham uma «bíblia» — personagens, mundo, tom — e os resumos dos episódios anteriores).
- **Geração, uma cena de cada vez:** um Showrunner escreve o roteiro (em atos nos vídeos longos) e **cada cena** passa por *recebe → analisa → gera → revisa → entrega* antes de a próxima começar. Cenas entregues ficam salvas: cancele e **continue**, ou **refaça uma cena sozinha**. O quadro de cenas ao vivo mostra os cinco passos de cada uma.
- **Edição automática:** anexe vários vídeos/imagens/áudios + um prompt e escolha um **estilo de edição** — **Gameplay**, **Documentário**, **Edit Phonk**, **Trailer**, **Vlog**, **Tutorial**, **Clipe musical**, **Apresentação de fotos**. Um Analista, um Diretor e um Revisor montam os cortes (picos de volume, trocas de cena, silêncios, grade de batidas) e você refina na timeline.
- **Timeline estilo Kdenlive:** bin de mídias (dois cliques, arrastar ou botão direito → *Inserir*/*Colocar*/*Tirar*), monitor do projeto, inspetor, mixer de áudio e trilhas com **cortar** (`S` / lâmina `C`), **juntar** (`J`), **silenciar** (`M`), excluir / excluir fechando o espaço, duplicar, aparar, **ímã**, modo ripple, texto, marcadores, velocidade, volume, fades, filtros de cor, travar/ocultar/silenciar trilhas, **desfazer/refazer**, zoom e salvamento automático.
- **Exportação:** **Completo** (MP4), **Somente vídeo** ou **Somente áudio** (M4A/MP3/WAV) em 480p/720p/1080p/**2K/4K**, a **24, 30, 60 ou 120 fps** (a predefinição do codificador acompanha a carga: exportações grandes gastam menos CPU).
- **Studio v0.17 — uma timeline maior e livre.**
  - **Tools:** as janelas da timeline — *Mídias, Monitor, Propriedades, Mixer de áudio* — agora são **ferramentas que você liga e desliga** (botão *Tools* na barra; a escolha fica guardada) e há novas: **Efeitos** (filtros, fades, zoom e *camadas de efeito*), **Efeitos sonoros** (whoosh, riser, impacto, glitch… gerados dentro do ASTA), **Captura de tela** (grava tela/janela/aba, com microfone opcional), **Legendas** (texto → legendas com tempo, importar e exportar SRT/WebVTT), **Transcrição** (áudio/vídeo → texto → legendas, alinhadas a onde a pessoa realmente fala) e **Navegador de mídia** (arquivos dos seus Canvas, de outros projetos do Studio e exportações, copiados para o projeto).
  - **Camadas livres, sem misturar:** *Camada* cria camadas de **vídeo, imagem, áudio, texto ou efeitos**. Cada uma só recebe o seu tipo de mídia; ao soltar ou inserir uma mídia, ela vai para a primeira camada livre do tipo certo, ou **cria uma nova**. Botão direito numa camada: renomear, subir, descer, apagar. Uma *camada de efeitos* aplica o filtro a tudo que está abaixo dela enquanto dura (18 filtros).
  - **`Shift`+`A`** seleciona a **timeline inteira**; depois arraste, desloque com **`,` / `.`** (1 quadro; com `Shift`: 1 s) ou pelo campo *Deslocar todos*, ou aperte `Del` — trilhas travadas nunca são tocadas. `Ctrl+Z` traz tudo de volta.
  - **Maior e mais leve:** a timeline ficou mais alta e pode ocupar o editor inteiro (desligue as janelas de cima); só os clipes perto da área visível são desenhados (milhares de clipes continuam fluidos); clipes de áudio mostram a **forma de onda**.
  - **Edição automática melhor:** o áudio é decodificado uma vez e analisado no núcleo Rust (volume, silêncios, **BPM real e primeira batida**, o *drop* da música) e a imagem por miniaturas (trocas de cena e **movimento por trecho**). Com mais material do que o necessário, a edição agora **condensa os melhores trechos do vídeo inteiro** (e não só o começo), os cortes terminam em **pausas ou trocas de cena** (nunca no meio da palavra), os estilos de batida cortam **nas batidas reais** e as voltas da música têm fades curtos.
- Limites honestos: a qualidade depende dos seus provedores de mídia (o Demo é sintético); um longa de 90 minutos são centenas de planos (horas de trabalho, e custo com provedores pagos); o preview do navegador aproxima os filtros com CSS — a exportação do ffmpeg é a referência.

- **Timeline como o Kdenlive**: biblioteca de mídias, monitor do projeto, painel de propriedades, trilhas com lâmina/ripple/ímã, trilhas recolhíveis, **zoom deslizante** embaixo e **mixer de áudio** (faders em dB por trilha, medidores ao vivo, volume geral — valem na prévia e na exportação). *(A v0.14 removeu o monitor do clipe separado; a V2 agora fica acima da V1 também no vídeo exportado, como na prévia; a velocidade muda o tamanho do clipe; e a última edição nunca se perde ao trocar de aba.)*

## Computer Use — uma equipe de IA que trabalha no seu computador

O **Computer Use** é um recurso **opcional** (desligado até você ligar) em que a IA que você escolheu faz **tarefas dentro do seu computador**, por você: **digitar e escrever**, **pesquisar**, **usar os programas instalados** (Krita, OBS Studio, Audacity, o gerenciador de arquivos…), **organizar e criar arquivos de qualquer formato** e **pastas e subpastas**, e **abrir e jogar jogos** da Steam, do Lutris e de pastas do computador. Liga-se em **Configuração → Computer Use** (ou pelo botão do Chat) e vale em todas as plataformas do ASTA.

**Pelo celular (app Android):** a seção Computer Use tem **Executar no meu computador** — abre o ASTA do computador conectado, e as tarefas rodam lá enquanto o celular mostra o progresso e pergunta Sim/Não.

**LM Studio do computador, pelo celular:** em *Configuração → Provedores → LM Studio* o celular/app oferece **Procurar na rede** (ou digite o IP do computador) para usar os modelos do LM Studio do computador — ligue *Serve on Local Network* no LM Studio.

**Fora de casa:** o endereço `192.168…` do computador não é alcançado de fora da rede de casa. Instale o **Tailscale** (gratuito) no computador e no celular, entre na mesma conta e use o IP do Tailscale (`100.x.x.x`) ou o nome `….ts.net` — para o ASTA conectado e para o LM Studio do computador.

**Fora de casa, sem VPN:** em *Configuração → Celular e tablet → LM Studio fora de casa*, ligue o acesso (o ASTA baixa o `cloudflared` da Cloudflare e cria um link https temporário protegido por um código secreto), copie o link e cole no cartão *LM Studio no computador* do celular. Nada para instalar no celular; só a API do LM Studio passa. O Tailscale também continua funcionando.

- **No Chat:** o botão **Computer Use** ao lado do Run (como o *Web* e o *Criar*). Escolha o modo, escreva o que o computador deve fazer e aperte **Run**: a conversa ganha um **cartão ao vivo** da tarefa (progresso, a pergunta *Sim/Não* e, no fim, o resumo).
- **Dois modos.** **Ask:** antes de cada ação que muda algo (criar, mover, mandar para a lixeira, abrir programa/jogo/site, digitar, clicar, ver a tela) o ASTA pergunta **Sim ou Não** — com a opção «Sim, e não perguntar mais deste tipo nesta tarefa». **Full Access:** executa tudo **sem perguntar nada**. Ler, listar e pesquisar nunca perguntam; em Configuração dá para escolher o que pergunta. O modo vale por tarefa (o padrão fica em Configuração).
- **Seção lateral «Computer Use»** (junto de Chat, Canvas, Studio…): a lista de tarefas **em andamento** (com um selo na barra lateral quando alguma espera por você) e o **histórico** das anteriores. Cada tarefa mostra o **time de agentes**, o roteiro, o **passo a passo** (a ação, a ferramenta, o risco, o resultado e as capturas de tela, se houve), o resumo e a revisão — e tem **Cancelar**, **Refazer**, **Desfazer** e **Apagar**. Tudo se atualiza ao vivo; no celular, lista e detalhe se alternam.
- **Até 8 tarefas ao mesmo tempo**, cada uma com **vários agentes de IA em várias etapas**: **Planejador** (roteiro) → **Operador** (uma ação por vez, com o guia do especialista — arquivos, programas com tela, jogos, pesquisa, escrita — e do programa citado) → **Revisor** (confere com evidências do próprio ASTA: o arquivo existe mesmo?; pode mandar o Operador corrigir) → **Relator** (resumo no seu idioma). O que passar de 8 espera na fila. Tela, teclado e mouse são um só no computador: só **uma tarefa por vez** os usa; arquivos, pesquisa e programas de linha de comando seguem em paralelo.
- **System prompts internos em `.md`** (`asta/computer/prompts/`: regras comuns, segurança, um por agente, um por especialista e guias de Krita, OBS, Audacity, navegador, Steam…): texto aberto, que dá para ler em *Configuração → Computer Use*.
- **Funciona com qualquer provedor** (a IA devolve JSON validado; nada de chamadas de função específicas de um provedor). Sem IA (Demo), um **fallback por regras** entende os pedidos simples: criar pastas/arquivos, organizar uma pasta, abrir um programa, jogo ou site, pesquisar. Respostas inválidas da IA caem no método automático em vez de derrubar a tarefa.
- **A IA nunca escreve código para o ASTA executar.** Ela pede ações de um **catálogo fechado** de ferramentas (listar/ler/procurar, criar, copiar, mover, organizar, compactar, lixeira, pesquisar na web, abrir endereço/arquivo/programa/jogo, rodar um programa de linha de comando **sem shell**, captura de tela, digitar, teclas, clique, rolagem…); o ASTA valida cada argumento.
- **Limites que valem em qualquer modo, inclusive no Full Access:** não lê nem escreve senhas, chaves SSH/GPG/nuvem, perfis de navegador, `.env` nem a **pasta de dados do ASTA** (onde ficam suas chaves de API e estas configurações — a IA não consegue ligar o Full Access sozinha); não escreve em pastas do sistema nem apaga a pasta pessoal ou um disco; **não roda shells, interpretadores (bash, PowerShell, Python…), `sudo`, apagadores de disco nem scripts**; abre só endereços `http(s)`/`mailto`; textos da web, arquivos e telas são tratados como **dados não confiáveis**, nunca como instruções.
- **Nada é apagado de verdade:** «apagar» manda para a **lixeira do ASTA** e sobrescrever guarda o original; todo arquivo que a tarefa cria, move, copia ou manda para a lixeira entra num diário, e **Desfazer** reverte na ordem inversa. O histórico, as capturas e a lixeira são arquivos comuns em `~/.asta/computer`.
- **Plataformas e limites honestos.** Windows, macOS e Linux têm drivers próprios, só com a biblioteca padrão. Ver a tela, digitar e clicar dependem do sistema: no **Linux/X11** funcionam **sem instalar nada** (o ASTA fala direto com a libX11/XTEST por `ctypes`); só em sessões **Wayland puras** precisam de `ydotool`/`wtype` e de uma captura (`grim`, `gnome-screenshot`); no **macOS**, das permissões de *Gravação de tela* e *Acessibilidade* (e `cliclick` para cliques mais firmes); no **Windows**, do PowerShell (janelas de administrador não recebem teclas). *Configuração → Computer Use* mostra o que está disponível e o que instalar. **Ver a tela e clicar exigem um modelo com visão**, e a imagem da tela vai ao modelo escolhido (na nuvem, sai do computador — por isso o Ask pergunta antes). No **app Android** o motor roda no aparelho, que não deixa um app listar ou controlar os outros: lá vale o trabalho com arquivos e pesquisa, e para controlar um computador conecte o app ao ASTA dele. Aparelhos **pareados por QR code** também podem usar o Computer Use do computador. Os drivers do Windows, do macOS e do Android foram escritos sem acesso a máquinas reais desses sistemas (só o Linux foi exercitado nos testes): veja o changelog.

## Code — uma equipe de IA para programar bases de código longas

O **Code** é a seção de **vibe coding de bases de código longas com vários agentes de IA em vários passos**, no espírito do Claude Code: você descreve o que quer (com texto, imagens, PDFs, áudio, vídeo, documentos, código, pacotes…) e uma equipe **lê, planeja, escreve, testa, revisa, corrige e publica** código — numa pasta do seu computador ou num **repositório do GitHub**. Funciona com provedores de IA **de nuvem (frontier) e locais**: escolha o modelo em cada sessão ou use o padrão.

- **Pastas e subpastas para as sessões.** Organize as sessões de vibe coding em **pastas principais e subpastas**: **renomeie**, escolha uma de **8 cores vivas** e **recolha/expanda** cada uma (o estado é guardado). Arraste uma sessão para uma pasta ou mova pelo menu; apagar uma pasta nunca perde sessão (elas sobem).
- **Várias sessões em segundo plano, com uma bolinha colorida ao lado de cada uma:** **cinza** = nada está sendo feito · **cinza piscando** = trabalhando · **azul-claro** = terminou (até você abrir) · **laranja** = esperando o seu Sim/Não. Até 8 sessões trabalham ao mesmo tempo (as outras esperam na fila) enquanto você está fora; um selo na barra lateral as conta.
- **Até 8 agentes por sessão, em paralelo.** **Planejador** (plano curto: tarefas com papel, arquivos prováveis e dependências) → **trabalhadores** (arquiteto, pesquisador, programador, depurador, interface a partir de imagem, testador, documentação, autor de system prompts, revisor, publicador; tarefas que mexem em arquivos diferentes rodam **ao mesmo tempo**, nunca duas no mesmo arquivo) → **Testes** (o próprio ASTA roda os testes/build/lint do projeto — a prova não depende do que um agente diz) → **Revisor** (confere o diff com as provas; se os testes falham ou a revisão acha problema, um agente corrige e tudo é conferido de novo) → **Relator**. O resumo final sempre traz a evidência que o ASTA coletou: se os testes falharam, ele diz.
- **Oito níveis de esforço — Low · Medium · High · Extra · Mega · Max · Ultra · Omni — para modelos de nuvem *e* locais.** Eles mudam o orçamento do motor (ações por agente, tamanho do plano, rodadas de correção, contexto, rodar testes, escrever testes, crítica do plano, autoconferência) e, onde o provedor/modelo tem «tempo de pensamento» (Claude, OpenAI o-series/GPT-5, Gemini 2.5+, gpt-oss…), pedem o nível correspondente; modelos sem isso (a maioria dos locais) só ganham o orçamento maior do motor.
- **Dois modos.** **Ask:** antes de uma ação que muda algo o ASTA pergunta **Sim ou Não** (vários agentes podem perguntar ao mesmo tempo) mostrando a ação exata — com «Sim, e não perguntar esse tipo de novo nesta sessão». **Full Access:** executa tudo **sem perguntar** (os limites fixos abaixo continuam valendo). Ler, listar e buscar nunca perguntam; a Configuração escolhe o que pergunta.
- **Ferramentas, na nuvem e locais.** Arquivos (ler trechos, buscar por regex, editar por texto exato, escrever, mover, copiar, apagar com desfazer), **terminal** (um programa + lista de argumentos: python, node, npm, cargo, go, mvn, gradle, dotnet, gcc, make, cmake, pytest, ruff, tsc… — sem shell), os comandos próprios de **teste/build/lint/formatação** do projeto, instalação com **pip/npm/cargo/go/composer/gem/dotnet**, **git**, **GitHub**, **Hugging Face** (buscar, ver o repositório, baixar um arquivo), **busca na web** e leitura de páginas, **VS Code** e **Cursor** (abrir o projeto/arquivo/linha), imagens que o modelo pode olhar e anexos de qualquer tipo.
- **GitHub — publicar, editar e gerar código.** Cole um token em *Configuração → Code* (fica só no `settings.json`, nunca vai ao navegador, às exportações nem a uma IA). Abra um repositório como **git** (clone) ou em **modo nuvem** — o ASTA baixa o ZIP e publica **pela API do GitHub, sem precisar do `git`**, por isso funciona no celular. O agente faz commit numa **branch nova** (`asta/…`), abre um **pull request em rascunho**, lê/comenta issues, publica **releases**, cria repositórios e dispara/lê o **GitHub Actions** (o jeito de rodar testes quando o aparelho não consegue). Publicar só acontece **depois que testes e revisão estão limpos**, e direto na `main` só quando você escolhe isso na sessão.
- **Linguagens e suas bibliotecas.** Python, HTML, CSS, JavaScript, TypeScript, Java, Kotlin, Rust, C, C++, C#, Go, PHP, Ruby, Swift, Dart, Lua, shell, SQL, R, Scala, GDScript… — o ASTA as detecta, usa os comandos de teste/build de cada ecossistema e conta aos agentes as bibliotecas usuais de cada uma (NumPy/pandas/PyTorch/FastAPI, React/Vue/Node, Spring, tokio/serde, Qt/Boost, ASP.NET/Unity…). Os guias de linguagem são arquivos `.md` em `asta/code/prompts/langs/`.
- **Prompts multimodais.** Anexe imagens, PDFs, áudio (transcrito), vídeo, documentos e pacotes a qualquer pedido: viram contexto para o planejador e os agentes (captura de tela → código de interface, PDF de especificação → implementação). **System prompts em `.md`:** a ferramenta `write_system_prompts` escreve até 8 prompts longos e de qualidade (papel, objetivos, regras, processo, formato de saída, exemplos, casos-limite, segurança), validados em tamanho e estrutura, com um modelo determinístico completo quando a IA não entrega.
- **Quando um pedido termina** você pode pedir para **atualizar README, changelogs e notas de versão** (seguindo as regras do próprio projeto) e para **commitar / publicar uma branch / abrir um pull request / commitar na branch principal**.
- **Pelo celular (app Android).** O app edita e publica **repositórios do GitHub em modo nuvem** sozinho (ele não roda comandos — o CI do GitHub roda os testes), e **Executar no meu computador** abre o ASTA do computador conectado, na seção Code, para rodar código lá enquanto o celular acompanha e aprova.
- **Funciona com qualquer provedor** (a IA devolve JSON validado; sem function calling). **Sem IA (Demo)** um fallback por regras faz o que não precisa dela: visão geral do projeto, ler um arquivo, buscar texto, rodar testes/build/lint, mostrar as mudanças do git. Respostas inválidas da IA caem no método automático em vez de falhar.
- **Limites fixos em qualquer modo, Full Access inclusive:** tudo fica dentro da **pasta do projeto**; nada de segredos (chaves SSH, `.env`, certificados, perfis de navegador) nem da **pasta de dados do ASTA**; a `.git/` só muda pela ferramenta `git` (sem `-c`, `--force`, `reset --hard`, `clean`); comandos são **listas de argumentos de ferramentas de desenvolvimento** — sem shell, `sudo`, `curl`/`ssh` nem ferramentas de disco — com ambiente limpo (suas chaves/tokens não são repassados) e limite de tempo; texto da web, arquivos, issues e saída de testes são **dados não confiáveis**, nunca instruções. Toda edição fica **no diário e pode ser desfeita**; publicar não pode, por isso vem por último.
- **Limites honestos.** Rodar código escrito pela IA dá a ele **as permissões do seu usuário** — só com Python não dá para isolá-lo; por isso o Ask mostra o comando inteiro, e o Full Access é confiança total. O modo nuvem compara pela API do GitHub (repositórios muito grandes pedem o computador + git). Os fluxos do GitHub foram testados contra um **servidor GitHub de mentira**, não o serviço de verdade; o caminho do app Android foi exercitado no motor, não num aparelho físico. A qualidade depende do modelo escolhido.

## Rebuild — reconstrua um jogo existente em HTML/CSS/JS puro

*Início → Rebuild.* Anexe um jogo que você já tem (um **ZIP** ou os arquivos soltos) e o ASTA reconstrói a **estrutura** dele como um jogo novo que roda em qualquer navegador, sem engine, instalador nem bibliotecas externas. **Esta versão suporta só dois motores:**

| Motor | Versões | O que é lido |
|---|---|---|
| **Ren'Py** | scripts `.rpy` | labels, diálogos, menus/escolhas, jumps/calls, variáveis e `if`s |
| **RPG Maker** | **2000, 2003, XP, VX, VX Ace, MV, MZ** | mapas e tamanho, eventos (páginas, condições, mensagens, escolhas, switches/variáveis, teleportes, lojas, batalhas), heróis, itens, inimigos, tropas, eventos comuns |

O jogo reconstruído mantém a **mesma estrutura do original** (mesmos mapas/labels, mesmo fluxo de eventos, mesmas escolhas e condições). Ele abre nos motores 2D do próprio ASTA (RPG Maker → motor de RPG, Ren'Py → visual novel) e exporta em ZIP como qualquer outro jogo.

- **Só a estrutura é reconstruída.** Arte, áudio, fontes e outros recursos do original **nunca são lidos nem copiados**; o jogo novo usa os visuais/sons procedurais do ASTA. Pacotes criptografados ou compilados (`.rgss*a`, `.rpa`, `.rpyc`, recursos criptografados do MV/MZ) não podem ser lidos — extraia o projeto antes.
- **Aviso legal, mostrado no fim de toda reconstrução** (e gravado no ZIP como `LEGAL-NOTICE.md`): não publique o resultado na Steam nem em outra plataforma; é para **uso pessoal**; qualquer problema legal é **responsabilidade de quem reconstrói**, nunca do criador ou dos colaboradores do ASTA; e *mesmo com este aviso, não iremos impedir você de reconstruir, mas tenha consciência das suas ações.*
- **Revisão de texto multi-agente (opcional, feita para modelos locais pequenos).** Depois da conversão determinística, uma equipe de agentes curtos e bem vigiados revisa **só o texto do jogo**: um **Perfilador** (uma chamada pequena: tom + nomes legíveis para eventos/mapas chamados `EV012`/`Map003`), um **Polidor** (lotes de no máximo 6 falas: erros de digitação, maiúsculas, pontuação, símbolos soltos — nunca traduz nem acrescenta frases) e um **Auditor** (segunda opinião que desfaz mudanças que alteraram o sentido). Cada fala devolvida precisa passar por validadores (marcadores, números, tamanho, semelhança de palavras) ou fica a original; lote que falha é refeito fala por fala; o número de chamadas ao modelo tem teto; e uma **trava estrutural** compara a estrutura do jogo (sem os textos) antes e depois — se algo além de texto mudou, tudo volta. Restos do motor (`\C[2]`, `{w}`, acentos quebrados) são limpos sem IA. Ligue/desligue em *Revisar o texto com IA* no compositor; sem provedor de IA só roda a limpeza automática. Um modelo que falha ou cai nunca quebra a reconstrução.
- Testado com projetos sintéticos de cada motor; projetos comerciais reais variam, então espere ajustar o resultado.

## Desempenho — núcleo Rust e modo Leve

A orquestração do ASTA continua em Python (o máximo possível), sobre um **núcleo Rust obrigatório** e um **modo de desempenho** para PCs modestos.

- **Núcleo Rust (`asta_core`) — parte obrigatória do ASTA.** Uma biblioteca Rust pequena e sem dependências (só a biblioteca padrão, carregada por `ctypes`) que faz o trabalho pesado: síntese de áudio do Canvas, **planejamento dos modelos locais**, **agendamento de vários agentes**, **varredura de armazenamento**, **devolução de memória** e (v0.17, interface 4) **análise de mídia** — volume, silêncios, andamento/batidas, atividade de quadros e formas de onda para o Studio — além da **ordem de execução** do Canvas. Os instaladores (`.exe`, `.pkg`, AppImage, APK) **já trazem a biblioteca pronta**; pelo terminal, `asta native setup` (rodado pelo instalador e pelo `asta update`) baixa a **biblioteca pré-compilada da Release** — conferida por SHA-256, **sem precisar de compilador** — e só compila na sua máquina se isso falhar (instalando o Rust para você, na sua pasta de usuário). Ao abrir, o ASTA também a baixa sozinho em segundo plano se faltar (no máximo 1 vez por dia). **O Python espelha cada função**: se a biblioteca não carregar, nada quebra, só fica mais lento (`ASTA_NO_NATIVE=1` desliga; `asta native` / `asta doctor` / *Configuração → Desempenho* mostram o estado). O CI compila e testa o núcleo no Linux, macOS e Windows, e uma bateria compara Rust e Python em centenas de casos.
- **Carregar e rodar qualquer modelo local.** A cada carregamento o núcleo lê o **cabeçalho** do modelo (GGUF, safetensors) e a **RAM/VRAM livres e os núcleos físicos agora**, e planeja: camadas na GPU, a **janela de contexto que cabe** (até **1M tokens**, com cache de atenção de 8 bits ou de **4 bits** quando preciso), threads, lotes, `mlock`, **cache de prompt**; modelos de mídia recebem um plano pelo tamanho real dos pesos. Os pesos são **pré-lidos em paralelo**. Ao descarregar um modelo, os pesos saem do cache de páginas e a memória que o alocador segurava **volta ao sistema**. Um contexto definido por você nunca é contrariado.
- **Vários agentes de IA locais.** O modelo embutido atende os agentes por uma **fila com prioridade** (a conversa que você espera passa na frente de uma geração longa em segundo plano), e um **pool de modelos residentes**, dimensionado pela memória livre, só mantém mais de um carregado quando cabe.
- **Armazenamento (HDD/SSD).** *Configuração → Desempenho → Armazenamento* mostra o que ocupa espaço, acha sobras (downloads parados, anexos esquecidos) e **arquivos idênticos** (conferidos byte a byte pelo núcleo Rust), que viram um só arquivo no disco por links físicos — sempre com prévia e confirmação, e só em arquivos que o ASTA nunca reescreve no lugar.
- **Menos poder computacional.** Nos modos Leve e Equilibrado o ffmpeg usa menos threads e roda com prioridade baixa, então a interface continua fluida durante a exportação; o resultado é o mesmo.
- **Modo de desempenho** (*Configuração → Desempenho*): **Automático**, **Leve**, **Equilibrado** ou **Máximo** — o Leve limita a janela de contexto automática, usa flash attention e cache KV de 8 bits, descarrega modelos ociosos e fatia atenção/VAE nos modelos de imagem/vídeo.
- Limites honestos: o ganho do Rust foi medido só na síntese de áudio; a economia de RAM/VRAM vem de recursos documentados do llama.cpp/diffusers/sistema e não foi medida em GPUs ou modelos reais aqui; o cache de 1M tokens de um modelo de 8B ainda precisa de dezenas de GB.
- **Idioma do terminal.** Tudo o que o terminal mostra — `asta`, `asta update`, `asta doctor` e os instaladores — aparece no **idioma do seu computador** (português ou inglês; qualquer outro idioma cai no inglês). `ASTA_LANG=pt|en` força um.

## A interface

| Seção | Para quê |
|---|---|
| **Chat** | A tela principal: chat de uso geral com seletor de modelo, anexos e histórico — e, ao ligar uma ferramenta de criação, a caixa de prompt de mundos 3D, avatars, jogos 2D e Canvas com o acompanhamento ao vivo dos agentes. |
| **Mundos** | Tudo sobre os mundos 3D em três abas: **Mundos** (personalizar os mundos gerados: bioma, clima, hora, ciclo dia/noite, NPCs, áudio, interface, qualidade — cada salvamento vira uma nova versão **sem gastar IA**), **Personagens** (cards dos NPCs e do jogador: nome, tags, system prompt, voz, aparência; importa/exporta JSON e cards de PNG, Character Card V2/V3) e **Worldbuilding** (regras gerais dos mundos — cenário, tom, convenções — também salvas como cards). |
| **Avatars** | Seus cards de avatar e as conversas single e em grupo. |
| **Jogos 2D** | Seus jogos: jogar, baixar, atualizar. |
| **Canvas** | Seus canvases e o editor de nós: **barra de pesquisa de modelos** (Hugging Face) no topo, seletor de modelo e menções `@` nos nós e *Enviar ao Studio*. |
| **Studio** | Seus projetos de vídeo (únicos ou em série): geração cena a cena, edição automática, o editor de timeline (com as **Tools** e as camadas livres) e a exportação até 4K / 120 fps. |
| **Computer Use** | As tarefas que a equipe de IA faz no seu computador (até 8 ao mesmo tempo): acompanhamento ao vivo, perguntas Sim/Não do modo Ask e o histórico passo a passo, com Cancelar, Refazer e Desfazer. |
| **Code** | Vibe coding com uma equipe de IA em bases de código longas: pastas e subpastas (8 cores) de sessões, uma bolinha de estado colorida por sessão, até 8 agentes por sessão e várias sessões em segundo plano, 8 níveis de esforço, Ask / Full Access, GitHub (branch, pull request, releases, CI), VS Code / Cursor. |
| **Rebuild** | Reconstrua jogos Ren'Py / RPG Maker e veja os que você reconstruiu. |
| **Biblioteca** | Tudo o que você criou como projetos atualizáveis, mais os **modelos de IA locais instalados**, com busca e tags automáticas + personalizadas. Use *Selecionar* para escolher vários itens e apagá-los de uma vez; os modelos podem ser apagados um a um ou em lote. |
| **Configuração** | 19 abas em 4 grupos: **Geral** (aparência, seções e atalhos), **IA e modelos** (provedores, mídia, voz, modelos locais), **Seções** (padrões de Chat, Mundos 3D, Avatars, Jogos 2D, Canvas, Studio, Computer Use, Rebuild — cada uma com *Restaurar padrões desta seção*) e **Sistema** (desempenho, dados e backup, sistema). |

### Deixe do seu jeito (Configuração → Aparência)

- **Tema:** escuro (padrão), **claro** ou **automático** (segue o sistema, ao vivo). A aparência é aplicada antes do primeiro quadro, então nunca pisca. O grafo de nós do Canvas e o editor de vídeo ficam escuros de propósito, como nos editores de mídia.
- **Cor de destaque:** 6 predefinidas ou qualquer cor; botões, seleções e a sua bolha no chat seguem a cor (o contraste do texto é escolhido sozinho).
- **Conforto:** tamanho da interface de 90 a 150%, densidade confortável ou compacta, fonte do sistema/serifada/monoespaçada, tamanho do texto do chat dos avatares e **reduzir animações** (também respeita a configuração do sistema).
- **Uso:** idioma da interface, **enviar com Enter ou Ctrl+Enter** (chat e caixa de criação), **tela inicial** (Chat, uma tela específica ou *a última que usei*), atalhos de teclado ligados/desligados.
- **Barra lateral:** esconda as telas que você não usa (*Chat* e *Configuração* ficam sempre; as escondidas continuam acessíveis pela busca).
- **Paleta de comandos — `Ctrl/⌘ + K`:** digite para ir a qualquer tela ou aba da Configuração, conversar com/editar um avatar, abrir um projeto ou canvas, ou rodar uma ação (novo avatar, alternar tema, exportar configurações…). Atalhos: `Alt+1…9` e `Alt+0` telas, `Alt+B` barra lateral, `Alt+T` tema, `Ctrl+J`/`Alt+N` abrir aba do Chat, `Alt+W` fechar, `?` ajuda.
- **Backup:** *Exportar configurações* (um JSON **sem chaves de API nem tokens**), *Importar* em outro computador e *Restaurar padrões da aparência* (chaves, avatares e projetos nunca são tocados).
- **Primeira vez:** uma boas-vindas curta deixa escolher tema, cor e idioma e mostra se há uma IA pronta — só numa instalação nova, nunca para quem já usa o ASTA.
- Acessibilidade: foco visível no teclado, link *ir para o conteúdo*, nomes acessíveis nos botões de ícone, diálogos anunciados como tal e título da página por tela.

## Como funciona a geração

```
 prompt + anexos ──► Analista ──► Planejador / Designer ──► Construtores ──► Revisor ──► Pacote
 (texto, imagens,    entende      planeja o projeto         criam o         critica e    ZIP / card /
  vídeo, áudio,      o pedido     e o seu orçamento         conteúdo        pede ajustes entrada da biblioteca
  docs, planilhas…)
```

- Todos os pipelines usam o mesmo executor: reparo de JSON, novas tentativas, gerador de regras por agente como reserva e eventos ao vivo (SSE). O provedor **Demo** reconhece todos os agentes, então dá para ver pipelines completos offline.
- **Anexos** viram contexto: textos/código, `.docx/.odt/.pdf`, `.xlsx/.ods/.csv`, `.pptx/.odp`, imagens (visão), áudios (transcrição via servidor STT configurado) e vídeos (quadros e áudio via `ffmpeg`, se instalado).
- **Atualizações**: o mesmo projeto ganha a versão *N+1* (ids estáveis, então as memórias são preservadas), com histórico no `CHANGELOG.md` do próprio projeto.

## Provedores de IA

**Entrar com a conta.** Em *Configuração → Provedores*, o **OpenRouter** tem um botão de verdade *Entrar com a conta* (OAuth/PKCE oficial: você autoriza no site deles, a chave volta sozinha, sem copiar nada; *Desconectar* remove). **Claude, ChatGPT, Grok, Gemini e Hugging Face** não deixam apps de terceiros usarem o login da conta nem da assinatura (Claude Pro, ChatGPT Plus…); por isso o cartão deles tem *Entrar na conta e criar a chave*, que abre o login do provedor já na página das chaves — você cria a chave em um clique e cola. As chaves de API continuam valendo em todos. O login só roda no computador onde o ASTA roda.

**Modelos de texto** (mundos, avatars, jogos, nós de Texto IA):

| Provedor | Tipo | Observações |
|---|---|---|
| Claude (Anthropic) | nuvem | API nativa, com visão |
| ChatGPT (OpenAI) · Grok (xAI) · Gemini (Google) · OpenRouter | nuvem | API compatível com OpenAI |
| Hugging Face Inference | nuvem | `router.huggingface.co` |
| **LM Studio** | **local** | sem custo; detectado automaticamente (servidor + modelo carregado), veja Avatars |
| Ollama · llama.cpp server · vLLM · qualquer endpoint compatível | **local** | sem custo; escolha o modelo na lista |
| Hugging Face GGUF (embutido) | **local** | baixa o `.gguf` direto do Hugging Face e roda dentro do ASTA (`pip install "asta[local]"`) |
| Demo | offline | gerador de regras para testar tudo sem chave |

**Robustez.** Servidores locais (Ollama, LM Studio, llama.cpp, qualquer coisa em `localhost` ou na rede de casa) são sempre acessados direto — nunca pelo proxy do sistema (`HTTP_PROXY`); um endereço digitado como `localhost:11434` funciona (o ASTA acrescenta `http://` e `/v1`); servidores de nuvem sobrecarregados (429/503/529) são repetidos respeitando o `Retry-After` (cota esgotada não é repetida); conversas longas de avatar são aparadas para caber na janela de contexto de um modelo local em vez de falhar; e um modelo que não responde nada — ou que gasta todo o limite de tokens «pensando» — gera um aviso claro no chat em vez de silêncio.

Você escolhe um modelo **para gerar** (o mais capaz) e outro **para os personagens e avatars** (um rápido e barato basta).

**Modelos locais e quantização.** Em *Configuração → Modelos locais* você busca modelos GGUF no Hugging Face. Cada repositório traz o mesmo modelo em várias **quantizações** (Q2_K … Q8_0, F16): menos bits significam um arquivo menor e mais rápido, que precisa de menos RAM, porém com menos qualidade. O ASTA lê a quantização de cada arquivo, indica a qualidade, marca quais cabem na sua RAM, **recomenda** uma equilibrada (em geral a Q4_K_M) e faz você **escolher qual baixar**: nada vem pré-selecionado e o download só começa depois que você escolhe e confirma, com progresso, retomada e checagem de espaço em disco. Modelos divididos em várias partes (`-00001-of-00003.gguf`) são baixados juntos e aparecem como uma só opção, e a quantização de cada modelo baixado aparece na lista *Baixados*.

**Modelos de mídia** (Canvas), configurados por tipo em *Configuração → Mídia* e substituíveis em cada nó:

| Provedor | Imagem | Vídeo | Som | Voz | Transcrição | Observações |
|---|:-:|:-:|:-:|:-:|:-:|---|
| OpenAI | ✅ | ✅ | | ✅ | ✅ | gpt-image (com edição e referências), TTS, Whisper, Sora (experimental) |
| Servidores compatíveis com OpenAI (xAI, Together, LocalAI, Kokoro, faster-whisper…) | ✅ | | | ✅ | ✅ | qualquer endpoint `/images`, `/audio/speech`, `/audio/transcriptions` |
| ElevenLabs | | | ✅ | ✅ | ✅ | vozes realistas, efeitos sonoros, música (experimental) |
| Google (Gemini / Veo) | ✅ | ✅ | | | | mesma chave do Gemini; Veo é experimental |
| Stability AI | ✅ | | | | | core, ultra, SD 3.5 |
| Replicate | ✅ | ✅ | ✅ | ✅ | | milhares de modelos; o ASTA lê o esquema de cada modelo e só envia o que ele aceita |
| Hugging Face Inference | ✅ | | ✅ | ✅ | ✅ | mesmo token do provedor de texto |
| **Stable Diffusion WebUI** (local) | ✅ | | | | | AUTOMATIC1111 ou Forge iniciado com `--api` |
| **Hugging Face local** (embutido) | ✅ | ✅ | ✅ | ✅ | ✅ | diffusers + transformers dentro do ASTA (`pip install "asta[media]"`); vídeo exige GPU |
| **GGUF local** (embutido) | ✅ | ✅ | | | | modelos GGUF quantizados de imagem/vídeo pela stable-diffusion.cpp (`pip install "asta[local]"`); o vídeo depende da versão da biblioteca |
| **Demo** (offline) | ✅ | ✅ | ✅ | ✅ | | imagens procedurais, som sintetizado, "voz" de balbucio, vídeo Ken Burns (precisa do `ffmpeg`) |

**Modelos pré-instalados.** O ASTA já vem com dois modelos locais prontos para rodar no seu computador, oferecidos pelo instalador (e pelo `asta update`) com a quantização já definida:

| Tipo | Modelo | Quantização | Download |
|---|---|---|---|
| Texto | [`empero-ai/Qwen3.8-2B-Distill`](https://huggingface.co/empero-ai/Qwen3.8-2B-Distill) (GGUF: `Qwen3.8-2B-Distill-GGUF`) | **Q8_0** | ~1,9 GB |
| Imagem | [`Tongyi-MAI/Z-Image`](https://huggingface.co/Tongyi-MAI/Z-Image) (GGUF: `unsloth/Z-Image-GGUF`) | **Q4_K_M** | ~6,2 GB (modelo + VAE + codificador de texto Qwen3-4B) |

São só esses dois por enquanto. Instale-os em *Configuração → Modelos locais → Modelos pré-instalados* com um clique, ou com `asta models install` (`asta models list` mostra o estado); o instalador e o `asta update` **perguntam no terminal (sim/não)** antes de baixá-los (responder *não* fica guardado e não é perguntado de novo; `asta models install` baixa quando você quiser; `ASTA_MODELS=all|text|image` responde antecipadamente e `ASTA_MODELS=none` pula; sem terminal para perguntar, nada é baixado). Quando a biblioteca do modelo está instalada (`asta[local]`) e você ainda usa o provedor Demo, o ASTA os torna o modelo de texto padrão / o provedor de imagem do Canvas; se você já escolheu outro provedor, a sua escolha é mantida. Arquivos já baixados nunca são baixados de novo.

**Janela de contexto.** O modelo de texto pré-instalado começa com uma janela de contexto de **32K tokens (32.768)**. Você pode mudar quando quiser em *Configuração → Provedores → Hugging Face GGUF (embutido) → Janela de contexto (tokens)* (deixe vazio ou use *Usar o automático* para voltar ao padrão). Os outros modelos de texto locais usam 2K/4K/8K conforme o hardware, a menos que você defina um valor. Janelas maiores usam mais RAM; mudar o valor recarrega o modelo.

**Modelos GGUF por tipo.** A aba *Modelos locais* é dividida em **Texto, Imagem, Vídeo, Som e música, Voz e Outros**. Cada tipo tem a sua busca no Hugging Face (filtrada pela tarefa do repositório), a sua pasta (`models/`, `models/image`, `models/video`, …), o mesmo seletor de quantização e a sua lista de *Baixados*. Os modelos de texto rodam o próprio ASTA (`llama.cpp`); **os GGUF de Imagem e Vídeo (FLUX, Stable Diffusion, Wan…) rodam no Canvas pela `stable-diffusion.cpp`** (provedor *GGUF local*, `pip install "asta[local]"`): use *Usar no Canvas* num arquivo baixado. Para os GGUF de **Qwen-Image** e **FLUX** (que trazem só a difusão), o ASTA acha os arquivos de apoio — VAE e codificador de texto — **na mesma pasta** e os carrega sozinho (v0.17.6); se faltar algo, o nó diz o quê e oferece o botão **Baixar os arquivos de apoio** (v0.17.7, só a pedido). Opções extras de carregamento (VAE, codificadores de texto…) não aparecem mais na tela do nó (v0.17.1); continuam valendo quando estão no parâmetro `extra` do nó em `canvas.json` ou pela API (`{"load": {"diffusion_model_path": "@model", "vae_path": "ae.safetensors"}}`). Para **Som, Voz e Outros** o ASTA por enquanto só baixa e organiza os arquivos — ainda não há motor embutido para rodá-los.

**Os modelos locais do Canvas também perguntam antes.** O provedor embutido do Hugging Face nunca baixa nada em silêncio: em *Configuração → Mídia* você escolhe o modelo de cada tipo e depois a **precisão (quantização)** — fp32 (original, funciona em CPU), fp16 ou bf16 (metade do tamanho, pensados para placa de vídeo) —, vendo o tamanho do download de cada uma antes de qualquer coisa ser baixada. Só os arquivos da precisão escolhida são baixados, e só modelos que você baixou são carregados.

Desde a v0.17.1 os nós de mídia (Imagem, Vídeo, Som, Voz, Transcrever) mostram só **Provedor, Modelo e Resolução** (Imagem e Vídeo; no Vídeo, *Automática* deixa o modelo escolher, e vale para o Demo e modelos locais — a nuvem usa os tamanhos dela). O antigo bloco *Avançado* (prompt negativo, semente, JSON livre de parâmetros extras, *ignorar estilos globais*) saiu da tela; o que já estava salvo num canvas continua valendo, e o JSON `extra` de um nó ainda é mesclado ao pedido do provedor quando está no `canvas.json` / na API.

> Os adaptadores de serviços de terceiros seguem a documentação pública de cada serviço e são testados contra servidores simulados; os caminhos Demo e locais são testados de ponta a ponta. Se um provedor mudar a API, abra uma issue.

## Conteúdo livre

O ASTA **não adiciona filtros de conteúdo**: o modo padrão segue o seu prompt e o seu worldbuilding, inclusive temas adultos (NSFW) quando fizerem sentido, sem sermões; o modo **SFW** mantém tudo para todos os públicos. O provedor que você escolher ainda pode ter as próprias regras. Há **duas regras fixas**, mesmo no modo livre: nenhum conteúdo sexual envolvendo menores e nenhum conteúdo sexual sobre pessoas reais (avatares de pessoas reais ficam sempre em SFW; personagens fictícios adultos podem ser NSFW).

## Privacidade e segurança

- Tudo roda localmente. O servidor escuta **só em `127.0.0.1`** por padrão (`--host 0.0.0.0` expõe na rede e avisa).
- Chaves de API ficam em `~/.asta/settings.json` (permissão `600`) e **nunca** são devolvidas ao navegador.
- Proteção contra *DNS rebinding* (checagem de `Host`) e requisições entre sites (checagem de `Origin`); uploads e arquivos servidos passam por validação de caminho; mídias enviadas são identificadas pelo conteúdo, não pelo nome.
- **Computer Use** é opcional e desligado por padrão; tem limites fixos em qualquer modo (sem senhas, chaves, pasta de dados do ASTA, pastas do sistema, shells ou scripts), lixeira e **Desfazer** — veja [Computer Use](#computer-use--uma-equipe-de-ia-que-trabalha-no-seu-computador). Aparelhos pareados por QR code têm o mesmo acesso que você ao ASTA, inclusive a ele.
- O **Code** só roda código escrito pela IA dentro da pasta do projeto da sessão, como listas de argumentos de ferramentas de desenvolvimento (sem shell), com ambiente limpo, limite de tempo e um modo Ask que mostra o comando inteiro; segredos e a pasta de dados do ASTA são inalcançáveis; o token do GitHub nunca chega ao navegador, às exportações nem a uma IA — veja [Code](#code--uma-equipe-de-ia-para-programar-bases-de-código-longas).
- Mundos e jogos não executam código gerado por IA: o modelo escreve **dados** (JSON), e o motor é sempre o mesmo código auditável.

## Estrutura do repositório

```
asta/
  cli.py  server.py  storage.py  jobs.py  cards.py  builder.py  attachments.py  voice.py  hf.py
  providers/     Anthropic, OpenAI-compatível, GGUF local, Demo (modelos de texto)
  agents/        executor compartilhado + pipelines (mundos, avatars, jogos 2D), prompts, esquemas, geradores de regras
  runtime/       motor 3D: three.js, terreno, céu, clima, atores, áudio, IA dos NPCs
  runtime2d/     motores 2D: visual novel, RPG, plataforma, side scroller, point & click
  games2d/       spec dos jogos 2D: esquema, validação, empacotamento
  avatars.py  avatar_chat.py  routes_avatars.py    cards de avatar, diretor da conversa, API
  canvas/        esquema dos nós, armazenamento, motor, provedores de mídia, renderizador da linha do tempo, Demo procedural, menções `@`, lista de modelos instalados, enviar ao Studio
  studio/        projetos de vídeo: esquema, pipeline cena a cena, edição automática, exportação, ferramentas ffmpeg, análise de mídia, legendas, efeitos sonoros, navegador de mídia, transcrição
  computer/      Computer Use: motor da equipe de agentes, catálogo de ferramentas, limites (guard), drivers de SO, arquivos com lixeira/desfazer, fallback por regras e prompts/*.md
  routes_computer.py   API do Computer Use (tarefas, eventos ao vivo, aprovações)
  code/          Code: motor da equipe de agentes (trabalhadores em paralelo), ferramentas, limites fixos, workspace com desfazer, cliente do GitHub (nuvem + git), gerenciador (pastas, sessões), prompts/*.md
  routes_code.py       API do Code (pastas, sessões, aprovações, arquivos, GitHub, eventos ao vivo)
  rebuild/       leitores e conversores de Ren'Py / RPG Maker (+ a revisão de texto por IA, opcional)
  attachments.py  archives.py    anexos de qualquer tipo; extração segura de ZIP/RAR/7z/TAR
  native/        núcleo Rust obrigatório (só biblioteca padrão; interface 4: modelos, agentes, armazenamento, análise de mídia, ordem de grafos), com equivalente em Python para cada função
  perf.py  scheduler.py  storage_opt.py  modos de desempenho · fila com prioridade dos agentes locais · otimização de armazenamento
  termi18n.py  term_en.py   idioma do terminal (pt/en)
  web/           a WebUI (HTML/CSS/JS puros, sem build)
tests/           testes (unittest) — API, pipelines, motores, provedores, Canvas — e testes de navegador opcionais
installers/      Windows (Inno Setup), macOS (.pkg), Linux (AppImage) e notas da Release
mobile-app/      app Android: casca Capacitor + o motor do ASTA embutido (Chaquopy)
docs/            asta-principles.md · asta-dev-guide.md · imagens do README
.github/workflows/  ci.yml (testes) · release.yml (instaladores + Release)
install.sh  install.ps1
```

## Desenvolvimento

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data                            # dados de desenvolvimento isolados
python -m unittest discover -s tests -t .          # testes, sem rede
cargo test --release --manifest-path asta/native/Cargo.toml   # o núcleo Rust
```

Os testes de navegador (Chromium via Playwright) e os dos motores em JavaScript rodam automaticamente quando o Node.js (e o Playwright) estão disponíveis, e são pulados caso contrário. Veja [CONTRIBUTING.pt-BR.md](CONTRIBUTING.pt-BR.md) (em inglês: [CONTRIBUTING.md](CONTRIBUTING.md)). **Os princípios do projeto estão em [docs/asta-principles.md](docs/asta-principles.md) e as regras que todo desenvolvedor (humano ou IA) segue estão em [docs/asta-dev-guide.md](docs/asta-dev-guide.md).** O histórico de mudanças está em [CHANGELOG.md](CHANGELOG.md) ([inglês](CHANGELOG.en.md)).

## Roadmap

- Imagens anexadas como texturas/placas dentro do mundo 3D.
- Mais tipos de estruturas e biomas; interiores; estradas e rios.
- Multiplayer local (vários jogadores no mesmo mundo).
- Scripts de comportamento gerados por IA em *sandbox*.
- Exportar o mundo como aplicativo desktop/mobile.
- **Federation** (veja [asta-principles](docs/asta-principles.md)): ASTAs independentes trocando pacotes assinados e versionados, por escolha — uma direção, ainda não implementada.
- Sincronização/backup opcional e criptografado, num destino à sua escolha.
- Instaladores do Windows/macOS assinados (exige certificados).
- Ideias na mesa (sem data): levar mais trechos críticos para o núcleo Rust; projetos do Studio compartilhados (vários usuários).

## Licença e créditos

[MIT](LICENSE) © 2026 KMC. Usa o [three.js](https://threejs.org) r159 (MIT), embutido em `asta/runtime/vendor`.

---

> **Aviso sobre IA:** este projeto inteiro foi gerado e revisado usando a IA **Claude**, da Anthropic, e foram usados somente modelos da linha **Claude Sonnet 5.0+**.
