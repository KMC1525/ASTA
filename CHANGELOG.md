# Changelog

Todas as mudanças relevantes do ASTA são registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.4.1] — 2026-11-05

**Chat com busca na web nativa e uma aba de configurações própria** (tamanho da resposta, janela de contexto, tempo de pensamento).

### Adicionado
- **Busca na web nativa no Chat (botão 🌐 Web)**, para qualquer prompt e qualquer modelo (nuvem ou local — a busca é do ASTA, não depende de recurso do provedor):
  - pesquisa a pergunta, **lê as primeiras páginas** e entrega ao modelo um bloco com **fontes numeradas**; a resposta cita [1], [2] e mostra chips de **Fontes** clicáveis, que ficam salvos no histórico. Em perguntas de seguimento ("e o preço dele?") o modelo reescreve a consulta com o contexto da conversa; a data de hoje vai no contexto.
  - **Motores:** *Automático* (DuckDuckGo → Wikipédia, sem chave), DuckDuckGo, Wikipédia, **Brave Search** (chave), **Tavily** (chave) e **SearXNG** (a sua instância). As chaves ficam no servidor e nunca voltam ao navegador. Número de resultados, páginas lidas por inteiro e idioma configuráveis; botão **Testar busca**.
  - **Também nas ferramentas de criação:** com a ferramenta ligada e o Web aceso, o Run pesquisa o prompt e anexa as referências (limitadas a 6.000 caracteres) antes de iniciar o pipeline; se a busca falhar, cria sem ela e avisa.
  - **Segurança:** só `http(s)`; páginas de resultados em `localhost`, redes privadas, link-local (como `169.254.169.254`) e IPs reservados são recusadas, **inclusive em redirecionamentos**; resultados são tratados como texto não confiável (o modelo é instruído a nunca seguir ordens vindas das páginas); limites de tamanho e de tempo.
  - A escolha do botão é lembrada; *Configuração → Chat → Deixar a busca na web ligada por padrão* define o começo. Com o Demo (sem IA) a busca não roda e o Chat explica o porquê. Falha de busca → aviso e a resposta segue só com o que o modelo sabe.
  - API: `POST /api/web/search` (títulos, links e trechos) e `POST /api/web/context` (bloco para o prompt); `POST /api/chats/<id>/send` e `/regenerate` aceitam `"web": true` e emitem os eventos `search` e `sources`.
- **Aba Chat em Configuração:**
  - **Tamanho das respostas (tokens)** — de 64 a 32.000, com atalhos (500 · 2K · 6K · 16K). Vale só para o texto visível: o pensamento vai além.
  - **Janela de contexto (tokens)** — de 1K a 2M, com atalhos (4K … 128K): o histórico enviado ao modelo cabe nela (descontados texto de sistema, fontes da web e a resposta); o que passar tem as mensagens **mais antigas** cortadas primeiro. Mais **turnos lembrados**, **criatividade** e **instruções personalizadas** (entram em toda conversa do Chat).
  - **Tempo de pensamento padrão** e as opções da **busca na web** (motor, resultados, páginas lidas, chaves, SearXNG, idioma).
- **Tempo de pensamento (Desligado · Slow · Medium · High · Extra high · Ultra)**, num botão **ao lado do nome do modelo — que só aparece quando o modelo escolhido tem o recurso**:
  - **Claude** (3.7 e família 4/5): pensamento estendido, com orçamento de 1.024 / 4.000 / 10.000 / 20.000 / 32.000 tokens **além** do tamanho da resposta (a temperatura não é enviada, como a API exige; o total respeita o teto de 32.000 de saída).
  - **OpenAI** (o-series, GPT-5), **Gemini 2.5+** (endpoint compatível), **gpt-oss** (LM Studio, Ollama, llama.cpp, personalizado) e modelos com raciocínio no **OpenRouter**: `reasoning_effort` (ou `reasoning.effort`) low / medium / high — *Extra high* e *Ultra* usam *high* com mais folga de tokens (esses provedores só têm três degraus).
  - Modelos sem o recurso: nenhum seletor e nada é enviado. Se um modelo recusar o modo, o ASTA **refaz o pedido sem ele e avisa**.
- Menus do Chat maiores (modelo e ferramentas rolam menos) e `settings.chat` ganhou `context_tokens`, `thinking`, `instructions` e `web`.

### Alterado
- O aviso "gastou o limite pensando" agora aponta para *Configuração → Chat* (aumentar o tamanho da resposta ou baixar o tempo de pensamento). Os avisos do Chat passaram a ser traduzidos.

### Testes
- `tests/test_websearch.py`: análise do HTML do DuckDuckGo (anúncios fora, redirecionamentos desfeitos), Wikipédia, Brave/SearXNG, motores sem chave, fallback do modo automático, bloqueio de hosts privados, HTML → texto, bloco de contexto com limite, consulta reescrita em seguimentos, fontes salvas na resposta, falha de busca e Demo; suporte por modelo, níveis, orçamentos, pedido ao Claude e `reasoning_effort` (com o retry quando o modelo recusa); janela de contexto cortando o mais antigo; segredos das chaves; rotas.
- `tests/browser/chat_settings_ui.js`: aba Chat (campos, atalhos, salvar), botão Web (padrão, lembrar, fontes persistentes), seletor de pensamento ao lado do modelo (só com modelo compatível) e a busca no prompt de uma ferramenta de criação.

### Observação
- **Não consegui testar a busca contra a internet real** neste ambiente de desenvolvimento (a rede de saída é bloqueada): o DuckDuckGo foi testado com HTML de exemplo no formato conhecido da página (`result__a`/`result__snippet`) e os demais motores com respostas simuladas. Se o DuckDuckGo mudar o HTML ou pedir verificação (CAPTCHA), o modo Automático cai para a Wikipédia e a mensagem aponta para os motores com chave (Brave/Tavily) ou SearXNG.
- Os modos de pensamento seguem a documentação pública de cada API, sem ter sido testados contra um Claude/OpenAI/Gemini reais; os testes usam servidores simulados.

