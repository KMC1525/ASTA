<div align="center">

# ASTA

**Crie mundos virtuais 3D jogáveis e persistentes, habitados por personagens que são agentes de IA.**

Uma WebUI preta e minimalista, inspirada no Grok — descreva um mundo (com texto, imagens, vídeos, áudios, documentos, planilhas…) e uma equipe de agentes de IA planeja, cria, revisa e entrega um jogo pronto num ZIP.

[Instalação](#instalação) · [Primeiros passos](#primeiros-passos) · [Como funciona](#como-funciona) · [Provedores](#provedores-de-ia) · [Contribuir](CONTRIBUTING.md) · [English](README.en.md)

`MIT` · `Windows` · `macOS` · `Linux` · `Python 3.9+` · `zero dependências obrigatórias`

</div>

---

## O que é

O ASTA é um projeto **open source e o mais livre possível**: roda no seu computador, não exige conta nem nuvem, aceita conteúdo **SFW e NSFW** (o ASTA não adiciona filtros próprios) e funciona com os modelos que você quiser — Claude, ChatGPT, Grok, Gemini, OpenRouter, Hugging Face ou modelos 100% locais.

- 🌍 **Mundos 3D jogáveis** em primeira ou terceira pessoa (HTML + CSS + JS + three.js), do jeito mais realista que o seu hardware aguenta.
- 🧠 **Cada personagem/NPC é um agente de IA** que pensa e age: conversa por **texto** (clique no personagem) ou por **voz**, em qualquer idioma, lembra do que você disse, segue você, foge, dança… e, se você ligar a autonomia, decide sozinho o que fazer.
- 🤖 **Sistema multi-agentes e multi-etapas**: Analista → Planejador → Personagens → Arquiteto → Som & UX → Revisor → Empacotador.
- 📦 **Entrega um ZIP** com `code/`, `chars/`, `sound/`, `prompts/`, `ui/ux/` e `Game.html`, mais `README.md` e `CHANGELOG.md` do próprio mundo.
- 🗂️ **Biblioteca** de projetos: atualize o mesmo jogo quantas vezes quiser; busca e tags (automáticas e personalizadas).
- 🪶 **Leve por design**: núcleo só com a biblioteca padrão do Python; os mundos se adaptam ao hardware (e ajustam a qualidade em tempo real).

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
| `ASTA_EXTRAS=local` | instala também o suporte a modelos GGUF embutidos (`llama-cpp-python`) |
| `ASTA_EXTRAS=docs` | extração de PDFs mais precisa (`pypdf`) |
| `ASTA_SOURCE=<url\|pasta>` | instala de outra origem (fork, branch, pasta local) |
| `ASTA_APP_DIR`, `ASTA_BIN_DIR` | onde ficam o programa e o comando `asta` |

Instalação manual: `pip install "asta @ https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"`.
Opções do comando: `asta --port 9000 --no-browser --home /outra/pasta` · `asta doctor` mostra o diagnóstico do seu hardware.

</details>

## Primeiros passos

1. **Teste sem configurar nada.** O provedor padrão é o **Demo** (offline, gera mundos por regras). Escreva um prompt na tela **Principal** e clique em enviar — você verá os agentes trabalhando e, no fim, **Jogar**.
2. **Ligue uma IA de verdade** em **Configuração → Provedores**: cole a chave (Claude, ChatGPT, Grok, Gemini…), clique em *Carregar modelos*, escolha um e *Testar*. Ou use **Ollama / LM Studio** (grátis, local).
3. **Crie personagens e worldbuildings** (ou deixe a IA criar). Anexe arquivos ao prompt. Gere. Jogue. Volte à **Biblioteca** e clique em *Atualizar* para evoluir o mesmo mundo.

## A interface

A barra lateral esquerda tem as seis seções:

| Seção | Para quê |
|---|---|
| **Principal** | O prompt (texto + anexos de qualquer tipo, arrastar-e-soltar/colar) e o acompanhamento ao vivo dos agentes. |
| **Mundos** | Configurar/personalizar os mundos gerados: bioma, clima, hora, ciclo dia/noite, NPCs, áudio, interface, qualidade. Cada salvamento vira uma nova versão **sem gastar IA**. |
| **Personagens** | Cards de personagens/NPCs e do jogador: nome, tags, system prompt, **voz** e aparência. Importa/exporta JSON e cards de PNG (formato Character Card V2/V3). |
| **Worldbuilding** | Regras gerais dos mundos (cenário, tom, convenções), também salvas como cards. |
| **Biblioteca** | Todos os mundos como projetos atualizáveis, com busca e tags automáticas + personalizadas. |
| **Configuração** | Provedores (frontier e locais), geração (mundos e personagens), voz, modelos locais do Hugging Face e sistema. |

## Como funciona

```
 prompt + anexos ──► Analista ──► Planejador ──► Personagens ──► Arquiteto ──► Som & UX ──► Revisor ──► ZIP
 (texto, imagens,    entende      mapa e         cards de IA     monta o       trilha e     critica e     Game.html
  vídeo, áudio,      o pedido     orçamento      dos NPCs        mundo         interface    pede ajustes  + pastas
  docs, planilhas…)               de hardware                                              (até N rodadas)
```

- Os agentes produzem um **spec JSON** do mundo; um **motor 3D determinístico** (three.js) o renderiza. Toda saída de modelo passa por validação (tipos, limites, orçamento de hardware), e um agente que responda lixo é substituído por um gerador de regras — **um mundo jogável é sempre entregue**.
- **Anexos** viram contexto: textos/código, `.docx/.odt/.pdf`, `.xlsx/.ods/.csv`, `.pptx/.odp`, imagens (visão), áudios (transcrição via servidor STT configurado) e vídeos (quadros e áudio via `ffmpeg`, se instalado).
- **Atualizações**: o mesmo projeto ganha a versão *N+1* (ids dos personagens estáveis → memórias preservadas), com histórico no `CHANGELOG.md` do jogo.

### O ZIP gerado

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

### O jogo

**WASD** move · **Shift** corre · **Espaço** pula · **V** alterna 1ª/3ª pessoa · **E** (ou clique) conversa · **M** minimapa · **Esc** solta o mouse. No celular há joystick e botões na tela.

- **Persistente**: posição, hora, memórias e conversas dos NPCs são salvas (no ASTA ou no navegador) e restauradas.
- **Qualquer hardware**: o jogo mede a máquina de quem joga (CPU, RAM, GPU) e ajusta resolução, sombras, vegetação e distância — e continua adaptando em tempo real para manter ~30–60 FPS.
- **Conversa**: abra o chat com **E**, escreva ou use o 🎙. Os NPCs respondem em *streaming*, podem agir (`seguir`, `ficar`, `ir até um lugar`, `acenar`, `dançar`, `fugir`) e guardam memórias de longo prazo.
- **Voz**: por padrão o navegador (reconhecimento + síntese, vários idiomas, grátis). Para vozes de modelos, configure um servidor compatível com a API da OpenAI (nuvem, ou local: Whisper, Kokoro, Piper…).
- Rodando pelo ASTA (**Jogar**), o jogo usa o provedor que você configurou. Abrindo o `Game.html` direto, informe um endpoint em ⚙ (a chave fica só no navegador).

## Provedores de IA

| Provedor | Tipo | Observações |
|---|---|---|
| Claude (Anthropic) | nuvem | API nativa, com visão |
| ChatGPT (OpenAI) · Grok (xAI) · Gemini (Google) · OpenRouter | nuvem | API compatível com OpenAI |
| Hugging Face Inference | nuvem | `router.huggingface.co` |
| Ollama · LM Studio · llama.cpp server · vLLM · qualquer endpoint compatível | **local** | sem custo; escolha o modelo na lista |
| Hugging Face GGUF (embutido) | **local** | baixa o `.gguf` direto do Hugging Face e roda dentro do ASTA (`pip install "asta[local]"`) |
| Demo | offline | gerador de regras para testar tudo sem chave |

Você escolhe um modelo **para gerar os mundos** (o mais capaz) e outro **para os personagens** (um rápido e barato basta).
Em *Configuração → Modelos locais* há busca no Hugging Face, indicação de quais arquivos cabem na sua RAM e download com progresso.

## Conteúdo livre

O ASTA **não adiciona filtros de conteúdo**: o modo padrão segue o seu prompt e o seu worldbuilding, inclusive temas adultos (NSFW) quando fizerem sentido, sem sermões; o modo **SFW** mantém tudo para todos os públicos. O provedor que você escolher ainda pode ter as próprias regras. Há **uma regra fixa**: nenhum conteúdo sexual envolvendo menores — e ela vale mesmo no modo livre.

## Privacidade e segurança

- Tudo roda localmente. O servidor escuta **só em `127.0.0.1`** por padrão (`--host 0.0.0.0` expõe na rede e avisa).
- Chaves de API ficam em `~/.asta/settings.json` (permissão `600`) e **nunca** são devolvidas ao navegador.
- Proteção contra *DNS rebinding* (checagem de `Host`) e requisições entre sites (checagem de `Origin`); uploads e arquivos servidos passam por validação de caminho.
- Os mundos não executam código gerado por IA: o modelo escreve **dados** (JSON), o motor é o mesmo código auditável.

## Estrutura do repositório

```
asta/
  cli.py  server.py  storage.py  cards.py  builder.py  attachments.py  voice.py  hf.py
  providers/    Anthropic, OpenAI-compatível, GGUF local, Demo
  agents/       pipeline multi-agentes, prompts, esquema/validação, gerador de regras
  runtime/      motor do jogo: three.js, terreno, céu, clima, atores, áudio, IA dos NPCs
  web/          a WebUI (HTML/CSS/JS puros, sem build)
tests/          testes (unittest) — API, pipeline, anexos, provedores, segurança
install.sh  install.ps1
```

## Desenvolvimento

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data                            # dados de desenvolvimento isolados
python -m unittest discover -s tests -t .          # 40 testes, sem rede
```

Veja [CONTRIBUTING.md](CONTRIBUTING.md). O histórico de mudanças está em [CHANGELOG.md](CHANGELOG.md).

## Roadmap

- Imagens anexadas como texturas/placas dentro do mundo.
- Mais tipos de estruturas e biomas; interiores; estradas e rios.
- Multiplayer local (vários jogadores no mesmo mundo).
- Scripts de comportamento gerados por IA em *sandbox*.
- Exportar o mundo como aplicativo desktop/mobile.

## Licença e créditos

[MIT](LICENSE) © 2026 KMC. Usa o [three.js](https://threejs.org) r159 (MIT), embutido em `asta/runtime/vendor`.
