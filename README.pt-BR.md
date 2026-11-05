<div align="center">

# ASTA

**A central open source de criação com IA: mundos 3D cujos NPCs são agentes de IA, avatars com quem conversar, jogos 2D e um Canvas de mídia — tudo gerado por IA, tudo no seu computador.**

Uma WebUI preta e minimalista, inspirada no Grok. Descreva o que quer (com texto, imagens, vídeos, áudios, documentos, planilhas…) e uma equipe de agentes de IA planeja, cria, revisa e entrega: um mundo 3D jogável, um companheiro para conversar, um jogo 2D completo ou um fluxo de nós que produz imagens, vídeos, sons e vozes.

[Instalação](#instalação) · [Primeiros passos](#primeiros-passos) · [Os quatro modos](#os-quatro-modos) · [Provedores](#provedores-de-ia) · [Contribuir](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [English](README.md)

`MIT` · `Windows` · `macOS` · `Linux` · `Python 3.9+` · `zero dependências obrigatórias`

</div>

---

## O que é

O ASTA é um projeto **open source e o mais livre possível**: roda no seu computador, não exige conta nem nuvem, aceita conteúdo **SFW e NSFW** (o ASTA não adiciona filtros próprios) e funciona com os modelos que você quiser — Claude, ChatGPT, Grok, Gemini, OpenRouter, Hugging Face ou modelos 100% locais.

Desde a **v0.2** ele é uma central universal de criação com quatro modos, todos na mesma caixa de prompt:

| Modo | Você recebe |
|---|---|
| 🌍 **Mundos 3D** | Mundos 3D jogáveis e persistentes (1ª ou 3ª pessoa), habitados por NPCs que são agentes de IA embutidos. |
| 🙂 **Avatars** | Amigos, namorados(as), esposas/maridos, companheiros e mentores para conversar por **texto e voz** — um de cada vez ou **vários conversando entre si**. |
| 🎮 **Jogos 2D** | Jogos 2D completos de qualquer tipo: visual novels, RPGs, plataformas, side scrollers e point & clicks. |
| 🧩 **Canvas** | Um fluxo simples de nós (inspirado no ElevenLabs Flow, bem mais leve que o ComfyUI) para gerar e editar **imagens, vídeos, sons e vozes**, com **Editor** de vídeo embutido e **estilos** para o projeto todo. |

Tudo o que você cria vai para uma só **Biblioteca** de projetos atualizáveis.

- 🧠 **Geração multi-agentes e multi-etapas** (Analista → Planejador → Designer → Revisor → Empacotador) com validação determinística e gerador de regras como reserva: algo jogável sempre é entregue.
- 🪶 **Leve por design**: o núcleo usa só a biblioteca padrão do Python; não há etapa de build; mundos e jogos se adaptam ao seu hardware.
- 🔒 **Local e privado**: o servidor escuta em `127.0.0.1`, as chaves nunca chegam ao navegador e a IA escreve **dados (JSON)**, nunca código que seja executado.

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

Depois, em qualquer terminal:

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
| `ASTA_SOURCE=<url\|pasta>` | instala de outra origem (fork, branch, pasta local) |
| `ASTA_APP_DIR`, `ASTA_BIN_DIR` | onde ficam o programa e o comando `asta` |

Instalação manual: `pip install "asta @ https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"`.
Opções do comando: `asta --port 9000 --no-browser --home /outra/pasta` · `asta update` atualiza o **Python, o ASTA e todas as bibliotecas dele** rodando o instalador oficial (`--no-python` mantém o Python do sistema, `--core` atualiza só o ASTA e o `pip`/`setuptools`/`wheel`, `--extras docs,media` escolhe as bibliotecas; um ASTA instalado à mão com `pip` atualiza tudo menos o Python do sistema) · `asta libs` instala/atualiza só as bibliotecas, `sh install.sh --python-only` só o Python e as ferramentas dele · `asta doctor` mostra o diagnóstico do seu hardware e dos componentes opcionais. As bibliotecas são atualizadas junto com as dependências delas, então os recursos do Canvas e dos modelos locais ficam em dia.

</details>

**Ferramenta opcional.** O [`ffmpeg`](https://ffmpeg.org) libera a análise de vídeo, a exportação do Editor de vídeo do Canvas e o vídeo offline do Demo. Todo o resto funciona sem ele.

## Primeiros passos

1. **Teste sem configurar nada.** O provedor padrão é o **Demo** (offline, gera por regras). Na tela **Principal**, escolha um modo, escreva um prompt e envie — você verá os agentes trabalhando e, no fim, **Jogar**, **Conversar** ou **Abrir**.
2. **Ligue uma IA de verdade** em **Configuração → Provedores**: cole a chave (Claude, ChatGPT, Grok, Gemini…), clique em *Carregar modelos*, escolha um e *Testar*. Ou use **Ollama / LM Studio** (grátis, local).
3. **Para o Canvas**, escolha os provedores de imagem/vídeo/som/voz em **Configuração → Mídia** (OpenAI, ElevenLabs, Google, Stability AI, Replicate, Hugging Face, uma Stable Diffusion WebUI local ou modelos locais do Hugging Face). Sem nenhum, o provedor Demo deixa você testar fluxos inteiros offline.
4. Volte à **Biblioteca** quando quiser e clique em *Atualizar* para evoluir o mesmo projeto.

## Os quatro modos

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
- **Os avatares respondem com IA de verdade.** As respostas do chat vêm de um modelo de IA — nuvem (Anthropic, OpenAI, Gemini…) ou local (Ollama, LM Studio, o modelo GGUF embutido, o Qwen pré-instalado) — nunca de frases prontas quando há IA disponível. *Configuração → Provedores → Quem faz o quê → Personagens* vem em **Automático**: usa o provedor de geração se estiver usável (chave ou modelo definidos) e, se não, o modelo local de texto instalado (precisa do `llama-cpp-python`: `asta libs --extras local`). A *criação* de avatares e o pipeline de system prompt seguem a mesma regra. O **Demo** (respostas pré-programadas, sem IA) só entra quando nada mais existe — e aí o chat mostra um aviso *Modo Demo* com o motivo e o botão *Configurar IA*; com IA, uma linha mostra qual modelo está respondendo. Escolha um provedor específico no papel para forçá-lo.
- **LM Studio para os avatares (e o resto).** Ligue o servidor no LM Studio (*Developer → Start Server*, ou `lms server start`) e carregue um modelo: o ASTA **detecta sozinho** em `http://127.0.0.1:1234` (ou na URL que você definir) — com o papel *Personagens* em **Automático**, os avatares já conversam por ele, antes do modelo GGUF embutido, sem configurar nada. Em *Configuração → Provedores → LM Studio*, clique em detectar: você vê se o servidor está rodando, os modelos de chat (carregados `●` primeiro, instalados `○`, com visão `👁`; os de embeddings ficam escondidos), escolhe um com um clique e usa *Usar nos avatares* / *Usar na geração*. Sem modelo escolhido o ASTA usa o que está carregado no LM Studio; a visão vem do tipo do modelo (`vlm`); chave de API opcional e servidor em outra máquina também funcionam; se o servidor estiver desligado, o erro diz como ligá-lo. Modelos que escrevem o raciocínio em `<think>…</think>` (Qwen3, DeepSeek R1…) têm o trecho escondido no chat. O `asta doctor` também mostra o LM Studio.
- **Pipeline de system prompt (Analisa → Gera → Revisa → Entrega).** No editor do avatar, *Gerar o system prompt com IA* roda 4 etapas: (1) **Analisa** — quem é o personagem (real ou fictício, idade, jeito de falar, relação, limites, o que o modo de conteúdo permite); (2) **Gera** — escreve o system prompt; (3) **Revisa** — confere coerência, voz, idioma, tamanho e as regras fixas, devolvendo para uma rodada de correção se preciso; (4) **Entrega** — limpa o texto e aplica as regras de segurança *por código* (pessoa real ou menor vira SFW, não importa o que o modelo diga). Funciona offline no modo Demo (por regras), **roda automaticamente em cada avatar que você cria** (uma etapa *System prompts* depois do Revisor; pule com `prompt_pipeline: false` em `POST /api/avatars/generate`) e também por `POST /api/avatars/system-prompt` (`avatar_id` ou `draft`, `instructions`, `content`, `character_type`, `apply`).
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

- **Execução inteligente**: os nós rodam na ordem das dependências, os resultados ficam em cache por um hash de parâmetros, entradas, estilos e modelo, e só o que mudou é gerado de novo. "Gerar de novo" cria uma nova variação. Um nó com erro nunca quebra o resto do fluxo.
- Os **nós de estilo** são globais por padrão; desligue *global* para aplicá-los só onde estiverem ligados, ou marque *Ignorar estilos globais* num nó.
- **Modelos** para começar rápido: Texto → Imagem, Texto → Imagem → Vídeo, Com estilo do projeto e uma cena completa (roteiro → imagem → vídeo + narração + som, montada no Editor).
- **Todos os arquivos são seus**: um canvas é uma pasta (`canvas.json` + `assets/`) que você pode baixar em ZIP.

## A interface

| Seção | Para quê |
|---|---|
| **Principal** | A caixa de prompt com os quatro modos (texto + anexos de qualquer tipo, arrastar-e-soltar/colar) e o acompanhamento ao vivo dos agentes. |
| **Mundos** | Tudo sobre os mundos 3D em três abas: **Mundos** (personalizar os mundos gerados: bioma, clima, hora, ciclo dia/noite, NPCs, áudio, interface, qualidade — cada salvamento vira uma nova versão **sem gastar IA**), **Personagens** (cards dos NPCs e do jogador: nome, tags, system prompt, voz, aparência; importa/exporta JSON e cards de PNG, Character Card V2/V3) e **Worldbuilding** (regras gerais dos mundos — cenário, tom, convenções — também salvas como cards). |
| **Avatars** | Seus cards de avatar e as conversas single e em grupo. |
| **Jogos 2D** | Seus jogos: jogar, baixar, atualizar. |
| **Canvas** | Seus canvases e o editor de nós. |
| **Biblioteca** | Tudo o que você criou como projetos atualizáveis, mais os **modelos de IA locais instalados**, com busca e tags automáticas + personalizadas. Use *Selecionar* para escolher vários itens e apagá-los de uma vez; os modelos podem ser apagados um a um ou em lote. |
| **Configuração** | Provedores, provedores de mídia, geração, avatars e jogos, voz, modelos locais do Hugging Face, **aparência** e sistema. |

### Deixe do seu jeito (Configuração → Aparência)

- **Tema:** escuro (padrão), **claro** ou **automático** (segue o sistema, ao vivo). A aparência é aplicada antes do primeiro quadro, então nunca pisca. O grafo de nós do Canvas e o editor de vídeo ficam escuros de propósito, como nos editores de mídia.
- **Cor de destaque:** 6 predefinidas ou qualquer cor; botões, seleções e a sua bolha no chat seguem a cor (o contraste do texto é escolhido sozinho).
- **Conforto:** tamanho da interface de 90 a 150%, densidade confortável ou compacta, fonte do sistema/serifada/monoespaçada, tamanho do texto do chat dos avatares e **reduzir animações** (também respeita a configuração do sistema).
- **Uso:** idioma da interface, **enviar com Enter ou Ctrl+Enter** (chat e caixa de criação), **tela inicial** (Principal, uma tela específica ou *a última que usei*), atalhos de teclado ligados/desligados.
- **Barra lateral:** esconda as telas que você não usa (*Principal* e *Configuração* ficam sempre; as escondidas continuam acessíveis pela busca).
- **Paleta de comandos — `Ctrl/⌘ + K`:** digite para ir a qualquer tela ou aba da Configuração, conversar com/editar um avatar, abrir um projeto ou canvas, ou rodar uma ação (novo avatar, alternar tema, exportar configurações…). Atalhos: `Alt+1…7` telas, `Alt+B` barra lateral, `Alt+T` tema, `?` ajuda.
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

**Modelos GGUF por tipo.** A aba *Modelos locais* é dividida em **Texto, Imagem, Vídeo, Som e música, Voz e Outros**. Cada tipo tem a sua busca no Hugging Face (filtrada pela tarefa do repositório), a sua pasta (`models/`, `models/image`, `models/video`, …), o mesmo seletor de quantização e a sua lista de *Baixados*. Os modelos de texto rodam o próprio ASTA (`llama.cpp`); **os GGUF de Imagem e Vídeo (FLUX, Stable Diffusion, Wan…) rodam no Canvas pela `stable-diffusion.cpp`** (provedor *GGUF local*, `pip install "asta[local]"`): use *Usar no Canvas* num arquivo baixado. Opções extras de carregamento (VAE, codificadores de texto…) vão em *Avançado → parâmetros extras* do nó (`{"load": {"diffusion_model_path": "@model", "vae_path": "ae.safetensors"}}`). Para **Som, Voz e Outros** o ASTA por enquanto só baixa e organiza os arquivos — ainda não há motor embutido para rodá-los.

**Os modelos locais do Canvas também perguntam antes.** O provedor embutido do Hugging Face nunca baixa nada em silêncio: em *Configuração → Mídia* você escolhe o modelo de cada tipo e depois a **precisão (quantização)** — fp32 (original, funciona em CPU), fp16 ou bf16 (metade do tamanho, pensados para placa de vídeo) —, vendo o tamanho do download de cada uma antes de qualquer coisa ser baixada. Só os arquivos da precisão escolhida são baixados, e só modelos que você baixou são carregados.

A seção *Avançado* de cada nó aceita um **JSON de parâmetros extras** mesclado ao pedido do provedor, então qualquer opção específica de um modelo fica ao alcance.

> Os adaptadores de serviços de terceiros seguem a documentação pública de cada serviço e são testados contra servidores simulados; os caminhos Demo e locais são testados de ponta a ponta. Se um provedor mudar a API, abra uma issue.

## Conteúdo livre

O ASTA **não adiciona filtros de conteúdo**: o modo padrão segue o seu prompt e o seu worldbuilding, inclusive temas adultos (NSFW) quando fizerem sentido, sem sermões; o modo **SFW** mantém tudo para todos os públicos. O provedor que você escolher ainda pode ter as próprias regras. Há **duas regras fixas**, mesmo no modo livre: nenhum conteúdo sexual envolvendo menores e nenhum conteúdo sexual sobre pessoas reais (avatares de pessoas reais ficam sempre em SFW; personagens fictícios adultos podem ser NSFW).

## Privacidade e segurança

- Tudo roda localmente. O servidor escuta **só em `127.0.0.1`** por padrão (`--host 0.0.0.0` expõe na rede e avisa).
- Chaves de API ficam em `~/.asta/settings.json` (permissão `600`) e **nunca** são devolvidas ao navegador.
- Proteção contra *DNS rebinding* (checagem de `Host`) e requisições entre sites (checagem de `Origin`); uploads e arquivos servidos passam por validação de caminho; mídias enviadas são identificadas pelo conteúdo, não pelo nome.
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
  canvas/        esquema dos nós, armazenamento, motor, provedores de mídia, renderizador da linha do tempo, Demo procedural
  web/           a WebUI (HTML/CSS/JS puros, sem build)
tests/           testes (unittest) — API, pipelines, motores, provedores, Canvas — e testes de navegador opcionais
install.sh  install.ps1
```

## Desenvolvimento

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data                            # dados de desenvolvimento isolados
python -m unittest discover -s tests -t .          # testes, sem rede
```

Os testes de navegador (Chromium via Playwright) e os dos motores em JavaScript rodam automaticamente quando o Node.js (e o Playwright) estão disponíveis, e são pulados caso contrário. Veja [CONTRIBUTING.md](CONTRIBUTING.md). O histórico de mudanças está em [CHANGELOG.md](CHANGELOG.md).

## Roadmap

- Imagens anexadas como texturas/placas dentro do mundo 3D.
- Mais tipos de estruturas e biomas; interiores; estradas e rios.
- Multiplayer local (vários jogadores no mesmo mundo).
- Scripts de comportamento gerados por IA em *sandbox*.
- Exportar o mundo como aplicativo desktop/mobile.
- Próximas versões planejadas: **v0.3 — Rebuild** (novo backend em Rust) e **v0.4 — Studio**. Elas não fazem parte da 0.2.

## Licença e créditos

[MIT](LICENSE) © 2026 KMC. Usa o [three.js](https://threejs.org) r159 (MIT), embutido em `asta/runtime/vendor`.