## [0.4.0] — 2026-11-05

**Chat 2.0.** A tela **Principal** virou **Chat**: uma conversa limpa e de uso geral (receita de bolo, estudo, texto, código…), com o seletor de modelo ao lado do Run. As criações com vários agentes continuam todas lá, mas agora só rodam **quando você pede** — um ativador.

### Adicionado
- **Tela Chat** no lugar da Principal (o atalho `#/chat` e a ordem do menu continuam; a *Tela inicial* "Principal" passou a se chamar "Chat"). Layout: **caixa de texto** em cima; embaixo, **anexos à esquerda** e, **à direita, o botão de modelo e o Run**. Anexos de qualquer tipo (clique, arrastar-e-soltar, colar) são lidos e usados como contexto.
- **Seletor de modelo e provedor** (botão ao lado do Run): lista os provedores (nuvem e locais), mostra os modelos de cada um (para o LM Studio, inclui *Automático*), aceita digitar outro nome e leva a *Gerenciar provedores…*. A troca é salva em `settings` (provedor de geração + modelo) e vale para o app todo.
- **Conversa geral persistida**, com resposta em **streaming** e **Markdown** (listas, títulos, tabelas, citações, código com botão *Copiar*; renderizador próprio que só cria nós DOM — HTML do modelo nunca é interpretado, links só `http(s)`/`mailto`). **Histórico** (a última conversa reabre sozinha; *Novo chat*; apagar), título automático, **Parar** (o Run vira Parar; nada pela metade é salvo), **Responder de novo** e copiar. Aviso honesto quando o motor é só o **Demo** (sem IA): o Chat diz que não consegue responder de verdade e aponta para o seletor de modelo.
  - API: `GET/POST /api/chats`, `GET/PUT/DELETE /api/chats/<id>`, `POST /api/chats/<id>/send` e `/regenerate` (SSE: `user, title, provider, notice, typing, delta, message, suggest, removed, error, end`), `GET /api/chat/providers`. Ajustes em `settings.chat` (`history_turns`, `temperature`, `max_tokens`).
- **Ativador das ferramentas de criação** (✦ *Criar*): Mundo 3D, Avatar, Jogo 2D e Canvas. **Nada de agente/multiagente/multi-etapas roda sozinho**: o Chat só conversa. Se o pedido parecer uma criação ("crie um jogo 2D…"), ele **sugere** a ferramenta (faixa com *Ligar Jogo 2D*), mas só pré-preenche a caixa — quem executa é você, apertando **Run** com a ferramenta ligada. Dá para desligar (×) e voltar a conversar. As opções de cada ferramenta (gênero, quantidade, relacionamento, SFW/NSFW, perspectiva, foto-base…) aparecem só enquanto ela está ligada; atualizar um projeto pela Biblioteca abre o Chat já com a ferramenta certa.
- Paleta de comandos: **Novo chat**.

### Alterado
- `home.js` agora só contém as ferramentas de criação e as telas de resultado (o compositor `composer.js` ficou configurável: ferramentas à esquerda/direita, rótulo do botão, troca de ação sem perder texto nem anexos).
- O menu flutuante (`popover`) se reposiciona quando a lista cresce e nunca sai da tela.

### Testes
- `tests/test_chat.py` (conversa, histórico, contexto, anexos, Parar/regenerar, detecção do ativador sem execução, Demo honesto, provedores) e `tests/browser/chat_ui.js` (layout: anexos à esquerda e modelo + Run à direita; streaming e Markdown sem HTML injetado; sugestão que não executa; troca de modelo; Parar; histórico; e o Run da ferramenta criando o jogo). Os testes de navegador antigos passaram a usar o ativador no lugar da barra de modos.

### Observação
- Os pipelines de criação são os mesmos de antes; só mudou **como** se chega neles. Quem usava a barra de modos da tela Principal agora liga a ferramenta em ✦ *Criar*.
- Com o provedor **Demo** o Chat não "entende" perguntas — o Demo é por regras. Para conversar de verdade, escolha um modelo no seletor.

## [0.3.3] — 2026-11-05

Revisão da seção **Avatars**, principalmente da hora em que o usuário conversa com o avatar. Cada item foi reproduzido (em teste ou no navegador) antes de corrigir.

### Corrigido
- **A resposta inteira sumia quando o modelo começava a fala com o nome do usuário ou de outro participante** (`Kaua: oi, tudo bem?`, imitando o formato do histórico): o ASTA cortava "tudo a partir da fala do outro" e sobrava nada, então o avatar "não respondia". Agora, se só sobraria vazio, ele tira o rótulo e mantém a fala; falas inventadas do outro no meio do texto continuam sendo cortadas.
- **Não havia como parar uma resposta em andamento.** O botão de enviar agora vira **Parar** enquanto o avatar responde: a fala é interrompida, o balão "digitando" some e **nada pela metade é salvo** no histórico.
- **A tela era puxada para baixo a cada trecho recebido**, mesmo quando você tinha subido para ler o histórico (principalmente na conversa livre em grupo). Agora ela só acompanha se você está no fim; se subiu, aparece o botão **↓ Novas mensagens**. Mandar uma mensagem sua sempre leva ao fim.
- **O título da conversa ficava preso ao nome antigo** do avatar. Conversas sem título escolhido agora usam o nome atual dos avatares (título escolhido por você é mantido); ao salvar *Configurar conversa*, a lista lateral atualiza na hora.
- **O que você digitava e não enviava se perdia** ao trocar de conversa. O rascunho agora é guardado por conversa e volta ao reabrir; o campo respeita o limite de 6.000 caracteres (antes o texto passado disso era cortado em silêncio).
- **Conversas com mais de 8 avatares eram cortadas em silêncio** (a lista de avatares e a janela "Nova conversa" deixavam marcar mais). Agora o limite de 8 aparece na seleção e a API responde com erro claro.
- Ao sair da conversa, o ouvinte de `visibilitychange` ficava registrado (um a mais a cada vez que a tela abria); agora é removido.

