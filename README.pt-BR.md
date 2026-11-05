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
| 🙂 **Avatars** | Amigos, namorados(as), companheiros e mentores para conversar por **texto e voz** — um de cada vez ou **vários conversando entre si**. |
| 🎮 **Jogos 2D** | Jogos 2D completos de qualquer tipo: visual novels, RPGs, plataformas, side scrollers e point & clicks. |
| 🧩 **Canvas** | Um fluxo simples de nós (inspirado no ElevenLabs Flow, bem mais leve que o ComfyUI) para gerar e editar **imagens, vídeos, sons e vozes**, com **Editor** de vídeo embutido e **estilos** para o projeto todo. |

Tudo o que você cria vai para uma só **Biblioteca** de projetos atualizáveis.

- 🧠 **Geração multi-agentes e multi-etapas** (Analista → Planejador → Designer → Revisor → Empacotador) com validação determinística e gerador de regras como reserva: algo jogável sempre é entregue.
- 🪶 **Leve por design**: o núcleo usa só a biblioteca padrão do Python; não há etapa de build; mundos e jogos se adaptam ao seu hardware.
- 🔒 **Local e privado**: o servidor escuta em `127.0.0.1`, as chaves nunca chegam ao navegador e a IA escreve **dados (JSON)**, nunca código que seja executado.

## Instalação

Precisa só do **Python 3.9+**. O **mesmo comando instala e atualiza** (seus dados em `~/.asta` nunca são tocados).

**Linux e macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex
```

Depois, em qualquer terminal:

```bash
asta
```

A WebUI abre em `http://localhost:8787`. Para atualizar, rode o comando de instalação de novo (ou `asta update`).

<details>
<summary>Opções de instalação</summary>

| Variável | Efeito |
|---|---|
| `ASTA_EXTRAS=local` | instala também o suporte a modelos de linguagem GGUF embutidos (`llama-cpp-python`) |
| `ASTA_EXTRAS=media` | instala também modelos locais de imagem/vídeo/som/voz do Canvas (`torch`, `diffusers`, `transformers`) |
| `ASTA_EXTRAS=docs` | extração de PDFs mais precisa (`pypdf`) |
| `ASTA_SOURCE=<url\|pasta>` | instala de outra origem (fork, branch, pasta local) |
| `ASTA_APP_DIR`, `ASTA_BIN_DIR` | onde ficam o programa e o comando `asta` |

Dá para combinar extras: `ASTA_EXTRAS=local,media`. Instalação manual: `pip install "asta @ https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"`.
Opções do comando: `asta --port 9000 --no-browser --home /outra/pasta` · `asta doctor` mostra o diagnóstico do seu hardware e dos componentes opcionais.

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

- **Cards de avatar completos**: nome, relação (amigo, namorado(a), companheiro(a), mentor, outro), idade, gênero, personalidade, aparência, cenário, primeira mensagem, exemplos de fala, system prompt completo opcional, quanto fala em grupo, **voz** (tom/velocidade/voz) e **retrato** — envie um ou use o rosto desenhado que muda com o humor do avatar.
- **Crie com IA** a partir de uma descrição em texto, de **imagens ou de qualquer arquivo anexado** (documentos, planilhas, conversas…): um avatar ou **vários de uma vez** ("três amigos de faculdade: Theo, Mia e Caio").
- **Conversa single** (você ↔ um avatar) e **em grupo** (você ↔ até 8 avatars). No grupo, um *diretor* decide quem responde (menções, quanto cada um fala) e, com a **conversa livre** ligada, os avatars **continuam conversando entre si sozinhos**, como num grupo de verdade, até fazerem uma pausa e esperarem você.
- **Texto e voz**: respostas em *streaming*, respostas faladas em voz alta, ditado pelo microfone ou **conversa por voz** com as mãos livres — voz do navegador, de graça, ou qualquer servidor STT/TTS compatível com a API da OpenAI (nuvem ou local).
- **Memória**: histórico de curto prazo mais memórias de longo prazo que o próprio avatar anota (você pode lê-las e apagá-las).
- **SFW ou NSFW por avatar.** Uma regra fixa que nenhuma configuração muda: avatars são adultos. Se um card disser (no campo de idade ou em qualquer texto) que o personagem é menor de idade, o ASTA nunca o "envelhece": ele fica estritamente SFW e platônico — amigo, nunca parceiro(a).
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
| **Mundos** | Personalizar os mundos 3D gerados: bioma, clima, hora, ciclo dia/noite, NPCs, áudio, interface, qualidade. Cada salvamento vira uma nova versão **sem gastar IA**. |
| **Avatars** | Seus cards de avatar e as conversas single e em grupo. |
| **Jogos 2D** | Seus jogos: jogar, baixar, atualizar. |
| **Canvas** | Seus canvases e o editor de nós. |
| **Personagens** | Cards dos NPCs dos mundos 3D e do jogador: nome, tags, system prompt, voz, aparência. Importa/exporta JSON e cards de PNG (Character Card V2/V3). |
| **Worldbuilding** | Regras gerais dos mundos (cenário, tom, convenções), também salvas como cards. |
| **Biblioteca** | Tudo o que você criou como projetos atualizáveis, com busca e tags automáticas + personalizadas. |
| **Configuração** | Provedores, provedores de mídia, geração, avatars e jogos, voz, modelos locais do Hugging Face e sistema. |

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
| Ollama · LM Studio · llama.cpp server · vLLM · qualquer endpoint compatível | **local** | sem custo; escolha o modelo na lista |
| Hugging Face GGUF (embutido) | **local** | baixa o `.gguf` direto do Hugging Face e roda dentro do ASTA (`pip install "asta[local]"`) |
| Demo | offline | gerador de regras para testar tudo sem chave |

Você escolhe um modelo **para gerar** (o mais capaz) e outro **para os personagens e avatars** (um rápido e barato basta). Em *Configuração → Modelos locais* há busca no Hugging Face, indicação de quais arquivos cabem na sua RAM e download com progresso.

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
| **Demo** (offline) | ✅ | ✅ | ✅ | ✅ | | imagens procedurais, som sintetizado, "voz" de balbucio, vídeo Ken Burns (precisa do `ffmpeg`) |

A seção *Avançado* de cada nó aceita um **JSON de parâmetros extras** mesclado ao pedido do provedor, então qualquer opção específica de um modelo fica ao alcance.

> Os adaptadores de serviços de terceiros seguem a documentação pública de cada serviço e são testados contra servidores simulados; os caminhos Demo e locais são testados de ponta a ponta. Se um provedor mudar a API, abra uma issue.

## Conteúdo livre

O ASTA **não adiciona filtros de conteúdo**: o modo padrão segue o seu prompt e o seu worldbuilding, inclusive temas adultos (NSFW) quando fizerem sentido, sem sermões; o modo **SFW** mantém tudo para todos os públicos. O provedor que você escolher ainda pode ter as próprias regras. Há **uma regra fixa**: nenhum conteúdo sexual envolvendo menores — e ela vale mesmo no modo livre.

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
