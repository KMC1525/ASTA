# Changelog

Todas as mudanças relevantes do ASTA são registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

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

[Não lançado]: https://github.com/KMC1525/ASTA/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/KMC1525/ASTA/releases/tag/v0.1.0