### Adicionado
- **Ações em cada mensagem** (aparecem ao passar o mouse ou focar com o teclado): **copiar**, **editar** (no lugar; Enter/Ctrl+Enter salva conforme a sua tecla de envio, Esc cancela) e **apagar**; na última resposta, **Responder de novo** — descarta a(s) resposta(s) daquela rodada (em grupo, todas) e gera outra a partir da sua última mensagem, sem duplicá-la. Editar/apagar enquanto o avatar responde é recusado com aviso (a edição vale para as próximas respostas, pois o histórico é reenviado ao modelo).
  - API: `POST /api/avatar-chats/<id>/regenerate` (SSE, evento `removed`), `PUT` e `DELETE /api/avatar-chats/<id>/messages/<mid>`.
- **Memórias:** além de "Esquecer tudo", dá para **esquecer uma lembrança só** e **ensinar algo ao avatar** ("meu aniversário é em março"). API: `POST /api/avatars/<id>/memory` e `DELETE …/memory?index=N`.
- Aviso "Mostrando as últimas 200 mensagens" em históricos longos.

### Testes
- Rótulo no começo da fala; refazer a resposta (a dois e em grupo, sem duplicar a mensagem do usuário, sem mensagem para refazer); editar e apagar (inclusive recusa durante uma resposta e ids de outra conversa); memórias; limite de 8; títulos que seguem o nome. No navegador, com um servidor local simulado e lento: parar no meio (botão, balão e histórico), responder de novo, editar, apagar, rascunho, rolagem inteligente, memórias e renomear.

### Observação
- Não consegui exercitar aqui a conversa por voz (microfone e síntese) nem um modelo de IA real: a revisão dessas partes foi por leitura do código, sem problemas óbvios além dos listados.

## [0.3.2] — 2026-11-05

### Corrigido
- **Criar um avatar a partir de uma foto/arte parava no Analista com «'url' field must be a base64 encoded image»** (visto com o LM Studio). Servidores locais de visão (LM Studio, Ollama, llama.cpp) só aceitam PNG e JPEG de forma confiável e recusam o resto — GIF, WebP… — com esse erro; antes o ASTA mandava a imagem como estava e qualquer recusa derrubava a criação inteira. Agora:
  - **o tipo da imagem vem dos bytes**, não do nome: um PNG declarado como JPEG (ou o contrário) é enviado com o tipo certo — vale também para o Claude, que recusa quando o tipo declarado não bate;
  - **nos servidores locais, imagens que não são PNG/JPEG são convertidas para PNG** (primeiro quadro, com o `ffmpeg` quando ele existe); sem como converter, a imagem fica de fora com uma nota no texto em vez de causar erro;
  - **se o servidor recusar as imagens mesmo assim** (formato, modelo sem visão, mensagem de erro sobre imagem/`url`/base64…), o ASTA **repete a chamada só com o texto** — no chat e na criação (também com streaming);
  - nos pipelines, isso vira um **aviso** no resultado (*"avatar_analyst: 1 imagem(ns) não puderam ser enviadas ao provedor (formato não aceito ou modelo sem visão); seguiu só com o texto"*) e a criação segue (o visual vem do texto e das cores dominantes da imagem), em vez de falhar. Os provedores de nuvem continuam recebendo todos os formatos.
- Testes: um servidor local "exigente" simulado (aceita só PNG/JPEG em data URL e responde com o erro real) cobre a conversão de GIF, o tipo real dos bytes, a imagem sem conversão possível, a recusa total com nova tentativa só com texto (chamada normal e streaming), provedor de nuvem intacto, Claude com o tipo certo e a criação de avatar a partir de foto concluindo com aviso.

### Observação
- Não tenho um LM Studio real aqui: a causa foi inferida pela mensagem de erro e pelo que esses servidores aceitam, e o conserto cobre os caminhos prováveis (formato, tipo declarado errado e recusa geral). Se aparecer o aviso de imagem não enviada, o modelo carregado provavelmente **não tem visão** (precisa ser um modelo "VLM", como Qwen-VL, Gemma 3 ou LLaVA) — a criação continua, só sem enxergar a foto.

## [0.3.1] — 2026-11-05

### Adicionado
- **Novas relações para os avatares: namorada, namorado, esposa e marido** (`girlfriend`, `boyfriend`, `wife`, `husband`). Aparecem na caixa de criação (*Relação:*), no editor do avatar e nas listas, e funcionam na API (`relationship` em `POST /api/avatars/generate` e nos cards). **Todas podem ser SFW ou NSFW**, como qualquer avatar adulto: o modo de conteúdo continua sendo escolhido à parte (`content`), e a regra fixa vale nos dois — nada de conteúdo sexual envolvendo menores.
  - O prompt de conversa descreve cada relação: namorada/namorado/parceiro(a) são afetuosos, atenciosos, brincalhões e românticos; **esposa/marido** conversam como quem divide a vida com você (casa, rotina, planos), de forma íntima e comprometida.
  - **O gênero é sugerido pela relação** quando o card não diz o gênero (namorada/esposa → feminino; namorado/marido → masculino); o que o card diz sempre vale.
  - O gerador sem IA (Demo) reconhece as relações no pedido — "uma esposa chamada Marta", "meu marido Theo", "my girlfriend Nina"… — e escreve primeira mensagem e respostas de cada uma. Os prompts dos agentes (analista, designer, escritor e revisor do system prompt) também conhecem as quatro.
  - "Parceiro(a)" (`partner`) continua existindo como relação romântica genérica; cards antigos não mudam.
- Exportação Character Card V2 leva a nova relação (`extensions.asta.relationship`).

