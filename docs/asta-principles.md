# asta-principles — os princípios do ASTA

> Documento interno do projeto. Define **o que o ASTA é e o que ele nunca deixa de ser**, hoje e no futuro. Quem desenvolve o ASTA (pessoa ou modelo de IA) lê este arquivo antes de decidir
> qualquer coisa e segue o [`asta-dev-guide.md`](asta-dev-guide.md), que transforma estes princípios em regras de trabalho. Em caso de conflito entre uma ideia e um princípio, **vence o princípio**.
> *(English summary at the bottom.)*

Os oito princípios, em ordem de importância quando dois deles disputam a mesma decisão:

1. [Usuário com controle total dos seus dados](#1-o-usuário-tem-controle-total-dos-seus-dados)
2. [Tudo open source](#2-tudo-open-source)
3. [Foco local](#3-foco-local)
4. [Cloud dos dados do usuário é opcional](#4-cloud-dos-dados-do-usuário-é-opcional)
5. [Interoperabilidade total entre tudo](#5-interoperabilidade-total-entre-tudo)
6. [Integrado com IA em tudo](#6-integrado-com-ia-em-tudo)
7. [Sistemas multi-agentes, multi-steps](#7-sistemas-multi-agentes-multi-steps)
8. [Federation](#8-federation)

---

## 1. O usuário tem controle total dos seus dados

**O que significa.** Tudo que a pessoa cria, escreve, envia ou configura (conversas, personagens, mundos, jogos, projetos do Studio, canvases, anexos, chaves de API, memórias dos avatars) é **dela**:
ela vê onde está, copia, move, exporta, apaga e leva embora — sem pedir permissão a ninguém, sem conta, sem prazo.

**Como se aplica.**
- Dados em arquivos comuns, em formatos abertos e legíveis (JSON, PNG/JPG, MP4/WAV/MP3, GGUF, ZIP), dentro de uma pasta que o usuário conhece (`~/.asta`, `asta folder`). Nada de banco de dados opaco ou formato fechado. O histórico passo a passo do Computer Use, as capturas de tela e a lixeira dele também (`~/.asta/computer`), e o usuário os apaga quando quiser.
- **Atualizar ou desinstalar nunca apaga os dados.** Qualquer limpeza (órfãos, duplicados) mostra a **prévia** e só age com confirmação (`Configuração → Desempenho → Armazenamento`).
- Exportar e importar tudo (configurações sem chaves, ZIP de canvases/jogos/mundos, cards de personagem em PNG) e **apagar de verdade** (a biblioteca e as conversas têm *Apagar*).
- Chaves de API ficam em `settings.json` com permissão `600` e **nunca** voltam ao navegador; segredos não entram em backups exportados.
- **Sem telemetria.** O ASTA não envia uso, texto, anexos ou métricas para ninguém. As únicas conexões externas são as que a pessoa pediu: o provedor de IA escolhido, a busca na web, downloads (modelos, atualizações).
- Anexos e pacotes (ZIP/RAR) são tratados como **não confiáveis**: abrir um pacote nunca escreve fora da pasta de destino nem preenche o disco.

**O que NÃO fazer.** Formato proprietário; dado que só abre dentro do ASTA; cópia dos dados da pessoa para fora do computador sem ela pedir; apagar ou "otimizar" arquivos sem prévia e confirmação; exigir login para usar o que roda local.

**Estado atual.** Cumprido. Próximo: um comando/tela de "exportar tudo" em um clique (hoje há exportação por parte).

## 2. Tudo open source

**O que significa.** O código é aberto (licença MIT), auditável e bifurcável — **inclusive o que gera os instaladores** (workflows, scripts, núcleo em Rust, app Android). A pessoa pode ler o que roda no computador dela, modificar e redistribuir.

**Como se aplica.**
- Dependências: o núcleo usa **só a biblioteca padrão** do Python e do Rust. Bibliotecas opcionais são open source e entram como *extras*. Componentes de terceiros embutidos têm a licença registrada (ex.: `three.js` em `asta/runtime/vendor`).
- Nada de serviço fechado obrigatório: toda função que usa um serviço pago/proprietário (provedores de IA na nuvem) tem alternativa **local e aberta** (Ollama, LM Studio, llama.cpp, modelos GGUF, o provedor Demo offline).
- Modelos de IA locais sugeridos são de pesos abertos; o ASTA não esconde a licença deles.
- Os instaladores são gerados por CI público a partir do código do repositório; o hash de cada arquivo fica em `SHA256SUMS.txt` na Release.
- A IA escreve **dados** (JSON) que o motor valida, nunca código que o ASTA executa — o comportamento é auditável.

**O que NÃO fazer.** Parte do código só em binário; "versão pro" fechada; dependência obrigatória de serviço que a pessoa não possa trocar; ofuscação.

**Estado atual.** Cumprido (MIT). Os instaladores do macOS e do Windows ainda não são **assinados** (exige certificado pago); isso é dito às claras no README.

## 3. Foco local

**O que significa.** O ASTA nasce para **rodar no computador (e agora no aparelho) da pessoa**: funciona sem internet quando usa modelos locais, não depende de um servidor nosso e escolhe o jeito de usar o hardware **com economia** de RAM, VRAM, CPU e disco.

**Como se aplica.**
- O servidor escuta só em `127.0.0.1`; sair disso exige pareamento por QR code (e, no app Android, o próprio motor roda **dentro do aparelho**, sem computador).
- **Núcleo em Rust obrigatório**, com o Python como orquestrador e espelho de tudo: o Rust planeja a carga de modelos (camadas na GPU, contexto que cabe — até 1M de tokens com cache de atenção de 4 bits —, threads), vigia memória, lê cabeçalhos GGUF/safetensors, escaneia pastas, acha arquivos idênticos e agenda vários agentes locais. Instaladores trazem a biblioteca pronta; sem ela o ASTA continua em Python, só mais devagar.
- Modo de desempenho (Leve/Equilibrado/Máximo) controla RAM/VRAM **e** CPU (ffmpeg com menos threads e prioridade baixa); modelos ociosos são descarregados e a memória **devolvida ao sistema**; arquivos de modelo saem do cache de páginas.
- O ASTA **adapta-se ao hardware** (nível baixo/médio/alto) e nunca contraria um valor que o usuário definiu à mão (ex.: janela de contexto).

**O que NÃO fazer.** Exigir internet para o que é local; subir dados para processar fora; "aquecer" modelos em segundo plano sem a pessoa pedir; ocupar disco sem avisar.

**Estado atual.** Cumprido. Limite honesto: modelos pesados locais (GGUF/PyTorch) não rodam dentro do celular; no app Android eles vêm de um servidor na rede (Ollama, LM Studio) ou do ASTA de um computador.

## 4. Cloud dos dados do usuário é opcional

**O que significa.** Sincronizar, fazer backup ou hospedar os dados em nuvem é **uma escolha da pessoa**, nunca um requisito nem um padrão. Quando existir, é **cliente-side**: a pessoa escolhe o destino (a conta dela, o servidor dela), e os dados vão **criptografados** e exportáveis.

**Como se aplica.**
- Hoje: nenhuma nuvem do ASTA. O "cloud" possível é o que a pessoa já tem — copiar `~/.asta` para o Drive/Dropbox/NAS, ou apontar `--home`/`ASTA_HOME` para uma pasta sincronizada.
- Provedores de IA na nuvem (Claude, ChatGPT, Gemini…) são **opt-in**, com a chave da própria pessoa; o texto vai para eles apenas quando ela escolhe esse provedor.
- Qualquer recurso futuro de sincronização deve: ser desligado por padrão, funcionar com destino à escolha do usuário (WebDAV/S3/Git/pasta), criptografar antes de sair e permitir desfazer tudo (baixar e apagar o remoto).

**O que NÃO fazer.** Conta obrigatória; nuvem própria como padrão; sincronizar "para ajudar" sem pedir; chave de criptografia que a pessoa não controle.

**Estado atual.** Princípio respeitado; sincronização opcional ainda não existe (ver [Futuro](#futuro-e-lacunas-honestas)).

## 5. Interoperabilidade total entre tudo

**O que significa.** Tudo conversa com tudo: **entre as seções do ASTA** (um resultado do Chat vira um mundo, um avatar, um jogo, um canvas ou um vídeo; um nó do Canvas alimenta o Studio), **entre provedores** (qualquer modelo em qualquer seção) e **com o mundo de fora** (formatos e protocolos abertos).

**Como se aplica.**
- Um **único anexo** (texto, documento, imagem, áudio, vídeo, **ZIP/RAR/7z/TAR**) funciona em **todas** as seções. Pacotes são abertos com segurança e cada arquivo vira um anexo.
- **Todo** provedor de texto funciona em **toda** seção (bateria `tests/test_all_providers.py` e `tests/test_v014_providers.py` garantem). APIs compatíveis com a OpenAI e a da Anthropic cobrem nuvem e local; novos provedores entram pelo mesmo contrato (`providers/base.py`).
- Formatos abertos de entrada e saída: cards de personagem (PNG com metadados, Tavern/SillyTavern), ZIP de jogos (HTML/CSS/JS puro) e de mundos, GGUF/safetensors, MP4/M4A/MP3/WAV, `.zip` de canvas. O Rebuild lê Ren'Py e RPG Maker.
- Mesma interface em PC, navegador de celular (PWA) e app Android; mesma API HTTP local para scripts e integrações.
- Limites sempre **aprendidos do provedor** (teto de tokens, janela de contexto), nunca assumidos: o ASTA se adapta ao que cada modelo aceita.

**O que NÃO fazer.** Recurso que só funciona com um provedor; formato fechado; seção que não aceita os anexos das outras; quebrar a API pública sem aviso e migração.

**Estado atual.** Forte. Lacuna: padronizar um "pacote ASTA" único para mover um projeto inteiro entre instalações.

## 6. Integrado com IA em tudo

**O que significa.** A IA não é uma aba: está **em cada ferramenta** — para criar, editar, revisar, resumir, traduzir e decidir — e **sempre com o usuário no comando**. A IA sugere e executa quando pedida; nada pesado roda por conta própria.

**Como se aplica.**
- Chat, Mundos 3D (NPCs são agentes), Avatars (conversa, memória, grupo), Jogos 2D, Canvas (nós de IA), Studio (roteiro, análise, edição automática), Rebuild (revisão de texto) — todos usam o mesmo contrato de provedor e as mesmas regras de conteúdo e de tamanho de resposta.
- A IA escreve **dados validados**; se a resposta vier inválida, há **fallback determinístico** (regras do ASTA) e a entrega nunca falha por culpa do modelo.
- Ferramentas de criação só começam quando o usuário aciona (✦ Criar → Run). O Chat apenas **sugere**.
- Respostas **longas e de qualidade** são prioridade: estilo Detalhado/Longo e profundo, continuação automática quando bate no limite, teto de tokens aprendido por modelo, contextos de até 1M de tokens.
- **Computer Use** (opcional, desligado por padrão) é o único lugar em que a decisão da IA vira **ação no computador** — por isso ela só escolhe entre ações de um **catálogo fechado** (JSON validado, nunca código ou shell), em dois modos escolhidos pelo usuário: **Ask** (Sim/Não antes de agir) e **Full Access** (sem perguntar). Limites fixos valem nos dois (segredos, dados do ASTA, pastas do sistema, interpretadores), nada é apagado de verdade (lixeira) e tudo se **desfaz**.

**O que NÃO fazer.** Chamar a IA sem o usuário saber; esconder o provedor/modelo usado; gastar tokens sem necessidade (emojis, enrolação); executar código escrito pela IA.

## 7. Sistemas multi-agentes, multi-steps

**O que significa.** O trabalho de qualidade sai de **equipes de agentes pequenos e focados**, em **etapas** com conferência (Analista → Planejador → Criador → Revisor → Empacotador), e não de um prompt gigante em um modelo só.

**Como se aplica.**
- Cada seção/ferramenta tem sua equipe: **Computer Use** (Planejador → Operador → Revisor → Relator, até 8 tarefas em paralelo, com fallback por regras), Mundos (analista, planejador, personagens, arquiteto, som/UX, revisor), Avatars (analista, designer, revisor), Jogos (analista, designer, revisor), Studio (showrunner + cena a cena; edição automática com Analista, Diretor, Revisor), Canvas (fluxo de nós), Rebuild (Perfilador, Polidor, Auditor) e **Chat** (modo *Equipe de agentes*: Planejador → Redator → Revisor).
- Cada agente tem entrada/saída em JSON validada, **fallback** e registro (`prompts/` no pacote). Falha de um agente nunca derruba a entrega.
- Vários agentes **locais** dividem o mesmo modelo por uma **fila com prioridade** (o que a pessoa espera passa à frente do que roda em segundo plano), um pool de modelos residentes decidido pela memória livre, e plano de execução do núcleo Rust.
- Qualquer modo, seção ou ferramenta **nova** nasce com ao menos um desenho multi-agente/multi-step, mesmo que simples (planejar → fazer → conferir).

**O que NÃO fazer.** Ferramenta nova com uma única chamada solta sem etapa de conferência; agente que não sabe falhar; paralelismo que passe do que o hardware aguenta.

## 8. Federation

**O que significa.** Muitos ASTAs independentes — cada um no seu computador, servidor ou celular — podem **se conectar e trocar** coisas (mundos, avatars, jogos, canvases, modelos, conversas compartilhadas) **sem uma central**, por escolha de cada dono, em protocolos e formatos abertos. Ninguém é obrigado a entrar; ninguém controla a rede.

**Como se aplica (direção).**
- Identidade e confiança **por instância**, controladas pelo dono (como o pareamento por QR code de hoje).
- Troca por **pacotes assinados e versionados** em formato aberto (o mesmo ZIP/JSON que a pessoa já exporta), transportados por HTTP entre instâncias, por arquivo ou por um repositório Git — sempre iniciada por uma pessoa.
- Compartilhamento **opt-in, item por item**, com a licença do item; remoto nunca recebe chaves, memórias privadas ou anexos sem permissão explícita.
- Evoluir os protocolos existentes (pareamento, `/api/version`, exportação) em vez de inventar um servidor central.

**Estado atual.** **Ainda não implementado** — é direção, não funcionalidade. Já existe a base: pareamento por QR, API HTTP local documentada, pacotes exportáveis, modo "conectar a um ASTA de outro computador" no app Android.

---

## Como usar este documento

Antes de uma decisão de produto ou de arquitetura, pergunte:

1. Isso tira o controle dos dados do usuário? → **não faça**.
2. Isso exige serviço fechado, conta ou nuvem nossa? → **não faça** (ou torne opcional e com alternativa aberta).
3. Funciona local e sem internet quando o modelo é local? → precisa funcionar.
4. Funciona com **qualquer** provedor, em **qualquer** seção, com **qualquer** anexo? → precisa funcionar.
5. Tem equipe multi-agente/multi-step e fallback? → precisa ter.
6. Está documentado (README, CHANGELOG) e testado? → só então termina.

### Futuro e lacunas honestas

- Federation: protocolo e pacote assinado (acima) — pesquisa e primeiro protótipo.
- Sincronização/backup opcional criptografado (destino à escolha).
- Exportar/importar um projeto inteiro em um único "pacote ASTA".
- Assinar os instaladores do Windows/macOS quando houver certificado.

---

## English summary

ASTA is **fully open source (MIT)**, **local-first**, with **optional** user-controlled cloud, built for **total interoperability** (any provider in any section, any attachment — including ZIP/RAR — anywhere, open formats), with **AI integrated in every tool** and **multi-agent, multi-step** systems everywhere, and a long-term **federation** direction (independent instances that exchange signed, versioned packages, opt-in and without a central server — *a direction, not yet implemented*).
Above all: **the user has total control of their data** — open file formats in a folder they know, no telemetry, nothing deleted or sent anywhere without their say, and updating or uninstalling never touches their data.
When an idea conflicts with a principle, the principle wins. Day-to-day rules live in [`asta-dev-guide.md`](asta-dev-guide.md).