### Regras que continuam valendo
- **Menor de idade nunca tem relação romântica ou conjugal** (inclusive as novas): vira amigo(a), sempre SFW e platônico — pelo campo de idade ou por qualquer texto do card.
- **Pessoa real** continua sempre SFW (a relação é mantida, o conteúdo sexual não existe).

### Corrigido
- O seletor *Relação:* da caixa de criação cortava o texto ("Relationship: automatic" aparecia pela metade); a largura máxima aumentou para caber as opções.

### Testes
- Relações novas e antigas, gênero sugerido, SFW/NSFW em todas, menor de idade (por idade e por texto) e pessoa real, prompts de conversa, reconhecimento no Demo (português e inglês), geração pela API em SFW e NSFW, edição, exportação V2 e, no navegador, as opções na criação e no editor, o texto sem corte e o rótulo na lista.

## [0.3.0] — 2026-11-05

Atualização geral com foco em **personalização** e **experiência do usuário**. Tudo que já funcionava continua igual: o padrão é exatamente a aparência de sempre (tema escuro, destaque branco, tamanho 100%).

### Adicionado — personalização (Configuração → nova aba **Aparência**)
- **Tema escuro / claro / automático.** O automático segue o sistema e muda ao vivo. A aparência é aplicada por um script no `<head>` (`boot.js`) com o último valor guardado, **antes do primeiro quadro** — sem piscar de escuro para claro. O CSS inteiro foi migrado de cores fixas para variáveis; o grafo de nós do Canvas, o editor de vídeo e o visualizador de imagens ficam **sempre escuros** de propósito (como editores de mídia).
- **Cor de destaque:** 6 predefinidas ou qualquer cor; botões, seleções, barras de progresso e a sua bolha no chat seguem a cor, com texto preto ou branco escolhido pelo contraste.
- **Conforto:** tamanho da interface (90–150%, sem barras de rolagem a mais), densidade **compacta**, fonte (sistema, serifada, monoespaçada), tamanho do texto do chat e **reduzir animações** (respeita também `prefers-reduced-motion`).
- **Uso:** idioma (movido para a aba Aparência), **tecla de envio** — Enter ou **Ctrl/⌘+Enter** — no chat dos avatares e na caixa de criação (Shift+Enter e a composição de texto por IME continuam respeitados), **tela inicial** (Principal, qualquer tela ou "a última que usei") e atalhos de teclado ligados/desligados.
- **Barra lateral:** esconder as telas que você não usa (Principal e Configuração nunca somem; a tela atual sempre aparece; as escondidas seguem acessíveis pela busca).
- **Backup e padrões:** *Exportar configurações* (JSON **sem chaves de API nem tokens** — vozes, Hugging Face e provedores saem sem segredos), *Importar configurações* (só seções conhecidas, valores validados, **nunca** troca as chaves de quem importa) e *Restaurar padrões da aparência* (nunca mexe em chaves, avatares ou projetos). API: `GET /api/settings/export`, `POST /api/settings/import`, `POST /api/settings/reset`.
- As preferências vivem em `settings.ui` e são **validadas** (`asta/uiprefs.py`): um valor inválido, por API ou edição manual do `settings.json`, volta ao padrão em vez de quebrar a interface (cor só em hex, escala só entre as permitidas etc.).

### Adicionado — experiência
- **Paleta de comandos (`Ctrl/⌘+K`)** e botão *Buscar…* na barra lateral: vá a qualquer tela ou aba da Configuração, converse com/edite um avatar, abra um projeto ou canvas, ou rode ações (novo avatar, nova criação, alternar tema, recolher a barra, exportar configurações, ver atalhos, recarregar). Busca sem diferenciar acentos nem maiúsculas, navegação por setas/Enter/Esc, anunciada como diálogo com lista de opções.
- **Atalhos:** `Alt+1…7` (telas), `Alt+B` (barra lateral), `Alt+T` (tema), `?` (ajuda com todos os atalhos). Podem ser desligados; `Ctrl+K` sempre funciona.
- **Boas-vindas na primeira vez:** escolha de tema, cor e idioma com efeito ao vivo e o estado da IA (pronta, ou aviso de modo Demo com *Configurar IA*). Aparece **só numa instalação nova** (nada criado); quem já usa o ASTA nunca vê, e dá para rever em *Aparência → Rever as boas-vindas*.
- **Acessibilidade:** anel de foco visível só no teclado, link *Ir para o conteúdo*, nome acessível automático em botões só de ícone, diálogos com `role="dialog"` e foco devolvido a quem abriu, avisos (toasts) anunciados, título da página por tela (`ASTA — Biblioteca`…), `aria-current` na barra lateral.
- Telas e textos novos têm tradução para o inglês.

### Corrigido
- **Biblioteca → "Abrir" de um canvas** levava à lista de canvases em vez do editor (o endereço estava sem `/edit/`).
- A faixa "Modo Demo" do chat mostrava o motivo em português mesmo com a interface em inglês.

### Testes
- Preferências (padrões, valores válidos e inválidos, cor, idempotência), gravação/carregamento sanitizados, exportação **sem nenhum segredo**, importação segura (não troca chaves, ignora seções desconhecidas, rejeita arquivos errados), ida e volta entre instalações, restaurar padrões (voz e provedores recusados).
- Navegador: tema (inclusive aplicado antes do primeiro quadro e `auto` ao vivo), cor e contraste, escala sem barra de rolagem, densidade, fonte, animações, barra lateral, tela inicial e título, paleta (abrir, buscar avatar, Enter, Esc), atalhos (ligados/desligados), Ctrl+Enter vs. Enter no chat, exportar/restaurar e acessibilidade; boas-vindas numa instalação nova **e** a ausência dela para quem já usa.

### Observação
- Revi o tema claro com capturas de tela das principais telas (Principal, Configuração, Avatars, chat, Canvas), mas **não todas as telas em todos os estados**: se alguma cor ficar ruim no claro, o tema escuro (padrão) não é afetado.
- O tamanho da interface usa a propriedade CSS `zoom` (Chrome, Edge, Safari e Firefox 126+); em navegadores sem ela o ajuste simplesmente não tem efeito.
- Em telas de celular a busca (`Ctrl+K`) não tem botão (a barra inferior ficou como estava).

## [0.2.18] — 2026-11-05

Revisão de bugs em tudo que envolve **avatares** e **provedores de IA** (nuvem e local). Cada item abaixo foi reproduzido antes de corrigir e tem teste de regressão (`tests/test_ai_regressions.py`).

### Corrigido — provedores de IA
- **Servidores locais não respondiam com proxy no sistema.** Com `HTTP_PROXY` definido (rede corporativa/VPN), as chamadas ao Ollama, LM Studio e llama.cpp em `127.0.0.1` passavam pelo proxy, que não enxerga a máquina de quem pede. Agora `localhost`, `127.x`, `::1`, redes privadas (192.168.x, 10.x, 172.16–31.x) e nomes `.local` são acessados direto.
- **Endereço digitado do jeito comum quebrava:** `localhost:11434` (sem `http://`) dava o erro incompreensível *"Não foi possível conectar a completions: unknown url type"*; `http://localhost:11434` (Ollama sem `/v1`) dava 404. Agora o ASTA completa o `http://` e, nos servidores locais, o `/v1`; endereço realmente inválido mostra *"Endereço inválido…"*; e a mensagem de falha de conexão cita o servidor certo.
- **Erro no meio do streaming era engolido** (a resposta simplesmente vinha vazia). Agora o erro do provedor (limite de taxa, modelo que caiu…) aparece; no Claude, o erro de streaming mostra a mensagem em vez do JSON cru.
- **Resposta em lista de partes** (alguns servidores compatíveis com a OpenAI) quebrava com erro interno; agora é lida normalmente.
- **Claude (Anthropic) com "criatividade" acima de 1** (a interface vai até 1,5) recebia erro 400 em toda mensagem — a API aceita só 0–1. O valor agora é limitado.
- **Servidor sobrecarregado derrubava a mensagem do avatar.** Respostas 429/502/503/529 agora são repetidas até 2 vezes, respeitando o `Retry-After` (até 8 s). Cota ou crédito esgotado (que também vem como 429) **não** é repetido, nem erros de chave.
- **Modelo local (GGUF embutido):** (1) conversas longas estouravam a janela de contexto e o avatar parava de responder — agora o histórico é aparado (o prompt do avatar e a pergunta atual ficam; o resto entra do mais novo para o mais antigo) e o `max_tokens` é limitado à metade do contexto; (2) um estouro mesmo assim vira uma mensagem com o que fazer (aumentar a janela de contexto) e, nos pipelines, o agente cai nas regras em vez de derrubar a geração; (3) erros do llama.cpp viram erro de provedor, não exceção solta; (4) o modo JSON agora usa a gramática JSON do llama.cpp (respostas dos agentes mais confiáveis em modelos pequenos), com fallback para versões antigas; (5) a lista de modelos mostrava partes de modelos divididos e arquivos de visão (`mmproj`).
- **Botão Testar com o campo Modelo vazio** testava, escondido, o modelo que estava salvo (impossível testar o modo automático do LM Studio). Campo vazio agora vale vazio.

### Corrigido — avatares
- **Resposta vazia sumia sem aviso.** Quando o modelo devolvia nada, ou gastava todo o limite de tokens «pensando» (`<think>…</think>`, comum no LM Studio/Ollama), o avatar só parava de digitar. Numa conversa a dois agora aparece o aviso com a causa e o que fazer (*"…gastou todo o limite de resposta pensando… aumente o Máximo de tokens por resposta"* ou *"o provedor não devolveu nenhum texto…"*); num grupo o avatar fica quieto.
- **Histórico começando pela saudação do avatar** quebrava modelos com template estrito (Gemma, Mistral…: *"roles must alternate user/assistant"*). Agora a conversa sempre começa pelo usuário.
- **Fala interrompida era salva cortada no histórico** (quando você escrevia no meio da conversa livre). Agora é descartada.
- **Prefixo em negrito** (`**Aya:** oi`) deixava `**` solto na mensagem.
- **Menções sem acento** não eram reconhecidas ("julia" não chamava a "Júlia"; "theo" não chamava o "Théo"): o diretor de turnos agora ignora acentos e maiúsculas.
- **Regra do menor de idade — detecção mais completa.** Só pegava "15 years old", "tem 15 anos" e "idade: 15"; passava "uma garota de 15 anos", "jovem com 17 anos", "chica de 15 años", "15 aninhos", "criança", "adolescente", "colegial", "high school student", "menos de 18 anos"… Agora todos viram SFW e só amigo. Idades de **outras** pessoas ("tem 2 filhos de 12 anos", "her 12-year-old son") e durações ("casados há 12 anos", "10 anos de experiência", "um casamento de 12 anos") não geram falso positivo.
- **Cards importados do SillyTavern/Janitor/Chub** vêm com `{{char}}`, `{{user}}`, `<BOT>`, `<USER>` e `<START>`, que iam literalmente para o modelo. Agora são trocados pelo nome do avatar e do usuário (no prompt e na saudação); o card guardado mantém as macros, então a exportação continua compatível.
- **Apagar um avatar deixava conversas fantasma** que, ao abrir, quebravam a tela do chat. Agora conversas a dois somem, e em grupo o avatar sai (com as falas dele) e a conversa continua; a tela também volta para a lista se abrir uma conversa assim.
- **Configurações inválidas** (`history_turns`, `max_tokens`, `temperature`… com texto ou fora da faixa, por API ou edição manual) quebravam toda mensagem; agora são limitadas. Idem para `count` inválido na geração de avatares.
- **Erro inesperado do modelo cortava a resposta** no meio do streaming; agora vira um aviso na conversa. Corpos malformados nas rotas de conversa davam erro 500; agora 400.
- O pipeline de system prompt ignora um `system_prompt` que não seja texto (lista/objeto), em vez de gravar `['a', 'b']`.

### Observação
- Nos casos que exercitei, não encontrei problemas em: renderização do chat (não há XSS: o texto do modelo é inserido como texto), importação de cards PNG, memória de longo prazo e criação de avatares com respostas malformadas do modelo — esses fluxos foram exercitados e se comportaram bem.
- O modelo local real (`llama-cpp-python`) e um LM Studio/Claude reais não estão neste ambiente: os testes usam um `Llama` simulado (com o mesmo erro de contexto do original) e servidores HTTP simulados.

## [0.2.17] — 2026-11-05

### Adicionado
- **Suporte de primeira classe ao LM Studio para conversar com os avatares** (e para a geração e os NPCs). Antes o LM Studio era só um endereço OpenAI-compatível que você preenchia à mão; agora o ASTA fala com ele de verdade:
  - **Detecção automática:** o ASTA procura o servidor do LM Studio em `http://127.0.0.1:1234` (ou na URL configurada, com ou sem `/v1`; também numa outra máquina da rede) e, com o papel *Personagens* em **Automático**, usa o LM Studio quando ele está rodando **com um modelo carregado** — antes do modelo GGUF embutido e depois do provedor de geração configurado. A consulta tem cache curto (8 s) para um servidor desligado não atrasar as mensagens.
  - **Modelos:** usa a API nativa `/api/v0/models` (estado carregado/não carregado, tipo `llm`/`vlm`/`embeddings`, quantização, contexto) e cai em `/v1/models` nas versões antigas. Só aparecem os modelos de **chat** (os de embeddings ficam escondidos), com os carregados primeiro.
  - **Sem escolher modelo**, usa o que está carregado no LM Studio; **a visão é ligada sozinha** para modelos `vlm` (a escolha manual do usuário continua valendo); chave de API opcional.
  - **Erros que ensinam:** servidor desligado → *"Não consegui falar com o LM Studio… vá em Developer → Start Server (ou lms server start) e carregue um modelo"*; nenhum modelo carregado → lista o que está instalado; modelo inexistente → mensagem específica.
  - **Configuração → Provedores → LM Studio:** detecta o servidor (indicador ligado/desligado), lista os modelos (`●` carregado, `○` instalado, `👁` visão), escolhe com um clique e tem os botões **Usar nos avatares** e **Usar na geração**; não há mais a caixa manual de visão nesse cartão.
  - API: `GET /api/lmstudio` (estado, modelos e o que será usado); `asta doctor` mostra o estado do LM Studio.
- **Raciocínio escondido no chat:** modelos que escrevem o raciocínio junto da resposta (`<think>…</think>`: Qwen3, DeepSeek R1…, muito comuns no LM Studio e no Ollama) não mostram mais esse trecho nas mensagens dos avatares, nem durante o streaming.
- Testes: um **servidor LM Studio falso** (API nativa, API antiga, com chave, streaming) cobre a detecção, a lista filtrada, o modelo carregado, a visão, a escolha do usuário, as mensagens de erro, a escolha automática (antes do modelo embutido), o chat dos avatares ponta a ponta e o cartão da Configuração no navegador.

### Observação
- Não há LM Studio real neste ambiente de desenvolvimento: tudo foi testado contra um servidor simulado que segue a documentação pública da API (`/api/v0/models` e `/v1/chat/completions`). Se alguma versão do LM Studio responder diferente, o cartão mostra o erro e a rota genérica OpenAI-compatível continua valendo.
- O LM Studio pode carregar modelos sob demanda (JIT): ao escolher um modelo instalado mas não carregado, ele costuma ser carregado na primeira mensagem (a primeira resposta demora).

## [0.2.16] — 2026-11-05

### Corrigido
- **Os avatares respondiam com frases genéricas pré-programadas em vez de usar IA.** Causa: o papel *Personagens (chat e voz)* vinha fixo em **Demo** (o gerador por regras, sem IA) e só mudava se você o trocasse à mão — mesmo com um provedor de IA configurado na *Geração* ou com o modelo local instalado. Agora:
  - o padrão do papel é **Automático** (`active.characters = "auto"`): usa o provedor de **geração** se estiver usável (nuvem: com chave; local — Ollama, LM Studio, llama.cpp server, personalizado: com modelo) e, se não, o **modelo local de texto** (o escolhido em *Hugging Face GGUF* ou o pré-instalado, se o arquivo existir e o `llama-cpp-python` estiver instalado). O valor antigo `demo` desse papel passa a significar o mesmo que Automático; escolher um provedor específico continua forçando aquele provedor (e, se faltar a chave, o erro aparece, sem trocar por outro).
  - o **Demo só entra quando não existe nenhuma IA** — e a conversa mostra uma faixa **"Modo Demo: as respostas são pré-programadas, sem IA"** com o motivo (por exemplo, *"o modelo local Qwen3.8… está instalado, mas falta a biblioteca llama-cpp-python: rode asta libs --extras local"*) e o botão **Configurar IA**. Quando há IA, uma linha informa qual modelo está respondendo ("Responde com … · modelo").
  - a **criação de avatares** e o **pipeline de system prompt** usam a mesma regra (antes, com a Geração no Demo, criavam cartões genéricos por regras); se não houver IA, a criação segue no Demo mas devolve o aviso.
  - os NPCs dos mundos 3D (também no papel *Personagens*) passam a seguir a mesma escolha.
  - instalar o modelo pré-instalado não precisa mais trocar o papel *Personagens*: ele fica em Automático e já segue o modelo local (só a *Geração* é trocada, como antes).
  - API: `GET /api/avatars/engine` (qual IA responde e, se for Demo, por quê) e o evento SSE `provider` no início de cada rodada de conversa.
- Testes: escolha do provedor (padrão, seguir a geração, chave ou modelo faltando, escolha explícita respeitada, modelo local com e sem biblioteca, valor antigo `demo`), conversa respondida pela IA configurada (servidor simulado) e conversa em Demo avisando o motivo, criação usando a IA, e a faixa de aviso no navegador.

### Observação
- Se você **quer** o Demo de propósito (testar sem IA), basta não ter nenhum provedor usável: não há mais uma opção para forçar o Demo só nas conversas.
- Para ter IA de graça e local: instale o modelo pré-instalado (`asta models install`) **e** a biblioteca (`asta libs --extras local`, que compila código nativo); sem a biblioteca, a faixa de aviso diz exatamente isso. Não consegui exercitar aqui um modelo local real (sem `llama-cpp-python`): a escolha do modelo foi testada, não a geração com ele.
- Respostas de um modelo pequeno ainda dependem da qualidade dele e do system prompt do avatar (por isso o pipeline de system prompt).

## [0.2.15] — 2026-11-05

### Adicionado
- **A criação de avatars também usa o pipeline de system prompt.** Depois do Analista → Designer → Revisor, uma nova etapa **System prompts** roda o pipeline *Analisa → Gera → Revisa → Entrega* (o mesmo do editor, da 0.2.14) **em cada avatar criado**, e o texto final substitui o do Designer. O texto do Designer não é descartado: entra como ponto de partida ("mantenha o que está bom"), junto com o pedido original e, nos grupos, os nomes dos outros avatares (`knows`) para que cada um saiba com quem convive. O progresso aparece na tela de criação (*System prompts — Ana (1/2)*, depois quantos foram corrigidos pelo revisor).
- As regras fixas valem nessa etapa também, por código: se o pipeline concluir que o personagem é **pessoa real** ou **menor de idade**, o avatar vira SFW (menor também fica só amigo), mesmo que o usuário e o Designer tenham pedido NSFW; fictícios adultos mantêm o NSFW. O analista do pipeline pode marcar "real" mesmo quando o da criação marcou "fictício" (vale o mais restritivo); o tipo escolhido pelo usuário continua valendo mais que o palpite do modelo.
- Para pular a etapa (mais rápido, menos chamadas ao modelo): `prompt_pipeline: false` em `POST /api/avatars/generate`. Ela custa cerca de 3 chamadas a mais por avatar.
- Modo Demo (sem IA): o texto já escrito é mantido e só se acrescentam aparência, quem o avatar conhece, instruções e a nota de pessoa real, sem repetir o que já está lá (apertar *Gerar* de novo não empilha texto).
- Testes: cada avatar tem a sua análise/geração/revisão, o rascunho do Designer e o grupo chegam ao redator, a rodada de correção de um avatar, desligar a etapa, regras (real e menor) depois do pipeline e o modo Demo.

### Observação
- Uma criação com vários avatares fica mais lenta com um modelo de IA de verdade (mais chamadas). O pipeline com um modelo real não foi exercitado aqui: foi testado com um provedor roteirizado e com o modo Demo.

## [0.2.14] — 2026-11-05

### Adicionado
- **Pipeline de geração de system prompts de avatares: Analisa → Gera → Revisa → Entrega.** No editor do avatar, o cartão **Gerar o system prompt com IA** (nome, personalidade, aparência e instruções opcionais) roda quatro etapas, com o progresso de cada uma na tela:
  1. **Analisa** — descobre quem é o personagem (qualquer tipo: original, de uma obra, histórico, robô, criatura…; **real ou fictício**; idade; jeito de falar; relação com o usuário; limites; o que o modo SFW/NSFW permite; idioma);
  2. **Gera** — escreve o system prompt a partir da análise, mantendo o que o criador já tinha escrito de bom;
  3. **Revisa** — confere coerência com o card, voz, idioma, tamanho, não mencionar ser uma IA e as regras fixas; se reprovar, o redator corrige **uma vez** e a revisão roda de novo;
  4. **Entrega** — etapa determinística: tira cercas de markdown, **aplica as regras de segurança por código** (o que o modelo disser não as contorna) e, com `apply`, grava no avatar.
  - Resposta inválida ou vazia de um agente → fallback por regras: funciona também no modo Demo, sem IA.
  - API: `POST /api/avatars/system-prompt` (job com SSE; `avatar_id` ou `draft`, `instructions`, `content`, `character_type`, `detail`, `apply`).
- **Qualquer tipo de personagem, real ou fictício, em SFW e NSFW** — com uma regra fixa nova. Novo campo **tipo de personagem** (`character_type`: `fictional` | `real`) no card, no editor, na caixa de criação (*Tipo: automático*, *Personagem fictício*, *Pessoa real (sempre SFW)*) e na API de geração:
  - **fictício** (original ou de livro/filme/jogo/anime/mito…): SFW ou NSFW, desde que adulto;
  - **pessoa real** (viva ou histórica, famosa ou não, ou a de uma foto): dá para criar, mas **sempre SFW** — o ASTA **não cria conteúdo sexual sobre pessoas reais** (elas não consentiram). O prompt a apresenta como uma *interpretação ficcional e respeitosa*, nunca como a pessoa de verdade, sem inventar fatos privados, escândalos ou falas como se fossem reais. A regra vale até para cards importados ou editados à mão (`normalize_avatar` força SFW) e na conversa (o prompt de chat também a lembra);
  - o analista pode marcar sozinho (foto de pessoa → real); **a escolha explícita do usuário vale mais que o palpite do modelo**;
  - menores continuam sempre SFW e platônicos, em qualquer tipo.
  - O Character Card V2 exportado leva o tipo (`extensions.asta.character_type`) e ele é lido na importação.
- Testes: card real/fictício e a regra no cartão V2, prompt de chat, o pipeline completo (Demo e com provedor roteirizado: etapas em ordem, `apply`, real forçado a SFW, menor forçado a SFW mesmo se o modelo discordar, escolha do usuário vs. palpite do modelo, rodada de correção do revisor, reprovação final, respostas lixo/vazias), a API e a criação de avatars (real = SFW, fictício = NSFW), e o editor no navegador.

### Observação
- **Pessoa real + NSFW não existe**, por escolha: se você pedir NSFW para uma pessoa real, o ASTA cria o avatar em SFW e avisa. Isso complementa a regra antiga para fotos (que já ficavam em SFW); personagens fictícios adultos continuam podendo ser NSFW.
- O ASTA não consegue confirmar sozinho que um nome digitado é de uma pessoa real: ele depende do analista (modelo), da foto ou da sua escolha em *Tipo de personagem*. Se for uma pessoa real, marque *Pessoa real*.
- A criação de avatars (Principal → Avatar) continua usando o pipeline Analista → Designer → Revisor de antes (agora também com o tipo de personagem); o novo pipeline de system prompt é o do editor do avatar e da API.

## [0.2.13] — 2026-11-05

### Corrigido
- **Configuração continuava mostrando "error loading dynamically imported module: …/js/quant.js"**, mesmo depois de recarregar a página e reiniciar o ASTA. O arquivo `quant.js` (rótulos das quantizações dos modelos) tinha o mesmo nome de um script de rastreamento conhecido (Quantcast, `quant.js`) que **bloqueadores de anúncios e de rastreadores** — extensões como uBlock Origin/AdBlock e a proteção contra rastreamento do Firefox — barram pelo nome. O navegador recusava só esse arquivo e a tela de Configuração (que o importa) não abria; o servidor nunca teve problema. O arquivo agora se chama **`model_labels.js`** (o conteúdo é o mesmo) e passou a ser carregado normalmente, mesmo com esses bloqueadores ligados.
- A mensagem de falha ao carregar uma tela (da 0.2.12) agora também cita que uma **extensão de bloqueio** pode estar barrando um arquivo, com o que fazer (desativar para `localhost`).
- Testes: nenhum arquivo da WebUI pode usar nome de script de rastreamento conhecido (`quant.js`, `analytics.js`, `track.js`, `pixel.js`…), e os testes de recuperação do navegador passam a bloquear o `model_labels.js`.

### Observação
- Eu não tenho o navegador nem as extensões da sua máquina, então **não reproduzi o bloqueio**: o diagnóstico vem de o erro persistir só nesse arquivo, depois de recarregar/reiniciar, e de o nome coincidir com um item de listas de bloqueio conhecidas. Se a Configuração ainda não abrir depois de atualizar, a mensagem na tela traz o arquivo que falhou; teste com as extensões desativadas para `localhost` e me avise qual é o arquivo.
- A explicação da 0.2.12 (página aberta durante uma atualização) era uma hipótese que não se confirmou como causa deste caso; as proteções dela continuam valendo para esse outro cenário.

## [0.2.12] — 2026-11-05

### Corrigido
- **Configuração mostrava "Algo deu errado: error loading dynamically imported module: …/js/quant.js"** em vez de abrir. O erro acontece quando o navegador não consegue carregar um dos arquivos da tela — tipicamente porque o ASTA foi atualizado (ou reiniciado numa versão nova) com a página já aberta, e a página ficou com arquivos de uma versão diferente dos do servidor. Agora:
  - se uma tela não carrega, a página **recarrega sozinha uma vez** (sem laço) e a tela abre normalmente;
  - se continuar falhando, aparece uma mensagem clara (*"Não foi possível carregar esta tela. Isso costuma acontecer quando o ASTA é atualizado com a página aberta"*) com o botão **Recarregar a página**, a dica de Ctrl+F5 / reiniciar o `asta` e o detalhe técnico, em vez de só o erro cru;
  - se o servidor for reiniciado numa versão nova com a página aberta, a página se recarrega sozinha;
  - se o ASTA foi atualizado em disco mas o processo em execução ainda é o antigo, a barra lateral avisa **"Versão X instalada: feche o ASTA e abra de novo"** (`/api/state` agora informa `disk_version`).
- Testes: no navegador, o arquivo `quant.js` é bloqueado (sempre, e só na primeira vez) e a Configuração tem de se recuperar ou explicar; e a versão em disco no `/api/state`.

### Observação
- **Não consegui reproduzir a falha original** (aqui o `quant.js` é servido normalmente, inclusive em 500 requisições paralelas, e o pacote instalável inclui todos os arquivos), então a causa exata na sua máquina não está confirmada. A correção cobre o cenário mais provável (página aberta com arquivos de outra versão) e torna qualquer falha de carregamento recuperável e explicada. Se ainda aparecer a mensagem nova depois de recarregar e reiniciar o `asta`, o detalhe técnico mostrado nela (e o console do navegador, F12) dizem qual arquivo falhou e por quê.

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

[Não lançado]: https://github.com/KMC1525/ASTA/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/KMC1525/ASTA/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/KMC1525/ASTA/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/KMC1525/ASTA/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/KMC1525/ASTA/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/KMC1525/ASTA/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/KMC1525/ASTA/compare/v0.2.18...v0.3.0
[0.2.18]: https://github.com/KMC1525/ASTA/compare/v0.2.17...v0.2.18
[0.2.17]: https://github.com/KMC1525/ASTA/compare/v0.2.16...v0.2.17
[0.2.16]: https://github.com/KMC1525/ASTA/compare/v0.2.15...v0.2.16
[0.2.15]: https://github.com/KMC1525/ASTA/compare/v0.2.14...v0.2.15
[0.2.14]: https://github.com/KMC1525/ASTA/compare/v0.2.13...v0.2.14
[0.2.13]: https://github.com/KMC1525/ASTA/compare/v0.2.12...v0.2.13
[0.2.12]: https://github.com/KMC1525/ASTA/compare/v0.2.11...v0.2.12
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
