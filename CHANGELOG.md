# Changelog

Todas as mudanças relevantes do ASTA são registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.17.21] — 2026-11-09

### Adicionado — suporte ao FLUX.2 klein (`black-forest-labs/FLUX.2-klein-4B` e 9B)
- **Hugging Face local (diffusers):** o `black-forest-labs/FLUX.2-klein-4B` (pipeline `Flux2KleinPipeline`) agora carrega — se o `AutoPipeline` da versão instalada do diffusers ainda não o conhece, a classe vem do `model_index.json`; se nenhuma versão o carrega, o erro diz para rodar `pip install -U diffusers transformers`. O modelo é destilado: roda com **4 passos e guidance 1,0** (a variante «base», com 50 passos e guidance 4), e o pipeline não recebe prompt negativo (o do FLUX não aceita). O download já ignora o `flux-2-klein-4b.safetensors` da raiz, que repete os pesos de `transformer/`. O modelo aparece entre as sugestões do provedor.
- **Edição com várias imagens:** o klein edita pelo próprio pipeline com **até 4 imagens de uma vez** (no Hugging Face local e no GGUF, via `ref_images`) — ideal para os `@` do node Texto.
- **GGUF (stable-diffusion.cpp):** o FLUX.2 klein (`leejet/FLUX.2-klein-4B-GGUF`, `unsloth/FLUX.2-klein-4B-GGUF`…) agora é uma família própria. Antes, `flux` casava com FLUX.1 e pedia `clip_l` e `t5xxl`, que o FLUX.2 não usa. Agora o ASTA acha o **VAE do FLUX.2** (`flux2-vae.safetensors`) e o **codificador de texto Qwen3** (4B para o klein 4B, 8B para o 9B; o Qwen3-4B-Instruct do Z-Image não serve) na mesma pasta, aplica os parâmetros do klein (4 passos, CFG 1; «base»: 50 passos, CFG 4) e, se faltar algo, oferece o botão **Baixar os arquivos de apoio** (≈ 0,3 GB de VAE + 2,5 GB do Qwen3-4B).
- O FLUX.2 **dev** (32B, codificador Mistral 24B) não tem família: não é mais tratado como FLUX.1.
- Passos e guidance padrão por modelo: FLUX.1 dev 28 passos e guidance 3,5; FLUX.1 schnell 4 passos.
- Versão 0.17.21 (o núcleo Rust não mudou).

## [0.17.20] — 2026-11-09

### Corrigido — node Texto com várias referências (`@`) na hora de gerar/editar imagens
- **Imagens enviadas em dobro.** Um `@foto-perfil` no Texto e o node Mídia com a mesma foto ligado em «Referências» mandavam a imagem duas vezes ao modelo (4 citações + 4 ligadas = 6 imagens, só 4 diferentes): as cópias ocupavam vagas do limite e a numeração «(reference image N)» do prompt passava a apontar também para cópias. Agora as referências repetidas (mesmo conteúdo) valem uma vez, na ordem de quem aparece primeiro: as citadas no texto e depois as ligadas.
- `@foto_perfil` (com sublinhado) agora também casa com `foto-perfil`, no servidor e nas fichas do node.
- Se uma imagem citada não puder ser lida (arquivo ausente, vídeo sem quadro), o nó avisa em vez de seguir com a numeração das referências trocada.
- **Texto cortado.** O campo de texto (Texto, Texto IA, Imagem, Vídeo…) agora cresce junto com o conteúdo, até um limite, em vez de esconder o fim de um prompt longo; o que você puxou à mão não é encolhido.
- **Conexões que ficavam no lugar errado** ao redimensionar ou ao crescer um campo: as linhas entre os nós agora se redesenham sempre que a altura de um nó muda.
- Ao escolher uma menção na lista, não entra mais um espaço a mais quando já há espaço ou pontuação depois.
- Versão 0.17.20 (o núcleo Rust não mudou).

## [0.17.19] — 2026-11-09

### Corrigido — referências de imagem nos nós com modelo local
- **Modo Gerar não vira imagem → imagem.** Desde a 0.17.10, qualquer imagem ligada em «Referências» (ou citada com `@`) num nó com modelo local virava a imagem de partida: numa thumb com `@foto-perfil`, `@fnaf-1-office`… a primeira imagem virava a base e as outras eram ignoradas sem aviso. Agora os modelos locais só usam as referências no modo **Editar**; no modo Gerar elas viram só texto, com aviso no nó.
- No modo Editar, o nó diz quantas imagens o modelo realmente usa (1 nos modelos comuns; até 4 nos de edição, como Qwen-Image-Edit e FLUX Kontext) e avisa quantas ignorou.
- Quando as imagens citadas com `@` não chegam ao modelo, o prompt perde a marcação «(reference image N)», que não apontaria para nada.
- Verificado sem achar problema: encadeamento Imagem → Imagem → Imagem (incluindo `count` 2 e modo Editar), execução só do nó final refazendo o que mudou, cache, e nós pulados após falha.
- **O erro do `qwen-image-2.1`** continua sendo a arquitetura do arquivo (265 tensores; módulos compartilhados em vez de `img_mod.1.weight` por bloco), que a stable-diffusion.cpp 0.4.7 não reconhece. Atualize o ASTA (0.17.18+) para o botão «Atualizar a biblioteca agora» funcionar sem o `cmake`.
- Versão 0.17.19 (o núcleo Rust não mudou).

## [0.17.18] — 2026-11-09

### Corrigido — a stable-diffusion.cpp mais nova agora se instala e se atualiza sozinha
- O botão «Atualizar a biblioteca agora» parava com «falta instalar: cmake». O `cmake` (e o `ninja`) **não precisam estar instalados**: o build da biblioteca os baixa sozinho pelo pip. Agora o ASTA só confere o que realmente falta — `git` e um compilador C/C++ — e, se faltar, mostra o comando certo para o seu sistema (`sudo apt install git build-essential`, `xcode-select --install`…).
- **Automático na instalação e na atualização** (`asta libs`, usado pelos instaladores e pelo `asta update`): quem tem um GGUF de difusão baixado (Qwen-Image, FLUX…) ou já teve um modelo não reconhecido recebe a stable-diffusion-cpp-python mais nova do GitHub, **só quando o GitHub tem um commit novo** desde a última compilação (guardado em `sd_built_sha`) — sem recompilar a cada atualização. `ASTA_SD_LATEST=never` desliga; `always` vale para todos; `asta libs --sd-latest` força.
- A saída do botão não mostra mais o resumo das outras bibliotecas («Bibliotecas prontas: nenhuma…»), só o que importa para a compilação.
- Versão 0.17.18 (o núcleo Rust não mudou).

## [0.17.17] — 2026-11-09

### Corrigido — mensagem de erro do modelo não reconhecido cortada e sem saída
- O erro do nó era cortado em 800 caracteres (terminava em «(preci»). O limite agora é 1600 e a mensagem ficou bem mais curta.
- O arquivo do modelo (`qwen-image-2.1-Q4_K_M.gguf`, 265 tensores com nomes como `img_in.weight`, `modulation.1.weight`, `norm_out.linear.weight`, `proj_out.weight`) não tem o tensor `transformer_blocks.0.img_mod.1.weight` do Qwen-Image: a arquitetura não é a que a stable-diffusion.cpp 0.4.7 (a mais nova do PyPI) conhece. A mensagem agora mostra os nomes de fora dos blocos e os do primeiro bloco, que revelam a arquitetura.
- Novo botão **«Atualizar a biblioteca agora»** no nó com esse erro: compila a stable-diffusion-cpp-python mais nova do GitHub (`asta libs --sd-latest`; precisa de git, cmake e compilador C++; leva minutos), com o progresso no botão, e depois é só rodar o nó de novo (o modelo roda em processo próprio: não precisa reiniciar o ASTA).
- Versão 0.17.17 (o núcleo Rust não mudou).

## [0.17.16] — 2026-11-09

### Corrigido — o ASTA fechava («Falha de segmentação») ao gerar imagem com um modelo GGUF
- A stable-diffusion.cpp é código C++: ao recusar um modelo que não reconhece (`get sd version from file failed`) ou ao faltar memória, ela **derruba o processo inteiro** — e o Python não consegue interceptar isso. Conferir o arquivo antes (v0.17.15) só cobria um caso.
- Agora o modelo roda **sempre em um processo à parte** (`asta/canvas/sd_worker.py`), que fica carregado entre uma imagem e outra (sem recarregar a cada vez) e some junto com o modelo quando você troca de modelo ou o ASTA descarrega a memória. Se a biblioteca cair, cai só esse processo: o nó mostra o erro (modelo não reconhecido, falta de memória, ou «o processo fechou de repente (código -11)»), com o log da biblioteca e, para Qwen-Image/FLUX, os nomes de tensores do arquivo; a próxima geração sobe outro processo. O ASTA continua aberto.
- Imagem → imagem e edição (v0.17.10) funcionam igual: as referências seguem como arquivos para o processo. `ASTA_SD_INPROC=1` volta ao modo antigo, no mesmo processo.
- Versão 0.17.16 (o núcleo Rust não mudou).

## [0.17.15] — 2026-11-09

### Corrigido — o ASTA fechava («Falha de segmentação») ao gerar com um GGUF que a stable-diffusion.cpp não reconhece
- A stable-diffusion.cpp só reconhece o Qwen-Image se o arquivo tem o tensor `transformer_blocks.0.img_mod.1.weight` (e o FLUX, `double_blocks.`). Sem ele ela recusa o modelo e, ao desistir, **derruba o programa inteiro** — um erro de C que o Python não consegue interceptar.
- Agora o ASTA lê o cabeçalho do GGUF (só os nomes dos tensores, sem carregar pesos) antes de entregá-lo à biblioteca. Se o tensor esperado não está lá, a carga é testada num **processo à parte**: se ele cai ou recusa, o nó mostra o erro (com o tensor esperado, alguns nomes que o arquivo tem e o código de saída) e o ASTA continua de pé. Arquivos que passam na conferência carregam como antes, sem custo extra.
- O erro também deixa o aviso para o `asta update`/`asta libs` tentar a biblioteca mais nova.
- Versão 0.17.15 (o núcleo Rust não mudou).

## [0.17.14] — 2026-11-09

### Adicionado/Corrigido — a biblioteca de imagem mais nova entra na instalação e na atualização
- **A v0.17.13 foi mergeada sem o segundo commit**: a proteção contra a «Falha de segmentação» (nunca gerar com um modelo que não carregou) e a explicação do `get sd version from file failed` não chegaram à `main`. Estão de volta nesta versão.
- A stable-diffusion-cpp-python do PyPI já é a mais nova publicada (0.4.7), então `pip install -U` não resolve um modelo que ela não reconhece. Agora, quando o Canvas descobre isso, ele deixa um aviso e o `asta libs` — que roda na **instalação** e na **atualização** (`asta update`) — compila a versão mais nova **do GitHub** (precisa de git, cmake e um compilador C++; leva alguns minutos; se faltar algo, o ASTA diz o quê). Depois de instalar, o aviso some e não recompila a cada atualização.
- `asta libs --sd-latest` força isso a qualquer momento; `ASTA_SD_LATEST=never|auto|always` controla o comportamento (padrão: `auto`).
- Versão 0.17.14 (o núcleo Rust não mudou).

## [0.17.13] — 2026-11-09

### Corrigido — «NULL pointer access»: o modelo na verdade não carregava (e o motivo era apagado)
- Causa real, achada no código da stable-diffusion-cpp-python 0.4.7: quando o modelo **não carrega**, a biblioteca não dá erro (ela confere `is None`, mas a carga que falha devolve um ponteiro nulo, que não é `None`) e segue com um contexto vazio; a geração só falha depois, com «NULL pointer access». O motivo verdadeiro (memória, formato…) é registrado na hora da **carga** — e o ASTA apagava esse log antes de gerar. Por isso a mensagem sempre dizia «nenhum motivo».
- Agora o ASTA confere se o modelo carregou, guarda o log da carga e mostra o motivo (com dica de memória quando for o caso) e os arquivos carregados. Um modelo que não carregou nunca fica em cache.
- Se a carga falha com `diffusion_flash_attn`/`offload_params_to_cpu`, tenta de novo sem eles antes de mostrar o erro.
- **A segunda tentativa da v0.17.12 podia derrubar o programa** («Falha de segmentação» ao gerar): ela chamava a geração com um modelo que não tinha carregado, e a stable-diffusion.cpp acessa o ponteiro nulo. Agora a geração nunca é chamada sem um modelo carregado.
- Se o log traz `get sd version from file failed`, a stable-diffusion.cpp da biblioteca instalada é mais antiga que o modelo e não o reconhece: o erro diz para atualizar a biblioteca (`pip install -U stable-diffusion-cpp-python`) e não tenta de novo.
- Versão 0.17.13 (o núcleo Rust não mudou).

## [0.17.12] — 2026-11-08

### Corrigido — «NULL pointer access» no Qwen-Image GGUF mesmo com VAE e codificador de texto certos
- A mensagem mostrou que os arquivos de apoio certos estavam carregados e que a biblioteca não registra motivo nenhum: a falha é silenciosa dentro da stable-diffusion.cpp. As opções que o ASTA ligava por padrão no Qwen-Image/FLUX (`diffusion_flash_attn` e `offload_params_to_cpu`) não funcionam em todos os backends (CPU, Vulkan, placas antigas) e fazem a geração voltar nula.
- Agora, se a geração falha com ponteiro nulo, o ASTA tenta de novo (1) com resolução menor e (2) recarregando o modelo **sem** flash attention e sem descarregar pesos para a RAM, e lembra disso para o modelo na mesma sessão (não recarrega a cada imagem).
- O erro final traz a versão da stable-diffusion-cpp-python e o backend em uso, para identificar o que a sua máquina usa.
- Versão 0.17.12 (o núcleo Rust não mudou).

## [0.17.11] — 2026-11-08

### Corrigido — «NULL pointer access» no Qwen-Image GGUF: VAE errado
- Causa provável: o Qwen-Image aceitava como VAE qualquer `ae.safetensors` ou `vae` da pasta. O `ae.safetensors` é o VAE do **FLUX e do Z-Image** (o Z-Image pré-instalado o deixa na mesma pasta), e não serve ao Qwen-Image: o modelo carregava com o VAE errado e a geração falhava sem motivo claro. Agora só vale o `qwen_image_vae.safetensors`; sem ele, o nó oferece baixar o arquivo certo (botão «Baixar os arquivos de apoio»).
- Parâmetros de geração do Qwen-Image como na documentação da stable-diffusion.cpp: `flow_shift` 3 e amostrador `euler`.
- Quando a biblioteca não registra motivo nenhum, a mensagem diz isso e lista os arquivos de apoio que foram carregados (para ver na hora se algum está errado).
- Versão 0.17.11 (o núcleo Rust não mudou).

## [0.17.10] — 2026-11-08

### Corrigido — editar imagens com modelos locais e ligações entre nós
- **Modelos locais agora editam de verdade.** Antes, ligar uma imagem em «Referências» de um nó com modelo local (GGUF ou Hugging Face) só mostrava um aviso e gerava a imagem do zero, ignorando a referência. Agora o GGUF usa `init_image` (imagem → imagem) ou, nos modelos de edição (Qwen-Image-Edit, FLUX Kontext), `ref_images`; o modelo Hugging Face local faz imagem → imagem reaproveitando os pesos já carregados. A proporção da imagem ligada é mantida (não estica).
- Se a biblioteca instalada não aceita imagem de entrada, o erro diz isso e como resolver (`asta libs`) em vez de gerar uma imagem sem a referência.
- **Modo Editar com um modelo que não edita** (sem entrada de imagem) agora dá um erro claro no nó, em vez de gerar do zero com um aviso fácil de perder. No modo Gerar, a referência continua só virando aviso.
- Versão 0.17.10 (o núcleo Rust não mudou).

## [0.17.9] — 2026-11-08

### Corrigido — o motivo do «NULL pointer access» não aparecia, e a geração não tentava de novo com menos memória
- A stable-diffusion-cpp-python troca o callback de log ao criar o modelo, o que apagava o nosso: a mensagem vinha sem «Motivo informado pela biblioteca». Agora o callback é reinstalado antes de cada geração.
- Sem avisos ou erros no log, a mensagem mostra as últimas linhas dele (até onde a biblioteca chegou).
- Se a geração falha com ponteiro nulo em tamanho grande (causa mais comum: memória), o ASTA tenta uma vez de novo com resolução menor antes de mostrar o erro.
- Versão 0.17.9 (o núcleo Rust não mudou).

## [0.17.8] — 2026-11-08

### Corrigido — «NULL pointer access» no Qwen-Image GGUF mesmo com os arquivos de apoio na pasta
- **O que o erro realmente era:** lendo o código da stable-diffusion-cpp-python (0.4.x), o modelo **carrega** (`Stable Diffusion model not loaded` seria outro erro); o «NULL pointer access» vem de **`generate_image` devolver um ponteiro nulo** — a geração falhou dentro da stable-diffusion.cpp e o motivo fica só no log dela. Por isso a mensagem antiga («não carregou… precisa do VAE») apontava para o lugar errado quando os arquivos de apoio já estavam lá.
- **Agora o motivo aparece:** o ASTA guarda as últimas mensagens de aviso/erro da biblioteca (callback de log) e as mostra no nó — «Motivo informado pela biblioteca: … failed to allocate buffer of size …». Se for falta de memória, o erro diz isso e sugere quantização/resolução menores.
- **Padrões como na documentação da stable-diffusion.cpp para Qwen-Image e FLUX:** `offload_params_to_cpu` e `diffusion_flash_attn` ligados no carregamento (reduzem muito o pico de memória), além do `cfg_scale` 2,5 do Qwen-Image.
- **Resolução em múltiplos de 16** (antes 8): Qwen-Image/FLUX/Z-Image podem falhar com alturas/larguras que não são (`1536×1024` virava `1024×680`, agora `1024×672`).
- Mensagem: «A geração com … falhou» (antes «O modelo … não carregou»), com o botão de baixar apoios só quando eles realmente faltam.
- Testes: `tests/test_v017_models.py` (motivo do log, múltiplos de 16, opções da família).
- Versão do app Android e das telas atualizada para 0.17.8 (o núcleo Rust não mudou).

### Observações (limites honestos)
- **Não consegui reproduzir a falha com o modelo real** (sem a biblioteca compilada nem o Qwen-Image neste ambiente): a causa exata na sua máquina ainda é desconhecida — o mais provável é memória, mas pode ser outra coisa. **Esta versão faz o ASTA dizer o motivo**; se o erro continuar, a nova mensagem terá a linha da biblioteca e dá para corrigir o ponto certo.
- O Qwen-Image Q4_K_M (≈ 12 GB) + o codificador Qwen2.5-VL (≈ 4,7 GB) pedem bastante RAM; `offload_params_to_cpu` ajuda a GPU, não a RAM.
- O callback de log substitui o da biblioteca: as mensagens continuam indo para o terminal (nível aviso/erro e info), mas sem o formato original dela.
- Rodaram `test_v017_models`, `test_canvas` e `test_preinstalled`; a suíte completa **não foi rodada de novo**.

## [0.17.7] — 2026-11-08

### Corrigido — GGUF de difusão sem arquivos de apoio (Qwen-Image, FLUX): agora dá para baixá-los do próprio nó
- O erro «O modelo qwen-image-….gguf não carregou na stable-diffusion.cpp («NULL pointer access»)» só **mandava a pessoa baixar à mão** o VAE e o codificador de texto. Agora o nó mostra o erro **sem o marcador interno**, diz **o que falta e o tamanho aproximado** e traz o botão **«Baixar os arquivos de apoio»**, que baixa **só o que falta** direto para a pasta do modelo (`models/image`), com o progresso no botão; ao terminar, é só executar o nó de novo (o carregamento automático da 0.17.6 acha os arquivos).
- **Qwen-Image:** VAE `qwen_image_vae.safetensors` (Comfy-Org/Qwen-Image_ComfyUI, ≈ 0,25 GB) e codificador de texto `Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf` (unsloth/Qwen2.5-VL-7B-Instruct-GGUF, ≈ 4,7 GB). **FLUX:** `ae.safetensors`, `clip_l.safetensors` e `t5xxl_fp8_e4m3fn.safetensors` (≈ 5,5 GB no total).
- **Só a pedido:** o ASTA continua sem baixar gigabytes sozinho no meio de uma geração; o download começa quando a pessoa aperta o botão. Usa o token do Hugging Face de Configuração, retoma downloads parciais e recusa um segundo ao mesmo tempo.
- Famílias e downloads vivem em `asta/canvas/support.py` (`FAMILIES`, `missing`, `download_missing`); rota `POST /api/media/support/download`.
- Testes: `SupportFilesTests` em `tests/test_v017_models.py` (download simulado) e o teste de navegador `canvas_support_ui.js`.
- Versão do app Android e das telas atualizada para 0.17.7 (o núcleo Rust não mudou).

### Observações (limites honestos)
- **Não baixei nem rodei** os arquivos reais (sem rede para a Hugging Face nem a biblioteca neste ambiente): o download foi testado com um servidor simulado e o carregamento com um módulo falso. Os nomes dos arquivos nos repositórios podem mudar; se um download falhar, o erro aparece no nó e dá para pôr os arquivos à mão na pasta `models/image`.
- O codificador de texto do Qwen-Image é grande (≈ 4,7 GB): precisa de espaço em disco e de tempo; o resultado final ainda depende da versão da stable-diffusion-cpp-python instalada.
- Só **Qwen-Image** e **FLUX** têm download de apoio; outros modelos de difusão que precisem de arquivos extras seguem pelo `extra` no `canvas.json`.
- Rodaram `test_v017_models`, `test_canvas`, os testes de navegador do Canvas e o JS de i18n; a suíte completa **não foi rodada de novo**.

## [0.17.6] — 2026-11-08

### Corrigido — «NULL pointer access» ao gerar imagem com GGUF de difusão (Qwen-Image, FLUX…)
- **Causa:** um GGUF que traz só a difusão (Qwen-Image, FLUX…) era carregado como arquivo único (`model_path`); a stable-diffusion.cpp não consegue montar o modelo sem o VAE e o codificador de texto, o contexto fica nulo e a geração termina em «NULL pointer access».
- **Carregamento automático para famílias conhecidas** (`GGUFMedia.FAMILIES`): para **Qwen-Image** (VAE + codificador Qwen2.5-VL, `cfg_scale` 2,5) e **FLUX** (ae + clip_l + t5xxl), o ASTA procura os arquivos de apoio **na mesma pasta do modelo** (`models/image`) e carrega com `diffusion_model_path`, `vae_path` e `llm_path`/`clip_l_path`/`t5xxl_path`. Só vale se **todos** os apoios existem; um `extra.load` salvo no nó ou um pré-instalado continuam mandando.
- **Erro claro:** se a biblioteca ainda falhar com «NULL pointer», o nó mostra o que aconteceu e, para as famílias conhecidas, **quais arquivos baixar e onde pôr** (em vez de «NULL pointer access» solto).
- **Apoios fora da lista de modelos:** codificadores de texto (Qwen2.5-VL, Qwen3, t5xxl, clip, mmproj) e os arquivos de apoio dos pré-instalados não aparecem mais como «modelos instalados» no seletor do nó.
- Testes: `QwenImageGGUFTests` em `tests/test_v017_models.py`.
- Versão do app Android e das telas atualizada para 0.17.6 (o núcleo Rust não mudou).

### Observações (limites honestos)
- **Não rodei um modelo Qwen-Image/FLUX de verdade** (sem a biblioteca nem os arquivos neste ambiente): o carregamento automático foi testado com um módulo falso e segue a documentação da stable-diffusion.cpp. Os nomes dos parâmetros (`llm_path`, `clip_l_path`, `t5xxl_path`) e o `cfg_scale` podem precisar de ajuste conforme a versão instalada da biblioteca, e o modelo pode pedir outros parâmetros (por exemplo `flow_shift`).
- Os arquivos de apoio precisam estar **na mesma pasta do modelo** e ter nomes reconhecíveis (`*vae*.safetensors`, `Qwen2.5-VL*.gguf`, `clip_l*.safetensors`, `t5xxl*`); o ASTA não baixa esses arquivos por você (só os dos pré-instalados).
- Sem o campo de parâmetros extras na tela (removido na 0.17.1), um modelo que não é de uma família conhecida e precisa de outro carregamento só se ajusta pelo `extra` no `canvas.json`.
- Rodaram `test_v017_models`, `test_canvas` e `test_preinstalled`; a suíte completa **não foi rodada de novo**.

## [0.17.5] — 2026-11-08

### Alterado — nós de mídia sem «Provedor»: só o Modelo
- O seletor **«Provedor» saiu dos nós Imagem, Vídeo, Som, Voz e Transcrever.** A lista de **Modelo** agora é única e junta: **Instalados neste computador** (GGUF e Hugging Face local), os modelos de **cada provedor de nuvem pronto para uso** — com chave (OpenAI/ChatGPT, OpenRouter, xAI/Grok, Google, ElevenLabs…) ou servidor local/compatível com endereço —, um grupo por provedor (as sugestões sempre; a lista completa do provedor do nó, e a de todos ao clicar em ↻), e a Demo / a Voz da Configuração onde existirem. **Escolher um modelo define também o provedor que o executa**; *Padrão* volta ao que está em Configuração → Mídia; *Configurar provedores e chaves…* abre essa tela; *Outro modelo…* ainda deixa digitar um nome.
- **Nós antigos continuam valendo:** o provedor já salvo num nó segue sendo usado (o modelo aparece como «atual» na lista) e o aviso «Sem chave de API» continua aparecendo quando falta a chave do provedor do nó.
- Testes: `canvas_model_picker_ui.js` e `canvas_simple_nodes_ui.js` atualizados (sem seletor de provedor; grupo do provedor com chave; escolher modelo da nuvem define o provedor).

### Corrigido
- **«Erro inesperado: 'StableDiffusion' object has no attribute 'txt2img'»** ao gerar imagem com um modelo GGUF local: a stable-diffusion-cpp-python nova chama o gerador de `generate_image` (a antiga, `txt2img`). O ASTA agora usa o que existir e, se não houver nenhum dos dois, explica como atualizar a biblioteca (`asta libs`) em vez de um erro inesperado.
- **GGUF de imagem perdia a proporção:** cada lado era limitado a 1024 sozinho, então `1280×720` virava `1024×720`. Agora o lado maior vai até 1024 mantendo a proporção (`1280×720` → `1024×576`).
- Testes: `GGUFApiCompatTests` em `tests/test_v017_models.py`.

### Observações (limites honestos)
- O gerador novo da stable-diffusion-cpp-python foi coberto com um **módulo falso**; **não rodei um modelo GGUF de verdade** (sem a biblioteca nem o modelo neste ambiente), então o nome dos parâmetros extras do gerador novo pode precisar de ajuste conforme a versão instalada.
- Listar «todos os modelos» de um provedor pede chave e rede e pode trazer muitos modelos (OpenRouter); sem isso aparecem só as sugestões.
- Quem precisava escolher um provedor **sem escolher modelo** usa agora a opção do provedor na lista (Demo, Voz da Configuração) ou *Padrão*; provedores de nuvem sem modelo sugerido só aparecem depois de ↻ ou de «Outro modelo…».
- Rodaram `test_v017_models`, `test_canvas`, os testes de navegador do Canvas e o JS de i18n; a suíte completa **não foi rodada de novo**.

### Alterado
- README (pt-BR e inglês): a tabela de modos agora lista as **oito ferramentas** (inclui **Computer Use** e **Code**), as linhas do Studio e do Canvas citam as novidades da 0.17 (Tools, camadas livres, 4K/120 fps, `@`, barra de modelos, seletor de modelo, Enviar ao Studio), e a tabela de seções e o mapa do repositório foram atualizados.

## [0.17.4] — 2026-11-08

### Adicionado — menções com «@» também em nós de Texto e para vídeos e sons
- **O `@` funciona nos nós Texto e Texto IA** (`canvas_nodes.js`): digitar `@` abre a mesma lista e as mesmas fichas dos prompts de Imagem e Vídeo. Como o texto de um nó **Texto ligado** a um nó de Imagem ou Vídeo entra no prompt dele, uma menção escrita ali **vale como se tivesse sido digitada no próprio nó**; mudar a menção deixa o nó de Imagem/Vídeo desatualizado (o hash agora olha o texto ligado, não só o prompt do nó). O nó **Texto IA** é instruído a manter os `@nomes` exatamente como estão na saída.
- **Vídeos e sons podem ser citados** (`asta/canvas/mentions.py`): a lista e as fichas mostram a miniatura do vídeo (primeiro quadro) e um ícone de som; o apelido segue a mesma regra (`Cena Praia.mp4` → `@cena-praia`, `chuva.mp3` → `@chuva`, nomes repetidos com `-2`…, o mesmo espaço de apelidos para os três tipos). Na geração:
  - **imagem** → referência numerada (como antes);
  - **vídeo** → entra como referência pelo **quadro do meio** e o prompt vira `cena-praia (reference image N, a frame of the video)`; num nó de **Vídeo**, a primeira imagem ou quadro citado vira a **imagem inicial**;
  - **som** → não é imagem: fica no prompt como `chuva (audio reference)` e o nó **avisa** que modelos de imagem/vídeo não usam áudio como referência.
  Só imagens e quadros recebem número de referência. A rota `GET /api/canvases/{id}/mentions` agora devolve também o `kind` de cada item.
- Testes: `MediaMentionTests` e `EngineMediaMentionTests` em `tests/test_v017_mentions.py` e novas verificações em `tests/browser/canvas_mention_ui.js`.

### Alterado
- Versão do app Android e das telas atualizada para 0.17.4 (o núcleo Rust não mudou).

### Observações (limites honestos)
- Nenhum provedor/modelo atual do ASTA usa **áudio como referência** de imagem ou vídeo, nem um **vídeo inteiro** como referência: o som só aparece no texto (com aviso) e o vídeo entra por **um quadro** (o do meio).
- O `@` não está nos nós de **Som** e **Voz**, na caixa do Chat nem no Studio; num Texto ligado a eles a menção fica como texto.
- Num nó de Vídeo só **uma** imagem inicial é usada.
- Quanto uma referência guia o resultado **depende do modelo** (a Demo aceita referências mas só varia o resultado).
- Rodaram `test_v017_mentions`, `test_v017_canvas`, `test_canvas`, `test_canvas_nodes`, o JS de i18n e os testes de navegador do Canvas; a suíte completa **não foi rodada de novo**.

## [0.17.3] — 2026-11-08

### Adicionado — seletor de modelos nos nós do Canvas
- **O campo «Modelo» dos nós Imagem, Vídeo, Som, Voz e Transcrever virou um seletor** (`canvas_nodes.js`, `GET /api/media/installed`, `asta/canvas/installed.py`) com grupos: **Instalados neste computador** (GGUF de imagem e vídeo baixados em `models/image` e `models/video`, com quantização e tamanho, e os modelos do **Hugging Face local** que o ASTA baixou — reconhecidos pelo marcador de precisão —, com a precisão), **Sugeridos** (as sugestões do provedor) e **Disponíveis na nuvem** (a lista que o provedor escolhido oferece, via `/api/media/models`: OpenAI/ChatGPT, OpenRouter, xAI/Grok, Google, ElevenLabs, Replicate, Hugging Face Inference…). A lista da nuvem só é pedida quando o provedor tem chave (ou é um servidor local); o botão ↻ atualiza (as listas ficam em memória por 1 minuto).
- **Escolher um modelo instalado também troca o provedor do nó** para o que o executa (GGUF local ou Hugging Face local); escolher um modelo da nuvem ou sugerido só troca o modelo e mantém o provedor. *Padrão* limpa a escolha e *Outro modelo…* abre um campo para digitar qualquer nome (como era antes).
- Testes: `tests/test_v017_models.py` (rota com GGUF e cache falso do Hugging Face) e o teste de navegador `canvas_model_picker_ui.js`.

### Alterado
- As imagens citadas com `@` agora têm ordem estável (mais antiga primeiro, e no mesmo segundo vale a ordem de entrada no canvas): antes o desempate usava o id sorteado, então a ordem da lista e o `-2`/`-3` de nomes repetidos podiam variar.
- Versão do app Android e das telas atualizada para 0.17.3 (o núcleo Rust não mudou).

### Observações (limites honestos)
- Modelos do **Hugging Face local** só aparecem se foram baixados **pelo ASTA** (o cache de outros programas não é lido), e o ASTA não sabe para qual tipo cada um serve: os que não são os sugeridos/escolhidos para o tipo aparecem em todos os tipos compatíveis com o provedor.
- A lista da nuvem depende da API do provedor e da chave; sem chave, ou sem rede, só aparecem os sugeridos (e o modelo atual do nó continua selecionável). Ela mostra o que o provedor oferece, não só o que serve ao tipo: provedores como OpenRouter listam muitos modelos.
- Modelos de **texto** (a conversa e o nó «Texto IA») não ganharam o seletor: ele vale para os nós de mídia.
- A suíte completa **não foi rodada de novo**: rodaram `test_v017_models`, `test_v017_mentions`, `test_v017_canvas`, `test_canvas`, `test_canvas_nodes`, o JS de i18n e os testes de navegador do Canvas.

## [0.17.2] — 2026-11-08

### Adicionado — comando «@» para citar uma imagem específica nos prompts
- **Menções com `@` nos prompts dos nós Imagem e Vídeo do Canvas** (`asta/canvas/mentions.py`, `canvas_mention.js`): digitar `@` abre a lista das imagens do canvas (enviadas ou geradas, com miniatura), filtrada pelo que se digita; setas, `Enter`/`Tab` escolhem, `Esc` fecha, e o apelido é inserido no texto. Fichas embaixo do prompt mostram as imagens citadas (vermelho = apelido sem imagem).
- **Apelido de cada imagem:** o nome sem extensão, em minúsculas, sem acentos e com hífens (`Foto Perfil.png` → `@foto-perfil`); nomes repetidos ficam com `-2`, `-3`… (a mais antiga mantém o simples), então um apelido aponta sempre para uma imagem só (o id do arquivo também vale). `a@b.com` nunca é tomado por menção.
- **Na geração:** cada `@apelido` vira `apelido (reference image N)` no prompt e a imagem entra como **referência N**, na ordem da 1ª citação (até 6), **antes** das imagens ligadas em «Referências». No modo **Editar** a menção basta como imagem a editar. No **Vídeo**, a primeira imagem citada vira a **imagem inicial** (se nenhuma estiver ligada); as outras ficam só como texto, com aviso. `@` sem imagem fica como texto e gera um aviso no nó.
- **Cache:** as imagens citadas entram no hash do nó — citar outra imagem deixa o nó desatualizado.
- Rota `GET /api/canvases/{id}/mentions?q=` (apelido, nome e miniatura).
- Testes: `tests/test_v017_mentions.py` (apelidos, reescrita, referências de imagem e vídeo, hash, rota) e o teste de navegador `canvas_mention_ui.js`.

### Alterado
- Os textos de ajuda dos prompts de Imagem e Vídeo lembram do `@`. Versão do app Android e das telas atualizada para 0.17.2 (o núcleo Rust não mudou).

### Observações (limites honestos)
- As menções valem **nos prompts de Imagem e Vídeo do Canvas**; não há `@` na caixa do Chat, no Studio nem em outros nós (texto, som, voz).
- Só **imagens** do canvas podem ser citadas (não vídeos nem áudios).
- Quanto a imagem de referência realmente guia o resultado **depende do modelo**: provedores/modelos sem suporte a referências recebem só o texto (com aviso); a Demo aceita referências mas só varia o resultado, não edita de verdade.
- No Vídeo só **uma** imagem inicial é usada.
- Rodaram `test_v017_mentions`, `test_v017_canvas`, `test_canvas`, `test_canvas_nodes`, o JS de i18n e os testes de navegador do Canvas; a suíte completa **não foi rodada de novo**.

## [0.17.1] — 2026-11-08

### Alterado — nós de mídia do Canvas mais simples: Provedor, Modelo e Resolução
- O bloco **«Avançado»** dos nós **Imagem, Vídeo, Som, Voz e Transcrever** (prompt negativo, semente, parâmetros extras em JSON e «ignorar estilos globais») foi **substituído por Modelo + Resolução**: o nó mostra *Provedor*, *Modelo* e, em Imagem e Vídeo, *Resolução*. Em Imagem a antiga lista de tamanhos virou a **Resolução**, agora com a proporção (`1280×720 (16:9)`); em Vídeo há a nova **Resolução** (*Automática*, 480p, 720p ou 1080p, lado maior).
- **Resolução do vídeo** (`resolution`, `long_side` nos provedores): vale para o **Demo e os modelos locais** (Hugging Face local e GGUF), que usam o tamanho pedido; os provedores de nuvem escolhem os próprios tamanhos e a ignoram. Mudar a resolução deixa o nó desatualizado (muda o hash).
- **Nada se perde:** o que já estava salvo nos canvases (prompt negativo, semente, `extra`, `ignore_global_styles`) **continua valendo no motor**; só não aparece mais na tela. Os canvases antigos abrem sem mudança.
- «Gerar de novo» já sorteia outra semente, então a semente na tela deixou de ser necessária.
- README: as opções de carga dos GGUF (VAE etc.) agora se definem no `extra` do nó em `canvas.json` ou pela API; o texto foi atualizado.
- Versão do app Android e das telas atualizada para 0.17.1 (o núcleo Rust não mudou).
- Testes: `SimpleNodeTests` e `SimpleNodeApi` em `tests/test_v017_canvas.py` e o teste de navegador `canvas_simple_nodes_ui.js`.

### Observações (limites honestos)
- **Quem usava prompt negativo, semente fixa ou JSON extra pela tela perdeu esse acesso**: agora só dá pela edição do `canvas.json` ou pela API (não há mais campo para isso). Se fizer falta, dá para devolver como opção em Configuração → Mídia.
- A resolução do vídeo **não muda** o tamanho nos provedores de nuvem (OpenAI, Google, Replicate, Hugging Face Inference…).
- Rodaram `test_v017_canvas`, `test_canvas`, `test_canvas_nodes`, `test_all_providers`, o JS de i18n e os testes de navegador do Canvas; a suíte completa **não foi rodada de novo**.

## [0.17.0] — 2026-11-08

### Adicionado — Studio e Canvas para produção criativa de verdade
- **Studio · «Tools» na timeline** (`asta/web/js/views/studio_tools.js`): as janelas que já existiam — **Mídias, Monitor, Propriedades e Mixer de áudio** — viraram ferramentas que você **liga e desliga** (botão *Tools*; a escolha fica guardada no navegador), organizadas em painéis laterais com abas, e ganharam companhia: **Efeitos** (18 filtros, fades, zoom e *camadas de efeito*), **Efeitos sonoros** (20 efeitos gerados no ASTA, sem internet: whoosh, riser, impacto, glitch, rebobinar, moeda, chuva…), **Captura de tela** (gravação pelo navegador, com som da aba e microfone opcionais, que entra na timeline), **Legendas** (texto → legendas com tempo, importar/exportar SRT e WebVTT), **Transcrição** (áudio/vídeo → texto pelo provedor de transcrição → legendas alinhadas à fala; ou cole o texto e só alinhe) e **Navegador de mídia** (arquivos dos Canvas, de outros projetos e exportações, com busca e importação por cópia). Sem janelas no alto, a timeline ocupa o editor inteiro.
- **Studio · camadas livres, sem misturar** (`schema.add_track`, `TRACK_KINDS`): **vídeo, imagem, áudio, texto e efeitos**. Mídia solta vai para a primeira camada livre **do tipo certo** ou cria uma nova (nada de empilhar tipos diferentes na mesma trilha); botão direito na camada: renomear, subir, descer, apagar. A **camada de efeitos** aplica o filtro a tudo que está abaixo dela enquanto o clipe dura (na prévia e na exportação) e não alonga o vídeo.
- **Studio · exportação:** além de 480p/720p/1080p, agora **2K (2560 px) e 4K (3840 px)**; e **24, 30, 60 e 120 fps** (24 continua o padrão). A predefinição do x264 acompanha a carga (`veryfast` → `superfast` → `ultrafast`) para 2K/4K e 60/120 fps gastarem menos CPU. Padrão em Configuração → Studio (`export_fps`); o nome e o registro da exportação trazem resolução e fps.
- **Studio · `Shift`+`A`** seleciona a timeline inteira; **`,` e `.`** deslocam a seleção (1 quadro; com `Shift`, 1 s), há o campo *Deslocar todos (s)* no inspetor e `Del` apaga tudo (`Ctrl+Z` desfaz). Trilhas travadas ficam selecionadas, mas nunca se movem nem são apagadas (corrigido: antes um arrasto também movia clipes de trilhas travadas).
- **Studio · timeline maior e mais leve:** altura da timeline de `100vh − 250 px` para `100vh − 150 px` (mín. 720 px), trilhas mais altas, **forma de onda** nos clipes de áudio (picos calculados no Rust, em cache no servidor) e **virtualização**: só os clipes perto da área visível viram elementos (1500 clipes continuam fluidos).
- **Studio · edição automática melhor** (`asta/studio/analysis.py`, `autoedit.py`): o áudio é decodificado **uma vez** e analisado no núcleo Rust (volume, silêncios, momentos fortes, **BPM real, fase da primeira batida e o *drop* da música**); o vídeo vira miniaturas cinza (cortes de cena e **movimento por trecho**). Mudanças: **condensação** — com mais material do que o alvo, escolhe os melhores trechos **espalhados pelo vídeo inteiro**, na ordem em que aconteceram (antes pegava só o começo); cortes terminam em **pausas ou trocas de cena**; ação começa limpa numa troca de cena; estilos de batida usam o **BPM e a fase medidos** na música (e o *drop* define onde a introdução acaba); sobra de corte curtinha é absorvida; loops da música têm fades; o revisor também avisa de cortes de menos de meio segundo.
- **Canvas · Enviar ao Studio** (`asta/canvas/to_studio.py`, `POST /api/canvases/{id}/to-studio`): leva a montagem do **Editor** (camadas, tempos, volumes, textos) — ou as saídas finais do fluxo na ordem dos nós, ou só os nós selecionados — para a timeline de um **projeto novo** ou o **fim de um projeto existente**; os arquivos são copiados. Também no Studio, o **Navegador de mídia** importa arquivos dos Canvas.
- **Canvas · barra de pesquisa de modelos** (`canvas_hub.js`, `GET /api/media/hub/search`, `POST /api/media/hub/use`): pesquisa na **Hugging Face** por Imagem, Vídeo, Som, Voz, Transcrição ou Texto. Em **GGUF** lista **todas as quantizações** de cada modelo (bits, tamanho, qualidade, se cabe na RAM, a recomendada) e baixa a escolhida; no formato **original** oferece fp32/fp16/bf16 e as versões menores da comunidade. **Usar** define o padrão do tipo (Configuração → Mídia) e o modelo do nó selecionado.
- **Núcleo Rust · interface 4** (`asta/native/src/media.rs`): `asta_audio_levels`, `asta_silence_ranges`, `asta_pick_peaks`, `asta_onset_env`, `asta_tempo`, `asta_frame_activity`, `asta_scene_cuts`, `asta_waveform` e `asta_topo` (ordem de execução e níveis de um grafo). Cada uma tem o equivalente em Python (mesmas contas, mesma ordem) e os testes comparam os dois lados, inclusive com entradas aleatórias. Bibliotecas das interfaces 1–3 seguem aceitas (sem os recursos novos).
- Testes novos: `tests/test_v017_native.py`, `test_v017_studio.py`, `test_v017_canvas.py` e os de navegador `studio_tools_ui.js` e `canvas_hub_ui.js`.

### Alterado
- **Canvas · motor mais leve em fluxos grandes:** índices de nós/arquivos/conexões (antes cada consulta varria listas), leitura do arquivo só quando alguém grava (antes uma leitura completa por nó, mesmo em cache), resultado gravado também na memória, e ordem de execução calculada no Rust. Uma nova rodada de 40 nós em cache faz no máximo 3 leituras do arquivo.
- `tools.loud_moments`, `tools.silences` e `tools.scene_changes` (Studio) agora usam a análise nova: uma decodificação do áudio e miniaturas cinza, em vez de três filtros do ffmpeg que imprimiam texto. Mesma assinatura e mesmo formato de resultado; os momentos fortes saem a pelo menos `janela` segundos um do outro.
- `normalize_timeline` aceita as camadas `image` e `fx` e vários filtros novos (`sepia`, `negative`, `blur`, `sharpen`, `glow`, `grain`, `vignette`, `mirror`, `noir`, `teal_orange`); a duração da timeline ignora clipes de efeito.
- Versão do app Android, das telas, do núcleo (`Cargo.toml`) e dos instaladores atualizada para 0.17.0.

### Corrigido
- Arrastar com clipes de trilhas **travadas** selecionados os movia junto.
- A timeline desenhava todos os clipes de uma vez: com milhares de clipes a interface travava.
- Ao apagar uma mídia do projeto, a miniatura e as formas de onda em cache dela ficavam no disco.
- Os nomes dos instaladores no README (`ASTA-0-16-0-…`) não batiam com os que a Release gera (`ASTA-0-17-…`: o rótulo tira o `.0` final).

### Observações (limites honestos)
- **Captura de tela** e **gravação do microfone** dependem das permissões do navegador (em `http://localhost` funcionam no Chrome, Edge e Firefox); **não foram testadas num navegador real com tela compartilhada** neste ambiente (só o painel e o envio do arquivo).
- A **transcrição** usa o provedor de transcrição de Configuração → Mídia (o Demo não transcreve): os horários das legendas são calculados pela fala medida no áudio, não vêm do provedor, então são uma boa aproximação, não alinhamento por palavra.
- A busca de modelos fala com a **Hugging Face de verdade**; nos testes ela foi **simulada** (sem rede). Modelos de som e voz só rodam no formato original (provedor «Hugging Face local»); GGUF de imagem e vídeo rodam pela stable-diffusion.cpp e o de texto pela conversa.
- Exportar em **4K/120 fps** pede um computador forte e gera arquivos grandes; foi testado em 2K/60 e 4K/30 de 1 s em Linux.
- A análise de BPM escolhe a oitava mais próxima de ~120 BPM (faixas a 174 BPM saem como 87: a mesma grade, só nas batidas pares).
- Os instaladores (Windows, macOS, Android) são gerados pelo CI e **não foram executados em aparelhos reais**; o núcleo Rust 4 foi compilado e testado em Linux (`cargo test` + paridade com Python).
- A suíte completa **não foi rodada de novo**: rodaram `test_v017_*`, `test_studio`, `test_v014_studio`, `test_canvas`, `test_canvas_nodes`, `test_i18n`, o JS de i18n e os testes de navegador do Studio e do Canvas.

## [0.16.0] — 2026-11-08

### Adicionado — a seção **Code** (vibe coding de bases de código longas com equipes de agentes)
- **Nova seção «Code»** na barra lateral (ícone `</>`; atalho conforme a ordem das telas; também na paleta Ctrl+K e como tela inicial opcional) e **nova aba «Code»** em Configuração → Seções. Tem selo na barra lateral com as sessões que esperam você (laranja) ou trabalham em segundo plano (azul).
- **Sessões em pastas e subpastas** (`asta/code/manager.py`): pastas principais e subpastas (até 3 níveis) que se **renomeiam**, têm **uma de 8 cores vivas** e se **recolhem/expandem** (o estado fica salvo no servidor e sobrevive ao recarregar); sessões se movem pelo menu ou **arrastando**; apagar uma pasta sobe as sessões e subpastas dela (nada se perde).
- **Várias sessões em segundo plano** (até 8 ao mesmo tempo, configurável; as outras esperam na fila), cada uma com a **bolinha de estado**: **cinza** = parada · **cinza piscando** = trabalhando · **azul-claro** = terminou (volta ao cinza quando você abre a sessão) · **laranja** = esperando o seu Sim/Não *(a cor laranja é um acréscimo: o pedido só previa as três primeiras, mas sem ela uma sessão esperando resposta pareceria «trabalhando»)*. Execuções interrompidas por fechar o ASTA são marcadas como interrompidas (e dá para desfazer o que já foi feito).
- **Equipe de agentes multi-step, até 8 em paralelo por sessão** (`asta/code/engine.py`): **Planejador** (plano com tarefas, papéis, arquivos prováveis e dependências; crítica do plano nos níveis altos) → **trabalhadores** (arquiteto, pesquisador, programador, depurador, interface a partir de imagem, testador, documentação, autor de system prompts, revisor, publicador) que rodam **ao mesmo tempo** quando as tarefas não dependem uma da outra nem mexem nos mesmos arquivos → **Testes** (o próprio ASTA roda os testes/build/lint do projeto) → **Revisor** (confere o diff com as provas; se houver problema, um agente corrige e tudo é conferido de novo, até o limite do esforço) → **Publicação** (só depois de testes e revisão limpos) → **Relator**. O resumo final **sempre leva as provas que o motor coletou** (testes que falharam, pendências da revisão, ações negadas, o que não foi publicado), então o texto da IA nunca contradiz as provas.
- **8 níveis de esforço — Low, Medium, High, Extra, Mega, Max, Ultra, Omni** (`asta/code/efforts.py`), iguais para modelos de **nuvem (frontier)** e **locais**: mudam ações por agente, tamanho do plano, rodadas de correção, contexto, testes, revisão, crítica do plano e autoconferência; onde o provedor/modelo tem «tempo de pensamento» (`providers/thinking.py`), o nível correspondente é pedido ao modelo.
- **Modos Full Access e Ask**: no Ask aparece **Sim/Não** com a ação exata (várias perguntas ao mesmo tempo, uma por agente; «Sim, e não perguntar esse tipo de novo nesta sessão»); o Full Access não pergunta nada. O que pergunta é configurável por classe de risco (`write`, `delete`, `run`, `install`, `git`, `publish`; ler nunca pergunta). Dá para trocar o modo com a sessão em andamento.
- **Ferramentas** (catálogo fechado de 37, `asta/code/tools.py`): arquivos (ler trechos, buscar por regex, editar por texto exato, escrever, mover, copiar, apagar), **terminal** (programa + lista de argumentos; `python`, `node`, `npm`, `cargo`, `go`, `mvn`, `gradle`, `dotnet`, `gcc`, `make`, `cmake`, `pytest`, `ruff`, `tsc`…), os comandos de **teste/build/lint/formatação** de cada ecossistema, **instalação** (pip, npm, yarn, pnpm, cargo, go, composer, gem, dotnet), **git**, **GitHub**, **Hugging Face** (buscar, ver repositório, baixar arquivo), **busca na web** e leitura de páginas, **VS Code** e **Cursor**, ver imagens, usar anexos e **`write_system_prompts`** (até 8 system prompts longos em `.md`, validados em tamanho e estrutura, com modelo determinístico quando a IA não entrega).
- **GitHub** (`asta/code/github.py`): ler, **editar e publicar** repositórios. **Modo nuvem** (ZIP + API do GitHub, **sem precisar do `git`** — é o que o celular usa): o agente edita uma cópia e o ASTA compara com a árvore do GitHub e publica **só o que mudou** (blobs → árvore → commit → branch) e abre o **pull request em rascunho**; **modo git** (clone, commit, push) com o token entregue por variável de ambiente, nunca na linha de comando nem no remote. Também lê/comenta issues, publica **releases**, cria repositórios e dispara/lê **GitHub Actions** (a forma de rodar testes onde o aparelho não roda comandos). Branch nova `asta/…` por padrão; **direto na principal só quando a sessão pede**.
- **Linguagens** (`asta/code/langs.py`): Python, HTML, CSS, JavaScript, TypeScript, Java, Kotlin, Rust, C, C++, C#, Go, PHP, Ruby, Swift, Dart, Lua, shell, SQL, R, Scala, GDScript e Markdown, com as bibliotecas e frameworks mais usados de cada uma; detecção do projeto e dos comandos de teste/build/lint (pytest/unittest, npm/yarn/pnpm, cargo, go, mvn/gradle, dotnet, cmake/make, composer, bundle, dart, swift). Guias por linguagem em `prompts/langs/*.md`.
- **Prompts multimodais e unificados:** anexe imagens, PDFs, áudio (transcrito), vídeo, documentos e pacotes (ZIP/RAR/7z/TAR) a qualquer pedido; o texto e as imagens chegam ao Planejador e aos agentes, e `use_attachment` copia os arquivos anexos para o projeto.
- **Ao terminar um pedido:** atualizar README/changelogs/notas de versão (seguindo as regras do projeto) e **commit local / branch / pull request / direto na principal**.
- **Celular (app Android):** o app edita e publica repositórios do GitHub em **modo nuvem** no próprio aparelho; **«Executar no meu computador»** abre o ASTA do computador conectado direto na seção Code (`?goto=code`).
- **Pelo computador:** botões **VS Code** e **Cursor** abrem o projeto; lista de arquivos, diff e **Desfazer** (diário de mudanças com backup de cada arquivo, incluindo pastas criadas).
- **Sem IA (Demo):** fallback por regras — visão geral, ler arquivo, buscar texto, rodar testes/build/lint, ver mudanças do git; qualquer outra coisa explica o que falta.
- **Prompts internos abertos** em `asta/code/prompts/` (regras comuns, segurança, um por agente, um por papel, um por grupo de linguagens, escritor de prompts) — legíveis em Configuração → Code; entram no pacote.
- **Segurança (`asta/code/guard.py`)**, valendo em qualquer modo: tudo dentro da pasta do projeto (links seguidos); sem segredos (`.env`, chaves, certificados, perfis de navegador) nem a pasta de dados do ASTA; `.git/` só pela ferramenta `git`; programas só de uma lista de ferramentas de desenvolvimento, **sem shell**, `sudo`, `curl`/`ssh`, apagadores de disco nem `npm publish`/`cargo publish`; ambiente do comando **sem chaves/tokens**; `git` sem `-c`, `--force`, `reset --hard`, `clean`; token do GitHub nunca vai ao navegador, às exportações nem às saídas (redação). Exportar/importar configurações nunca leva nem aceita o token, o modo Full Access nem a publicação direta na principal; «restaurar padrões» não apaga o token.
- Novos: `asta/code/` (`engine`, `manager`, `tools`, `workspace`, `guard`, `github`, `langs`, `efforts`, `agents`, `rulebased`, `promptgen`, `promptlib`, `prompts/`), `asta/routes_code.py` (`/api/code/…`), `asta/web/js/views/code.js`, `code_ui.js`, `css/code.css`; testes `tests/test_code.py`, `test_code_team.py`, `test_code_api.py` e `tests/browser/code_ui.js`.

### Alterado
- O guia de desenvolvimento ganhou o item «Code» no mapa e uma armadilha própria: o Code é a **exceção deliberada** à regra «a IA nunca vira código executado» do Computer Use (rodar testes/código do projeto é o propósito da seção), com as barreiras acima.
- Atalhos numéricos: com o Code na barra lateral, **Alt+0 continua abrindo a Configuração** (a última tela), **Alt+8 abre o Code** e **Alt+9 o Rebuild**; a Biblioteca deixou de ter número (use Ctrl+K).
- Versão do app Android e das telas atualizada para 0.16.0.

### Observações (limites honestos)
- **Rodar código escrito pela IA dá a ele as permissões do seu usuário**; só com Python não há isolamento completo. Por isso o Ask mostra o comando inteiro e o Full Access é confiança total.
- Os fluxos do GitHub foram testados contra um **servidor GitHub de mentira** (API, ZIP, blobs, árvores, commits, PRs, issues, releases, workflows) — **não contra o github.com** (sem token/rede no ambiente de desenvolvimento). `git` foi testado de verdade (repositório local + remoto bare). Os fluxos de **VS Code/Cursor**, **Hugging Face** (servidor falso), **app Android** (o motor, não um aparelho físico) e os **modelos de nuvem** (modelo roteirizado) não foram exercitados com serviços/aparelhos reais.
- O modo nuvem compara com a árvore recursiva do GitHub: repositórios enormes (árvore truncada) e ZIPs acima de 500 MB pedem o computador com git.
- Serviços dev (servidores que não terminam) são encerrados no limite de tempo do comando; comandos interativos não são suportados (entrada fechada).
- A suíte completa não foi rodada de novo; rodaram `tests.test_code*`, `tests.test_i18n`, o teste de navegador do Code e os de navegador existentes.

## [0.15.12] — 2026-11-08

### Corrigido — app Android: o Chat não falava com o LM Studio do computador
- A checagem do LM Studio no Chat esperava só **1 segundo**, curto demais para outro computador pelo Wi-Fi (primeira conexão, economia de energia do Wi-Fi do celular). Para endereços da rede (`192.168…`, VPN, `.local`) agora espera **5 s** e **tenta de novo uma vez**; no próprio aparelho continua 1 s. Uma falha só fica em cache por 2 s (antes 8 s), então ligar o servidor e tentar de novo funciona logo.
- A mensagem de erro do Chat dizia sempre «abra o LM Studio e ligue Start Server», mesmo quando o servidor já estava rodando em **outro** computador. Agora diz a causa: **«Serve on Local Network» desligado** (conexão recusada), **firewall/Wi-Fi isolado** (tempo esgotado) ou **IP/Wi-Fi errado**; no app Android, `127.0.0.1` é explicado como «o próprio celular» e aponta para «LM Studio no computador».
- O aviso de «perdi a conexão» também deixou de mandar «ligar o servidor» quando o LM Studio é de outro computador.

## [0.15.11] — 2026-11-08

### Adicionado — LM Studio fora de casa SEM VPN no celular
- Em **Configuração → Celular e tablet → «LM Studio fora de casa (sem VPN)»** (no computador): um clique em **Baixar o cloudflared** (binário oficial da Cloudflare, para a pasta do ASTA) e outro em **Ligar o acesso de fora de casa** criam um **endereço https temporário** (túnel «quick» da Cloudflare — sem conta, sem abrir porta no roteador, sem instalar nada no celular). O ASTA mostra um **link** `https://….trycloudflare.com/lm/<código>`.
- No celular (app), em **Configuração → Provedores → LM Studio → «LM Studio no computador»**, cole o link e toque em **Conectar**: o provedor passa a usar o LM Studio do computador de qualquer lugar (4G/5G, outro Wi-Fi), com streaming.
- **Segurança:** desligado por padrão; pelo túnel só passa a API do LM Studio (`v1/…` e `api/v0/…`), nunca o resto do ASTA, e só com o **código secreto** do link (24 bytes aleatórios, comparação em tempo constante; **Gerar novo código** invalida o link antigo). O proxy só repassa ao LM Studio do próprio computador/rede de casa (nunca à internet). O endereço muda a cada vez que o acesso é ligado; o túnel é encerrado quando o ASTA fecha. Quem tem o link usa o seu LM Studio: não o compartilhe.
- Novos: `asta/remote.py`, rotas `GET/POST /api/remote` (só no computador) e `/lm/<código>/…`.
- O Tailscale (v0.15.10) continua funcionando; agora é só uma alternativa.

### Corrigido
- O túnel confundia o servidor da Cloudflare (`api.trycloudflare.com`, que aparece em mensagens de erro) com o endereço do túnel; agora a falha aparece como erro com o motivo.

### Observações
- Não consegui criar um túnel de verdade no ambiente de testes (sem acesso à Cloudflare): o proxy, o código e o gerenciador do túnel foram testados com um LM Studio falso e um `cloudflared` falso; o download do binário oficial foi verificado.

## [0.15.10] — 2026-11-08

### Revisado — usar o app fora de casa
- **Sem VPN não dá:** o endereço do computador em casa (`192.168…`) só existe dentro da rede de casa; de fora (4G/5G, outro Wi-Fi) o app não o alcança. Isso vale para o LM Studio do computador e para o ASTA do computador.
- **Com Tailscale (gratuito) funciona:** instale no computador e no celular, entre na mesma conta e use o IP do Tailscale (`100.x.x.x`) ou o nome `….ts.net` no lugar do `192.168…`.

### Adicionado/Corrigido
- Endereços de VPN (`100.64.0.0/10`, Tailscale) e nomes `.ts.net` são tratados como rede privada: não passam pelo proxy do sistema.
- O cartão **«LM Studio no computador»** aceita `https://…` (túnel/proxy reverso) sem forçar `http` e a porta 1234, e mostra a dica «Fora de casa».
- `asta mobile` / Configuração → Celular e tablet: se o Tailscale estiver instalado, o endereço Tailscale do computador entra na lista (e no pareamento) depois dos endereços da rede de casa.
- A busca de rede do LM Studio ignora a rede da VPN.

## [0.15.9] — 2026-11-08

### Corrigido
- **LM Studio do computador não conectava pelo celular sem dizer por quê:** agora a Configuração explica a causa — porta fechada («Serve on Local Network» desligado: sem isso o LM Studio só aceita o próprio computador), tempo esgotado (firewall do computador ou Wi-Fi de visitantes que isola aparelhos), endereço inexistente ou sem rota — e avisa quando o endereço ainda é `127.0.0.1` (que no celular é o próprio celular).
- Ao conectar pelo cartão **«LM Studio no computador»** e o servidor responder, o Chat/geração e os avatares passam a usar o LM Studio automaticamente (antes era preciso clicar em «Usar…»).
- A sonda do LM Studio devolve o tipo de falha (`kind`: `refused`, `timeout`, `dns`, `unreachable`).
- Lembrete: o cartão existe a partir do app v0.15.8; o APK v0.13.0 não o tem.

## [0.15.8] — 2026-11-08

### Adicionado
- **LM Studio do computador pelo celular/tablet:** em *Configuração → Provedores → LM Studio*, no celular/app aparece **«LM Studio no computador»**: **Procurar na rede** acha o servidor do LM Studio na mesma rede Wi-Fi (porta 1234, só a pedido) ou você digita o IP do computador; o ASTA aponta o provedor para ele e lista os modelos. No computador, ligue **Serve on Local Network** e **Start Server** (Developer) no LM Studio.
- Nova rota `POST /api/lmstudio/scan` e `lmstudio.scan()` (varre só a /24 do aparelho, só a porta do LM Studio, só leitura da lista de modelos).

## [0.15.7] — 2026-11-08

### Adicionado
- **Computer Use pelo celular (app Android):** na seção Computer Use do app aparece **«Executar no meu computador»**: ele abre direto o ASTA do computador já conectado, na seção Computer Use, e as tarefas rodam lá (o celular é só a janela: você acompanha o passo a passo e responde Sim/Não). Sem computador conectado, o app mostra a conexão (QR code ou endereço). Lá, **«Voltar ao ASTA deste aparelho»** retorna ao ASTA do celular.
- O Android não deixa um app controlar os outros, então o ASTA do próprio aparelho continua sem controlar o celular; o recurso serve para **mandar as tarefas ao computador**.

## [0.15.6] — 2026-11-08

### Corrigido
- **Release (instaladores e APK):** o job do AppImage falhava porque a release «latest» do python-build-standalone deixou de trazer o Python 3.12. O Python portátil agora vem de uma release **fixa** (3.12.7, 20241016, x86_64 e arm64), o que também deixa o build reproduzível. Com isso o Release volta a publicar o APK e os instaladores (Windows, macOS, Linux).

## [0.15.5] — 2026-11-08

### Alterado
- **App Android: conectar a um computador agora é opcional.** Com o motor embutido no aparelho, o app abre direto o ASTA local e **não mostra mais** a tela de «Escanear o QR code / digitar o endereço». Quem quiser usar o ASTA de um computador toca em «Conectar a um ASTA em outro computador (opcional)». Se o motor local não iniciar, essa opção aparece sozinha.

### Corrigido
- **Release nunca publicava (por isso o APK mais recente era o v0.13.0, com a tela obrigatória):** o job do AppImage não achava o Python portátil porque a lista de arquivos da release «latest» do python-build-standalone vem truncada; agora a busca pagina pela API de assets e falha com mensagem clara se não achar. *Não consegui reproduzir o job aqui: confirme na aba Actions se o Release foi publicado.*

## [0.15.4] — 2026-11-08

### Corrigido
- **Respostas em streaming cortadas no macOS (`Connection reset by peer`):** rotas de streaming (SSE) que não liam o corpo da requisição — como «regenerar» resposta de avatar, que envia `{}` — fechavam o socket com dados pendentes, e o macOS responde com RST, perdendo a resposta. O servidor agora consome o corpo não lido (até 1 MB) ao iniciar qualquer stream.
- **Windows:** o teste de traduções das dicas dos modelos pré-instalados importava o `en.js` por caminho `C:/…`, que o Node (ESM) recusa; agora usa URL `file://`. O teste de atualização ao abrir seguia o caminho do macOS/Linux (`execve`), mas no Windows o ASTA encerra e o instalador continua em outra janela (comportamento correto, agora testado como tal).
- **macOS/Windows sem ffmpeg completo:** os testes do Canvas que rodam o modelo «cena» (nós de vídeo e editor) agora são pulados quando o ffmpeg não está instalado, em vez de falhar.

## [0.15.3] — 2026-11-08

### Verificado
- Varredura de bugs em todo o projeto: suíte completa (711 testes, 8 pulados por falta de ferramentas opcionais), auditoria de rotas (fuzz) e checagem estática (argumentos mutáveis, `open()` sem codificação, processos com pipes) — **nenhum defeito novo encontrado no Linux**.

### Observações
- Seguem abertas as falhas antigas dos testes em macOS/Windows (por exemplo um `TypeError` em `test_cli` no Windows); não foram reproduzidas no Linux, então não foram alteradas às cegas.
- A publicação do Release depende de todos os jobs (núcleo, AppImage, Windows, macOS, Android) passarem.

## [0.15.2] — 2026-11-08

### Corrigido
- **`/api/mobile` travava no macOS:** a busca dos IPs da rede local usava `getaddrinfo(gethostname())`, que pode demorar muito; agora roda com limite de 1 s e o resultado fica em cache por 30 s.
- **Rebuild:** o arquivo ZIP enviado ficava aberto (vazamento de handle, trava de arquivo no Windows); agora é fechado e reaberto a cada leitura.
- **Release:** os executores do macOS passaram de `macos-14` para `macos-latest` (os jobs eram cancelados).
- **Testes portáteis:** `AutoEditTests` do Studio é pulado sem ffmpeg; os testes que chamam `node` leem a saída em UTF-8 (falhavam no Windows).

### Observações
- Os testes de macOS/Windows ainda têm falhas antigas fora deste escopo; o Linux está verde.

## [0.15.1] — 2026-11-08

### Corrigido — Computer Use
- **Segurança de `run_program`:** um argumento com o caminho **colado à opção** (`-o/caminho`, `-I~/x`) e o argumento `..` escapavam do filtro de caminhos (dava para ler a pasta de dados do ASTA, onde ficam as chaves de API, por um programa como `grep -r … ..`). Agora toda opção com caminho embutido, `.`/`..` e qualquer nome que exista ao lado do programa passam pelo mesmo crivo dos arquivos.
- **Modelos pequenos erravam o formato:** a IA que manda os argumentos como **texto JSON**, usa nomes de ferramenta parecidos (`mkdir`, `write_file`, `open_application`, `hotkey`…; «delete» vira lixeira, sempre desfazível) ou nomes de argumento parecidos (`file_path`, `destination`, `app_name`…) agora é entendida em vez de gastar passos com erro.
- **Jogos:** a pasta Downloads deixou de ser varrida por padrão (instaladores e páginas soltas apareciam como «jogos»); pastas de jogos próprias continuam em *Configuração → Computer Use → Pastas de jogos*.
- **macOS:** o texto digitado e as teclas vão como argumento do AppleScript (UTF-8 correto para acentos), não por variável de ambiente.
- Limite de tarefas ao mesmo tempo **aumentado nas configurações** passa a liberar na hora quem estava na fila.
- Dicas de instalação que faltavam no relatório (macOS e Windows).

### Adicionado
- **Bibliotecas e ferramentas** em *Configuração → Computer Use*: o que está instalado e o que falta (com o comando para instalar), por sistema: libX11/libXtst (X11), `xdg-open`, `grim`/`ydotool` (Wayland), `cliclick` (macOS), PowerShell (Windows), Pillow, `ffmpeg` e `pypdf`. Só o Python padrão é obrigatório; Pillow ganhou o extra `pip install "asta[computer]"` (reduz a captura de telas grandes; sem ele o `ffmpeg` faz o trabalho).
- Testes novos: argumentos de programas, nomes tolerantes, relatório de dependências e falha do provedor.

### Verificado nesta versão (Linux, X virtual com o Xvfb)
- As **27 ferramentas** rodaram com o driver real: arquivos (inclusive `.docx`/`.xlsx`/`.pdf` válidos), `zip`, organizar, lixeira, `ffmpeg`/`pandoc`/`soffice` por `run_program`, abrir programa por entrada `.desktop`, jogos de pasta, URL, captura de tela (com redução em tela 2560×1440: escala de clique correta, com Pillow e com `ffmpeg`), clique, digitação com acentos/Unicode, atalhos e rolagem.
- **Equipe completa ponta a ponta** com um modelo «com visão» roteirizado: abrir o terminal, capturar a tela (a imagem chega ao modelo), clicar, digitar e conferir o arquivo escrito.
- Continua sem verificação em máquinas reais: Windows, macOS e Android.

## [0.15.0] — 2026-11-08

### Adicionado — Computer Use
- **Computer Use (opcional, desligado por padrão):** uma equipe de agentes de IA faz **tarefas no computador do usuário** — digitar e escrever, pesquisar, usar programas instalados (Krita, OBS Studio, Audacity, o gerenciador de arquivos…), organizar e criar arquivos de qualquer formato e pastas/subpastas, abrir e jogar jogos da Steam, do Lutris e de pastas. Liga-se em *Configuração → Computer Use* ou pelo botão **Computer Use** do Chat; disponível em todas as plataformas do ASTA.
- **No Chat:** botão **Computer Use** ao lado do Run (junto de *Criar* e *Web*), com menu **Ask** / **Full Access**. A tarefa vira um **cartão ao vivo** na conversa (progresso, pergunta Sim/Não, resumo final e atalho para a seção); o cartão fica no histórico e «Responder de novo» não se aplica a ele.
- **Dois modos.** **Ask** pergunta **Sim ou Não** antes de cada ação que muda algo — criar/alterar arquivos, mandar para a lixeira, abrir programa/jogo/site, digitar/clicar/teclas, ver a tela — com «Sim, e não perguntar mais deste tipo nesta tarefa»; **Full Access** executa tudo **sem perguntar** (e a ferramenta `ask_user` some). Ler, listar e pesquisar nunca perguntam; *Configuração → Computer Use → Quando perguntar* escolhe os tipos. O Full Access pede uma confirmação na primeira vez.
- **Seção lateral «Computer Use»** (após o Studio; Alt+0 abre a 10ª tela; dá para escondê-la da barra): lista de tarefas **em andamento** (com selo na barra lateral quando alguma espera a sua resposta) e **histórico** das anteriores com busca; cada tarefa mostra o **time de agentes**, o roteiro, o **passo a passo** (ação, ferramenta, risco, resultado, capturas de tela, aprovação), a revisão e o resumo, com **Cancelar**, **Refazer**, **Desfazer** e **Apagar**; tudo atualiza ao vivo (eventos SSE). No celular a lista e o detalhe se alternam. Primeiro uso: tela de apresentação com o botão de ligar.
- **Até 8 tarefas ao mesmo tempo** (fila para as demais; limite ajustável de 1 a 8), cada uma com uma **equipe multi-agente e multi-etapas**: **Planejador → Operador → Revisor → Relator**. O Operador devolve **uma ação por vez** (JSON validado, qualquer provedor), com o guia do **especialista** da tarefa e do **programa** citado. O Revisor confere com **evidências do próprio motor** (os arquivos existem agora?, ações negadas, o Operador desistiu?) e pode mandar o Operador corrigir (1 rodada por padrão). Equipe **Rápida** opcional (só o Operador, para modelos locais lentos). **Tela, teclado e mouse têm uma trava única** (uma tarefa por vez); arquivos, pesquisa e programas de linha de comando rodam em paralelo.
- **System prompts internos em Markdown** (`asta/computer/prompts/`, 21 arquivos, empacotados e legíveis em *Configuração → Computer Use*): regras comuns, segurança, planejador, operador, revisor, relator, modo Ask/Full, cinco especialistas (arquivos, programas com tela, jogos, pesquisa, escrita) e guias de Krita, OBS Studio, Audacity, navegador, editores/Office, Steam/Lutris, gerenciador de arquivos e genérico. Respeitam *Conteúdo* (livre/SFW) e os limites fixos (nada sexual com menores ou sobre pessoas reais).
- **Catálogo fechado de 25 ferramentas** (listar, ler — inclusive docx/xlsx/pptx/pdf/zip —, procurar, criar pasta/arquivo, copiar, mover, organizar pasta por tipo/extensão/data/nome, compactar, lixeira, pesquisar na web, abrir endereço/arquivo/programa/jogo, listar programas e jogos, rodar programa de linha de comando **sem shell**, captura de tela, digitar, teclas, clique, rolagem, esperar, perguntar). Cria `.docx`, `.xlsx` e `.pdf` sozinho (só biblioteca padrão), texto em qualquer formato aberto e binários por base64 ou por programas (ffmpeg, magick, pandoc, soffice…).
- **Limites fixos em qualquer modo, inclusive Full Access** (`computer/guard.py`): nada de ler/escrever senhas, chaves SSH/GPG/nuvem, perfis de navegador, `.env`, certificados nem a **pasta de dados do ASTA** (a IA não pode ligar o Full Access sozinha); nada de escrever em pastas do sistema, apagar a pasta pessoal/raízes do usuário/disco; **nenhum shell, interpretador, `sudo`, apagador/formatador de disco, baixador de rede ou script**; argumentos que parecem caminho passam pelo mesmo crivo; só endereços `http(s)`/`mailto`; links simbólicos são resolvidos. Texto da web, de arquivos e de telas é **dado não confiável**.
- **Nada é apagado de verdade e tudo se desfaz** (`computer/files.py`): «apagar» manda para `~/.asta/computer/trash`, sobrescrever guarda o original, nunca sobrescreve sem pedido; um diário por tarefa e **Desfazer** reverte na ordem inversa. O histórico passo a passo, as capturas e a lixeira são arquivos comuns em `~/.asta/computer` (apagar o histórico tem a opção de esvaziar a lixeira junto).
- **Drivers de SO só com a biblioteca padrão** (`computer/osdrv.py`): Linux (`.desktop`, `xdg-open`, `xdotool`/`ydotool`/`wtype`, `scrot`/`maim`/`gnome-screenshot`/`grim`), macOS (`open`, `osascript`, `screencapture`, `cliclick` opcional), Windows (Start Menu/`Get-StartApps`, `SendInput` por ctypes, captura por PowerShell) e Android (limitado). Steam (bibliotecas e `appmanifest`), Lutris (`--list-games`/`.yml`) e pastas de jogos configuráveis. *Configuração → Computer Use* mostra o que cada computador permite e **o que instalar** quando falta algo.
- **Fallback por regras sem IA** (`computer/rulebased.py`): com o Demo, entende pedidos simples em português e inglês (criar pasta/arquivo, organizar pasta, abrir programa/jogo/site, pesquisar, vários passos encadeados); o resto diz com clareza que precisa de um modelo de IA. Resposta inválida do modelo → método automático.
- API: `GET/POST /api/computer/tasks`, `…/tasks/<id>` (+ `cancel`, `answer`, `undo`, `retry`, `shots/<arquivo>`), `GET /api/computer/events` (SSE), `status`, `inventory`, `prompts`, `history/clear`. Configuração `computer` em `settings.json` (`enabled`, `mode`, `max_parallel`, `max_steps`, `team`, `revisions`, `ask_for`, `game_dirs`, `app_wait`).

### Corrigido
- **Release do APK/instaladores:** o build do app Android falhava (`Python 3.12 is not available for the ABI armeabi-v7a`) e derrubava a Release inteira. O app passa a ser gerado para `arm64-v8a` e `x86_64` (o Chaquopy com Python 3.12 não tem `armeabi-v7a`; aparelhos de 32 bits ficam sem o APK).

### Alterado
- **Linux/X11: tela, teclado e mouse funcionam sem instalar nada** (`computer/x11.py`: libX11 + XTEST por `ctypes`, captura em PNG com `zlib`, acentos e qualquer Unicode, atalhos, clique e rolagem; testado num X virtual com o Xvfb). Ferramentas externas (`xdotool`, `grim`, `ydotool`…) só entram em sessões Wayland puras. Em Wayland com XWayland, o X11 só alcança janelas X.
- Barra lateral com **10 telas**: `Alt+0` abre a 10ª (Configuração); a paleta de comandos mostra o atalho certo; *Configuração* ganhou a aba **Computer Use** (18 abas) e um cartão no *Chat*. Tela inicial e esconder-da-barra aceitam a nova seção.
- Importar configurações **nunca liga o Computer Use, troca o modo nem remove perguntas do Ask** (só limites numéricos); exportar leva a seção `computer`.

### Observações e limites
- **Os drivers do Windows, do macOS e do Android foram escritos sem acesso a máquinas reais desses sistemas**: apenas o Linux (com um sistema simulado e comandos reais de arquivos) foi exercitado pelos testes. Ver a tela, digitar e clicar dependem de ferramentas e permissões do sistema (xdotool/ydotool, captura, permissões de Acessibilidade e Gravação de tela no macOS) e **exigem um modelo com visão** para clicar com precisão. O app Android só faz arquivos e pesquisa no próprio aparelho (o Android não deixa um app controlar os outros); para controlar um computador, conecte-o ao ASTA dele. Os instaladores continuam gerados pelo CI e não foram executados em Windows, macOS ou aparelhos Android reais por quem fez esta mudança.
- Ver a tela envia a imagem ao modelo escolhido (na nuvem, sai do computador): por isso é uma classe própria no modo Ask. **Full Access é responsabilidade de quem o liga**: a lixeira e o Desfazer cobrem arquivos, mas não ações de programas (ex.: algo salvo por um programa aberto) nem jogos/sites. Um aparelho **pareado por QR code** tem o mesmo acesso ao ASTA que o dono, inclusive ao Computer Use.
- Programas de linha de comando (`run_program`) recebem uma lista de argumentos, sem shell; a lista de programas bloqueados reduz o risco, mas não elimina o de um programa legítimo usado de forma destrutiva — o modo Ask pergunta sempre antes.

## [0.14.2] — 2026-11-08

### Melhorado — links: imagens e vídeos analisados conforme o pedido
- **O ASTA entende o que você pede sobre o link.** Pediu *imagens/fotos/gráficos* → o modelo (com visão) recebe até 10 imagens da página em vez de 4. Pediu *vídeo/transcrição/resumo do áudio* → o vídeo é baixado, o ASTA tira quadros e **transcreve o áudio** (serviço de voz em *Configuração → Voz*) e entrega tudo ao modelo. Link direto para um vídeo é sempre analisado.
- Vídeos hospedados em arquivo (`.mp4`, `.webm`, `.mov`…) são baixados direto (até 60 MB, só endereços públicos); YouTube, Vimeo e similares usam o `yt-dlp` se estiver instalado; sem ele, o vídeo é descrito pelo título e o modelo avisa que dá para tentar. Quadros e transcrição precisam do `ffmpeg`.
- Palavras dentro do próprio endereço não contam como pedido.

## [0.14.1] — 2026-11-08

### Melhorado — Chat lê links, inclusive de páginas com imagens e vídeos
- **Links colados na mensagem são lidos sozinhos** (até 4 por mensagem, sem precisar ligar a busca na web): o ASTA abre a página, extrai o texto (com título e descrição) e entrega ao modelo, marcado como texto da web não confiável.
- **Imagens da página**: a imagem de destaque (`og:image`), capas de vídeo e as imagens do conteúdo (ícones e pixels de rastreio ficam de fora) são listadas com o texto alternativo e, se o modelo enxerga imagens, até 4 por página seguem junto da mensagem. Link direto para uma imagem vira imagem anexada.
- **Vídeos da página**: `<video>`, `<source>`, `og:video`, links `.mp4/.webm` e embeds do YouTube, Vimeo, TikTok e outros entram na lista com título; o modelo é avisado de que não assiste vídeos e usa título e texto ao redor.
- Segurança como na busca: só endereços públicos (inclusive a cada redirecionamento), tamanho e tempo limitados. A interface mostra quais links foram lidos, com a contagem de imagens e vídeos.

## [0.14.0] — 2026-11-08

### Adicionado — instaladores e app Android sem computador
- **Instaladores para todas as plataformas**, gerados pelo workflow `release` e publicados na Release: **`ASTA-0-14-Win.exe`** (Windows, instala só para o usuário, sem administrador, com Python embutido), **`ASTA-0-14-macOS.pkg`** (macOS, Apple Silicon e Intel), **`ASTA-0-14-Linux.appimage`** (x86_64; também `-arm64`) e **`ASTA-0-14-Android.apk`**. Junto vão o **núcleo em Rust pré-compilado** de cada plataforma (`asta-core-*`) e `SHA256SUMS.txt`. Os comandos `curl … | sh` e `irm … | iex` continuam valendo.
- **O app Android não depende mais do ASTA do computador.** O APK traz o **motor do ASTA (Python, via Chaquopy) rodando dentro do aparelho**: abre sozinho, com a mesma interface, os provedores de IA na nuvem, busca na web, mundos 3D, avatars, jogos 2D, Canvas e Studio. Conectar a um computador (QR code/endereço) continua como opção na tela inicial e em *Configuração → Celular e tablet*. O servidor do app roda em **modo estrito**: até o endereço local exige o cookie de pareamento do app, então outros apps do celular não entram. O núcleo Rust vai compilado para arm64, armeabi-v7a e x86_64. O app avisa de APK novo nas Releases.
- **ZIP, RAR, 7z e TAR (`.tar.gz`, `.tgz`…) como anexo em todas as seções** (Chat, Mundos, Avatars, Jogos 2D, Canvas e Studio, inclusive no envio direto de mídias do Canvas e da timeline): o pacote é aberto **com segurança** (caminhos `..`/absolutos/`C:` nunca saem da pasta, links ignorados, limites de arquivos e de tamanho **realmente escrito**, pacotes dentro de pacotes até 2 níveis, nomes acentuados de ZIPs do Windows corrigidos) e cada arquivo de dentro vira um anexo (no Chat, o pacote continua sendo um anexo só, com a lista e o conteúdo). RAR e 7z usam `unrar`, `unar`, `7z` ou o `tar` (bsdtar) do sistema; se faltar, a mensagem diz o que instalar.
- **Janelas de contexto de 256K, 512K e 1M tokens** (para modelos que suportam). Chat: atalhos 256K/512K/1M e limite de 2M; Hugging Face GGUF: 262144/524288/1048576 na lista. O núcleo Rust passa a usar **cache de atenção de 4 bits** quando nem o de 8 bits cabe em contexto longo, avisa quando o pedido passa do que o modelo foi **treinado** e a tela mostra, para cada modelo local, o contexto de treino e a **memória estimada do cache**. Claude: pede a janela de 1M (cabeçalho beta) quando o Chat passa de 200K e volta ao normal se o modelo não aceita.
- **Equipe de agentes no Chat** (*Configuração → Chat → Equipe de agentes*): *Planejar e escrever* (Planejador → Redator) ou *Planejar, escrever e revisar* (+ Revisor, e o Redator melhora o texto uma vez). Falha de um agente = a resposta segue sem ele.
- **Armazenamento** (*Configuração → Desempenho*): quanto cada parte ocupa, sobras (downloads de modelo parados, anexos esquecidos) e **arquivos idênticos**, que viram **um só no disco** por links físicos (conferidos byte a byte pelo núcleo Rust; só em modelos/mídias/pacotes; sempre com prévia e confirmação).
- **`docs/asta-principles.md`** (os princípios do projeto) e **`docs/asta-dev-guide.md`** (o guia que os desenvolvedores e os modelos de IA seguem).

### Alterado — respostas longas e de qualidade
- **Tamanho das respostas** do Chat até **128.000 tokens**, **Estilo das respostas** (*Equilibrado*, *Detalhado* — novo padrão — e *Longo e profundo*: o comprimento vem de conteúdo, nunca de enrolação) e **continuação automática**: se a resposta bate no limite de tokens, o ASTA pede ao modelo que siga de onde parou (até 3 vezes por padrão) em vez de entregar texto cortado.
- **Teto de saída aprendido por modelo.** Quando o provedor recusa um `max_tokens` grande demais (OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter…), o ASTA **lê o limite na própria mensagem de erro**, refaz o pedido com o valor certo e lembra dele (o aviso aparece no Chat).
- **Modelos locais:** a janela automática agora **cresce para caber a resposta pedida** (antes a resposta era encolhida para metade de uma janela de 2K em PCs fracos) e nunca encolhe de volta; os agentes JSON dobram o espaço até 16K quando a resposta vem cortada; a fala de um avatar cortada pelo limite termina na última frase completa.
- Histórico do Chat: até 1.000 turnos lembrados; anexos grandes cabem na janela configurada (limite por arquivo e total acompanham a janela).

### Alterado — núcleo em Rust obrigatório e mais eficiente (interface 3)
- **O núcleo Rust é parte obrigatória do ASTA**: os instaladores já o trazem; pelo terminal, `asta native setup` baixa a **biblioteca pré-compilada da Release** (conferida por SHA-256, sem compilador) e só compila na máquina se isso falhar; ao abrir, o ASTA a baixa sozinho em segundo plano se faltar (no máximo 1 vez por dia). O Python segue como orquestrador e **espelho** de cada função: sem a biblioteca o ASTA continua funcionando, só mais devagar. O CI agora compila e testa o Rust nas três plataformas.
- **Vários agentes de IA locais:** o modelo embutido atende por uma **fila com prioridade** (a conversa que você espera passa na frente de uma geração longa em segundo plano), um **pool de modelos residentes** decidido pela memória livre e um plano de execução do núcleo (`asta_plan_agents`).
- **RAM/VRAM:** ao descarregar modelos (de texto e de mídia), os pesos saem do cache de páginas e a memória que o alocador segurava **volta ao sistema** (`malloc_trim`/`posix_fadvise`).
- **Armazenamento:** varredura de pastas com várias threads e busca de duplicados no Rust (`asta_scan_dir`, `asta_dup_groups`).
- **Menos CPU:** nos modos Leve e Equilibrado o ffmpeg usa menos threads e roda com **prioridade baixa** (`nice`/classe «abaixo do normal»); o resultado é o mesmo.
- O diretório de compilação do Rust (`asta/native/target/`) tinha sido versionado por engano: foi removido do git e ignorado.

### Alterado — Studio
- **O monitor do clipe foi removido** da timeline. A mídia do bin se coloca com dois cliques, arrastando ou pelo menu do botão direito (*Inserir no cursor*, que empurra o que vem depois, *Colocar no cursor*, que não mexe nos outros clipes, e *Tirar do projeto*).
- **Todos os 11 provedores de texto** agora passam também na geração do Studio e na **edição automática** (bateria de conformidade ampliada).

### Corrigido
- **Studio — exportação com as camadas invertidas:** na timeline a V2 fica acima da V1 (como na prévia), mas o vídeo exportado empilhava ao contrário e a V2 ficava **escondida atrás da V1** (a edição automática em camadas e qualquer sobreposição manual saíam erradas). Corrigido, com teste que confere os pixels.
- **Studio — edição manual:** a lâmina perto da borda de um clipe cortava clipes de **outras trilhas**; mudar a **velocidade** não mudava a duração do clipe (2× agora usa o mesmo trecho em metade do tempo); mídia solta ia para a **A3** (agora áudio vai para a A1 e vídeo para a V1, subindo para a trilha seguinte se o trecho estiver ocupado); **Juntar** unia clipes com volume/posição/escala diferentes; trocar de aba logo após editar ou fechar a página podia **perder a última edição**; salvar com falha ficava eternamente em «Salvando…» (agora tenta de novo e avisa); arrastar clipes refazia o mixer inteiro a cada movimento do mouse (agora só o necessário, no máximo uma vez por quadro).
- **macOS (instalação/atualização no terminal):** o **Python do python.org vinha sem certificados** e toda chamada HTTPS falhava (atualização, provedores, downloads) — o ASTA agora usa os certificados do Chaveiro, sem desligar a verificação; o atalho `/usr/bin/python3` da Apple (que abre uma janela pedindo as ferramentas de linha de comando) deixou de ser executado; o **Homebrew do Apple Silicon** (`/opt/homebrew`) é achado fora do PATH; a detecção do Python do Homebrew (`brew upgrade`) funciona com o alias `python`; a dica de PATH usa `~/.zshrc`/`~/.bash_profile` (antes `~/.profile`, que o zsh não lê); sem ferramentas de linha de comando o ASTA **não baixa 300 MB de Rust à toa**.
- **Python embutido do Windows (instalador):** o `pip` é instalado na primeira vez que `asta libs`/`asta update` precisam; `asta update` e o aviso de versão nova funcionam em instalações pelo `.exe` e pelo AppImage.

### Observações e limites
- **Os instaladores e o APK são gerados pelo CI do GitHub e não foram executados em Windows, macOS ou aparelhos Android reais por quem fez esta mudança.** O que pôde ser verificado aqui: o AppImage foi montado e executado (versão, núcleo Rust, servidor); o motor do app Android sobe e recusa quem não tem o cookie (teste); o patcher do projeto Android é idempotente; scripts passam em `sh -n`/`bash -n`. O workflow confere o conteúdo de cada instalador e roda um teste de instalação do Windows.
- **Instaladores sem assinatura** (precisa de certificado pago): no Windows aparece o SmartScreen («Mais informações → Executar assim mesmo»); no macOS, clique com o botão direito no `.pkg` → Abrir.
- **App Android:** modelos locais pesados (GGUF/PyTorch) não rodam dentro do celular — use um servidor na rede (Ollama, LM Studio) ou conecte ao ASTA de um computador. Recursos que usam o ffmpeg dependem de o APK trazer um (`libffmpeg.so`/`libffprobe.so`); sem ele, a análise e a exportação de vídeo ficam indisponíveis no aparelho.
- Contextos de 256K a 1M exigem muita memória (o cache de atenção de 1M tokens de um modelo de 8B ocupa dezenas de GB mesmo com 4 bits): o ASTA avisa, mas **nunca contraria o valor que você escolheu**.
- RAR e 7z precisam de uma ferramenta do sistema (`unrar`, `unar`, `7z` ou `bsdtar`); ZIP e TAR funcionam sem nada.


## [0.13.0] — 2026-11-06

### Melhorado — Timeline do Studio (inspirada no Kdenlive)
- **Mixer de áudio**: um fader por trilha de vídeo e de áudio, em **dB** (−60 a +6; dois cliques voltam a 0 dB; dá para digitar o valor), botão de mudo, **medidor de nível ao vivo** durante a reprodução e o **volume geral (Principal)**. O volume de cada trilha e o geral valem **na prévia e na exportação** (multiplicam o volume dos clipes) e ficam salvos no projeto.
- **Monitor do clipe** ao lado do monitor do projeto: um clique numa mídia da lista a mostra ali; marque **entrada (I) e saída (O)** e use **Inserir** (no cursor, empurrando o que vem depois) ou **Sobrescrever** (sem mexer nos outros clipes).
- **Barra de baixo** com a posição/duração e um **controle de zoom** deslizante; **trilhas recolhíveis** (seta no cabeçalho). Botões na barra de ferramentas mostram/escondem o monitor do clipe e o mixer.

## [0.12.7] — 2026-11-06

### Adicionado — Studio
- **Editar direto na timeline, sem gerar nem automatizar.** Novo modo «Editar na timeline» ao lado de «Gerar com IA» e «Edição automática»: dá nome, formato e duração estimada e abre uma **timeline vazia** (episódio já pronto, sem roteiro) para importar mídias, cortar, juntar, ajustar volume, pôr legendas e exportar. Nenhuma IA roda a menos que você peça; o projeto reabre sempre na timeline.

## [0.12.6] — 2026-11-06

### Melhorado — Edição automática em camadas
- **A edição automática não emenda tudo na mesma trilha.** Quando há um vídeo principal comprido e material curto (memes, reações, fotos, b-roll), o principal corre sozinho na **V1** e o curto vai para a **V2**: em **Gameplay** e **Tutorial** como janelinhas (*picture-in-picture*) que alternam os cantos; em **Documentário** e **Vlog** como planos de cobertura em tela cheia enquanto o som do principal continua. As sobreposições se espalham pela duração, sem encostar umas nas outras. Música e narração seguem nas trilhas A2/A1 e títulos na T1. Com vários vídeos de tamanho parecido a edição continua em sequência na V1, e os estilos de batida (Phonk, Clipe musical), Trailer e Fotos não usam camadas.
- Corrigido: quando faltavam poucos décimos de segundo para o alvo, a edição acrescentava um corte inteiro e passava da duração; e, com poucos picos de volume, o Gameplay repetia o mesmo trecho em vez de usar o resto do vídeo.

## [0.12.5] — 2026-11-06

### Adicionado
- **OpenRouter no Studio e no Canvas (imagem, vídeo e voz).** Além do texto (roteiro, análise, edição automática), o OpenRouter agora é um provedor de **mídia**: imagens (`/images`), vídeos (`/videos`, com envio, consulta e download) e vozes (`/audio/speech`), com a mesma chave ou login do chat. No Studio, quem usa o OpenRouter no chat e não escolheu outro provedor de mídia já gera imagens, narração e (com «Modelo de vídeo em cada plano») clipes de vídeo pelo OpenRouter, sem configurar mais nada; a edição (timeline, cortes, exportação) segue no ffmpeg. Em Configuração → Mídia dá para escolher o OpenRouter por tipo e carregar os modelos atuais.

## [0.12.4] — 2026-11-06

### Testes — provedores em todas as seções
- **Bateria de conformidade de provedores** (`tests/test_all_providers.py`): um servidor falso fala as APIs reais (OpenAI Chat Completions — usada por OpenAI, Grok, Gemini, OpenRouter, Hugging Face, Ollama, LM Studio, llama.cpp e personalizado — e Anthropic Messages), com e sem streaming, e o provedor embutido (GGUF) roda com um llama-cpp falso. **Todos os 11 provedores de texto passam em Chat, Mundos 3D, Avatars (criação e conversa), Jogos 2D e nós de texto do Canvas; Studio passou em 4 deles** (Claude, ChatGPT, Ollama e o embutido); conferem também o formato de imagens, do prompt de sistema e dos cabeçalhos de cada tipo, e a degradação sem visão.
- Provedores de mídia: cada capacidade declarada (imagem, vídeo, som, voz, transcrição) tem implementação própria, e cada uma tem ao menos um provedor local ou sem chave.
- Limite conhecido: modelos locais com janela de contexto menor que o pedido de um agente caem nas regras do ASTA para aquele passo (em vez de derrubar a geração).

## [0.12.3] — 2026-11-06

### Corrigido — Canvas
- **«Erro inesperado: … requires the Torchvision library»** ao gerar imagem com modelos locais como o Qwen-Image: agora a mensagem diz o que fazer (`pip install torchvision`, ou `asta libs --extras media`) e a **torchvision entrou nas bibliotecas de mídia** (instaladores e `asta update` passam a instalá-la).
- **Menu «…» do nó (Gerar de novo, Duplicar, Apagar) aparecia longe do botão** quando a interface estava ampliada (escala ≠ 100%). O posicionamento dos menus flutuantes agora mede a escala no próprio navegador e fica colado no botão; vale também para o seletor de modelo do Chat e demais menus.

## [0.12.2] — 2026-11-06

### Alterado
- **Chat: toda resposta tem, no mínimo, 2K tokens de espaço.** O tamanho das respostas (Configuração → Chat) tem piso de 2.000: valores menores, antigos ou digitados, sobem para 2.000 em cada envio; o campo e os atalhos (2K, 4K, 8K, 16K) respeitam o piso. Valores maiores continuam valendo.

## [0.12.1] — 2026-11-06

### Adicionado
- **Pesquisa no seletor de modelo do Chat**: um campo no topo filtra, de uma vez, os modelos de **todos os provedores prontos** (nuvem e locais) — por nome do modelo ou do provedor, com vários termos. **Enter** escolhe o primeiro resultado; provedores sem chave aparecem quando o nome combina e levam para a configuração.

## [0.12.0] — 2026-11-06

### Melhorado — Núcleo Rust v2 (carga e inferência de modelos locais)
- **Cabeçalhos sem carregar os pesos**: leitura de GGUF e safetensors em Rust (arquitetura, camadas, contexto de treino, quantização dominante, parâmetros, custo do cache de atenção por token).
- **Planejador por hardware livre agora** (RAM, VRAM, núcleos físicos, memória unificada da Apple): camadas na GPU, janela de contexto que cabe (com cache de atenção em 8 bits quando precisa), threads = núcleos físicos, lotes, `mlock`, pré-carga e cache de prompt. O contexto definido pelo usuário nunca é contrariado (só avisa).
- **Mídia (imagem, vídeo, som, voz)**: plano pelo tamanho real dos pesos — tudo na GPU, descarga do modelo, descarga sequencial (pouca VRAM) ou CPU, com fatias de atenção/VAE.
- **Pré-carga paralela** dos pesos para o cache do sistema antes de carregar (várias threads + `posix_fadvise` no Linux).
- **Cache de prompt** (llama-cpp) com tamanho decidido pela RAM sobrando.
- Hardware: núcleos físicos/lógicos, AVX2/AVX-512/NEON, RAM total/disponível (respeitando limite de contêiner) — também em Python quando não há o núcleo. Configuração → Desempenho mostra o estado e o último plano.
- O mesmo cálculo existe em Python; os testes conferem Rust × Python (inclusive 200 cenários aleatórios). Bibliotecas antigas (interface 1) continuam servindo o áudio; `asta update` recompila a nova.

## [0.11.0] — 2026-11-06

### Adicionado — Canvas
- **30 nós novos, 5 em cada tipo**: Texto (modelo, juntar, editar, escolher trecho, refinar com IA), Imagem (redimensionar/girar, filtros e cor, texto na imagem, colagem, quadro do vídeo), Vídeo (cortar, juntar clipes, velocidade/reverso, visual, imagens em vídeo), Som (cortar, misturar, efeitos, áudio do vídeo, repetir), Input (cor/degradê, silêncio, link, sorteio de texto, data e projeto) e Output (vídeo final, GIF, áudio final, imagem final, galeria). Rodam com ffmpeg e Python, sem modelo nem chave (só «Refinar com IA» usa o modelo de texto).

### Alterado
- **Paleta reorganizada**: Texto, Imagem, Vídeo, Som, Input, Output (nós antigos e novos nos grupos certos).
- **Integração entre todos os nós**: vídeo agora liga em portas de imagem (usa o quadro do meio) — inclusive nas referências do nó Imagem e na imagem inicial do Vídeo; texto, imagem, vídeo e áudio entram no Editor e na Galeria; cada tipo de saída tem destino em nós antigos e novos. Canvases antigos abrem sem mudança.
- Mensagens de erro dos nós novos citam o nome da porta como aparece no nó.

## [0.10.5] — 2026-11-06

### Adicionado
- **Quantizações menores para os modelos de Mídia** (Configuração → Mídia → Precisão e download): além de fp32/fp16/bf16, o painel de cada modelo procura na Hugging Face as **versões comprimidas da comunidade** (8 bits, 4 bits/NF4, fp8…) ligadas ao modelo original, com o tamanho de cada uma, e «Usar esta» troca o modelo escolhido por aquele repositório para baixar. Aparecem primeiro as que o ASTA carrega, da menor para a maior; GGUF/AWQ/GPTQ aparecem marcadas como não suportadas ali. Funciona para imagem, vídeo, som, voz e transcrição. São feitas por terceiros e 8/4 bits pedem a biblioteca bitsandbytes (placa NVIDIA).

## [0.10.4] — 2026-11-06

### Corrigido
- **Canvas: gerar imagem com modelo local ainda não baixado** só mostrava um erro. Agora, se o modelo escolhido não foi baixado, o ASTA usa outro já baixado da mesma função (o padrão ou uma sugestão) e avisa no nó; se nenhum foi baixado, o erro ganha o botão «Baixar o modelo agora» (abre Configuração → Mídia na escolha da precisão). Nada é baixado em silêncio. Vale para imagem, som, voz, transcrição e vídeo.

## [0.10.3] — 2026-11-06

### Adicionado
- **Entrar com a conta nos provedores de IA**: o **OpenRouter** ganhou login OAuth/PKCE oficial («Entrar com a conta», sem copiar chave; «Desconectar»). Para **Claude, ChatGPT, Grok, Gemini e Hugging Face**, que não permitem que apps de terceiros usem o login da conta ou da assinatura, o cartão tem «Entrar na conta e criar a chave» (abre o login deles já na página das chaves). As chaves de API continuam valendo em todos; o login só roda no computador do ASTA.

## [0.10.2] — 2026-11-06

### Corrigido
- A aba Releases do repositório estava vazia (o APK só era gerado ao publicar uma Release à mão). O workflow `android-apk` agora roda a cada push na `main` que muda a versão ou o app e cria a Release `vX.Y.Z` com o APK sozinho.

## [0.10.1] — 2026-11-06

### Adicionado — Mobile sem computador
- **App Android (APK) pelo repositório**: pasta `mobile-app/` (casca Capacitor) e workflow `android-apk` que gera o APK e o anexa a cada Release. QR code no README (en/pt-BR) e em Configuração → Celular e tablet leva a `releases/latest`.
- O app pede o endereço do ASTA (QR de pareamento pela câmera ou digitando), lembra o último e **consulta as Releases por versão nova, perguntando «Baixar agora» ou «Depois»**.
- Observação: o app é só a janela, o ASTA em si segue rodando num computador/servidor/VPN; iPhone/iPad seguem com «Adicionar à Tela de Início». O APK é compilado pelo CI e não foi executado em aparelho real nem compilado aqui.

## [0.10.0] — 2026-11-06

### Adicionado — Mobile
- **App mobile (PWA)**: o ASTA instala no celular/tablet (ícone na tela inicial, tela cheia) e fala com o ASTA do seu computador. Manifest, ícones (inclusive maskable e Apple), service worker e meta tags de iOS/Android.
- **Instalação por QR code**: `asta mobile` mostra o QR de pareamento no terminal, e **Configuração → Celular e tablet** mostra o mesmo QR na tela do PC; escanear instala e pareia. O README (en/pt-BR) ganhou a seção «Celular e tablet» (com um QR que abre o guia no celular).
- **Pareamento e segurança**: fora do localhost só entram aparelhos pareados (código secreto no QR, cookie HttpOnly); o computador local não precisa parear; proxy/túnel também exige pareamento; «Gerar novo código» despareia todos. Gerador de QR próprio, sem dependências (versões 1–10, validado com um leitor real).
- **Atualizações no app**: ao abrir, ao voltar ao app, ao recuperar a conexão e a cada 5 minutos o app consulta `/api/version`; se o ASTA do computador tem versão nova, **pergunta «Atualizar agora» ou «Depois»**. Funciona em Wi-Fi e em dados móveis (basta o aparelho alcançar o computador). Service worker com cache «rede primeiro» para abrir sem rede.
- **Plataformas, arquiteturas e aparelhos**: Android e Apple (iOS/iPadOS), qualquer chip (ARM64 — Snapdragon, Apple A/M, MediaTek, Exynos, Tensor — e x86); smartphones, dobráveis, tablets e afins.
- **Interface adaptativa**: o app detecta o tipo de aparelho (celular, dobrável, tablet, computador), a orientação, o estado da dobra, o layout por largura e a plataforma, e se ajusta sozinho — alvos de toque de 44px, campos sem zoom no iOS, áreas seguras (notch/gestos), celular deitado com menu lateral, tablet/dobrável aberto com mais espaço e dobrável dividido por dobradiça com menu numa tela e conteúdo na outra.
- Faixa «Instalar o app» (diálogo nativo no Android; instrução de «Adicionar à Tela de Início» no iPhone/iPad).

### Observações
- A dobradiça dividida (Surface Duo etc.) e o diálogo nativo de instalação dependem de recursos do navegador do aparelho e não puderam ser testados em aparelhos reais aqui; a classificação foi testada com emulação (iPhone, Pixel, iPad, Galaxy Fold).
- Dados móveis fora de casa exigem que o computador seja alcançável de fora (VPN/túnel); isso não faz parte desta versão.

## [0.9.4] — 2026-11-06

### Corrigido
- **Analista e Diretor da edição automática: «nenhum objeto JSON na resposta»**. Causas tratadas: modelo que «pensa» e não fecha o `<think>` (o JSON ficava escondido no raciocínio — agora é procurado ali também); resposta vazia ou só em texto (a nova tentativa repete o formato exato esperado e a instrução `/no_think` pede aos modelos Qwen3 e afins que pulem o raciocínio).
- Quando ainda assim falha, a mensagem mostra o começo do que a IA respondeu (ou «respondeu vazio»), para dar para diagnosticar o modelo.

## [0.9.3] — 2026-11-06

### Corrigido
- **Edição automática: Analista e Diretor caíam no ⚠ (método automático)** quando a IA devolvia a resposta cortada — comum em modelos que «pensam» antes de responder, porque o limite de tokens era pequeno (900). Agora o limite é de 3000, o pedido ao modelo é curto e direto, uma resposta cortada é repetida com o dobro de espaço e, em último caso, a parte válida é aproveitada (o que faltar usa os padrões do estilo).
- Quando um agente ainda precisa do método automático, a tela mostra o motivo («a IA não devolveu um JSON válido…») em vez de só o ⚠.
- Vale também para todos os agentes: respostas cortadas ganham mais espaço na nova tentativa.

## [0.9.2] — 2026-11-06

### Melhorado
- **Edição automática, todos os estilos**, com técnicas de edição por gênero (guias de edição para YouTube/Shorts pesquisados; não consigo assistir aos vídeos, então usei as práticas descritas neles). Cada estilo mostra a sua «Técnica» abaixo da lista e o Diretor de IA recebe essa nota.
  - **Gameplay**: abre com o melhor momento (gancho com zoom) e segue em ordem cronológica.
  - **Documentário e Vlog**: plano de cobertura (b-roll) intercalado (a cada 2 e 3 planos), movimento lento de câmera e pan; no Vlog/Tutorial os cortes de silêncio deixam uma folga na fala.
  - **Phonk e Clipe musical**: introdução mais lenta, «drop»/refrão com cortes de 1–2 batidas e zoom a cada corte, rampas de velocidade só depois da introdução e fecho em câmera lenta.
  - **Trailer**: cartela final com o título; **Apresentação de fotos**: tempos variados e zoom/pan alternados.
  - Nenhum estilo repete o mesmo trecho enquanto houver material novo; a música abaixa quando há narração.
  - O Revisor avisa quando faltou material e cortes repetiram trechos.
- Corrigido: uma foto no fim podia estourar a duração alvo.

## [0.9.1] — 2026-11-06

### Adicionado
- **Configuração → Sistema**: cartão «Componentes do seu PC» com o tipo e o nome de cada componente detectado (CPU, placa-mãe, computador, BIOS, GPUs, discos, áudio, rede, pentes de memória no Windows, RAM e sistema operacional). Detecção local, melhor esforço (Linux, macOS, Windows); nada é enviado para fora.

## [0.9.0] — 2026-11-06

### Alterado
- **Configuração reorganizada**: 16 abas em 4 grupos — **Geral** (Aparência, Seções e atalhos), **IA e modelos** (Provedores, Mídia, Voz, Modelos locais), **Seções** (Chat, Mundos 3D, Avatars, Jogos 2D, Canvas, Studio, Rebuild) e **Sistema** (Desempenho, Dados e backup, Sistema). Cada aba de seção tem um cabeçalho com link para abrir a seção e o botão «Restaurar padrões desta seção».
- «Criativo» foi dividida em **Avatars** e **Jogos 2D**; a aba Aparência ficou só com tema, leitura/conforto e idioma; a de Sistema só com hardware e versão. Os links antigos (`tab=creative`) continuam funcionando.

### Adicionado
- **Padrões por seção** (valem sempre que você cria algo novo): **Studio** (tipo de projeto, duração, estilo, formato, idioma, movimento, revisões, voz, legendas, música, qualidade/áudio da exportação, estilo e duração da edição automática), **Rebuild** (revisão por IA ligada/desligada e limite de chamadas ao modelo), **Canvas** (modelo inicial).
- **Seções e atalhos**: o que aparece na barra lateral (incluindo Studio e Rebuild), a página inicial, atalhos de teclado e tecla de envio, com botões de salto para a aba de cada seção.
- **Dados e backup**: pasta de dados (e o comando `asta folder`), exportar/importar configurações (agora com os padrões de Studio, Rebuild, Canvas e Desempenho) e «Restaurar tudo ao padrão». **Desempenho** mostra o estado do núcleo Rust.
- O servidor guarda `studio`, `rebuild` e `canvas` nas configurações; entram em exportar/importar e restaurar (nunca `chat`, que guarda chaves da busca).

## [0.8.6] — 2026-11-06

### Alterado
- **README (en/pt-BR)**: nova seção «Comandos do terminal» com a tabela de todos os comandos, destacando `asta update` (Python, ASTA, bibliotecas e Rust) e o novo `asta folder`.

## [0.8.5] — 2026-11-06

### Adicionado
- **`asta folder`**: abre a pasta dos dados locais do ASTA (`~/.asta`, ou `--home`/`ASTA_HOME`) no gerenciador de arquivos do computador (Windows: Explorer; macOS: Finder; Linux: `xdg-open`). Cria a pasta se ainda não existir e mostra o caminho. `--print` só mostra o caminho; `--app` abre a pasta do programa instalado. Sem gerenciador de arquivos (ex.: servidor sem tela), avisa e mostra o caminho. Texto em português/inglês conforme o computador.

## [0.8.4] — 2026-11-06

### Alterado
- **O guia de contribuição em inglês agora é o `CONTRIBUTING.md`** — o arquivo que o GitHub mostra na aba «Contributing» do repositório (que só exibe um). A versão em português passou para **`CONTRIBUTING.pt-BR.md`** (como já era com o README). O `CONTRIBUTING.en.md` deixou de existir; os links dos READMEs e dos guias foram ajustados.

## [0.8.3] — 2026-11-06

### Alterado
- **README atualizado** (inglês e português): agora apresenta as seis ferramentas (Studio e Rebuild incluídos), as seções Studio e Rebuild na tabela da interface, as variáveis `ASTA_RUST` e `ASTA_LANG`, o ffmpeg para o Studio, o layout do repositório (`studio/`, `rebuild/`, `native/`) e os links corretos (o menu apontava para âncoras que não existiam).
- **`CONTRIBUTING.en.md`**: tradução completa do guia de contribuição para o inglês (o `CONTRIBUTING.md` continua em português); os dois se referenciam e devem ficar em sincronia.

## [0.8.2] — 2026-11-06

### Corrigido
- **Studio: o vídeo do preview aparecia por cima dos diálogos** (ex.: «Este projeto já tem uma timeline…» na edição automática), furando o fundo escuro. O monitor agora tem a sua própria camada de empilhamento, e a tela cheia do editor fica abaixo dos diálogos. Teste de navegador cobre.

## [0.8.1] — 2026-11-06

### Alterado
- **O Rust agora é instalado/atualizado automaticamente**, sem perguntar, como os outros códigos e bibliotecas: o `install.sh`, o `install.ps1`, o `asta update` e o `asta native setup` instalam o Rust se faltar (rustup, na pasta do usuário, sem sudo), atualizam se já existir e recompilam o núcleo. Vale também sem terminal. `ASTA_RUST=no` (ou `--rust no`) pula e `ASTA_RUST=ask` volta a perguntar. Se algo falhar (sem internet, sem compilador), segue sem Rust — o ASTA funciona igual em Python.

## [0.8.0] — 2026-11-06

### Adicionado
- **Rust opcional nos instaladores, no `asta` e no `asta update`.** Novo comando **`asta native setup`**: instala o Rust (rustup, perfil mínimo, toolchain estável, **na pasta do usuário, sem sudo**) se faltar, **atualiza** (`rustup update`) se já existir e **recompila** o núcleo rápido do ASTA — o mesmo núcleo (`asta_core`) e as bibliotecas que o `cargo` baixar, se um dia houver. Também `asta native install`, `asta native update`, `asta native build` e `asta native status`. O `install.sh`, o `install.ps1` e o `asta update` rodam esta etapa no fim (depois das bibliotecas e dos modelos) e **perguntam** no terminal (`ASTA_RUST=ask`, o padrão; instalar = padrão «não», atualizar o que já existe = padrão «sim»); `ASTA_RUST=yes` (ou `asta update --rust yes`) faz sem perguntar e `ASTA_RUST=no` pula. **Sem terminal o Rust nunca é instalado sem permissão** (só atualiza se já existe). Funciona também com `curl … | sh` (a pergunta lê o terminal de verdade). O `cargo`/`rustup` recém-instalados são achados mesmo fora do PATH (`~/.cargo/bin`, `CARGO_HOME`). Se faltar o compilador do sistema, o ASTA diz o que instalar (Linux: `build-essential`; macOS: `xcode-select --install`; Windows: Ferramentas de Build do Visual Studio). Tudo é opcional e nunca derruba a instalação.
- **Textos do terminal no idioma do computador.** Tudo o que o terminal mostra — `asta`, `asta update`, `asta libs`, `asta models`, `asta native`, `asta doctor`, `--help` e os **instaladores** (`install.sh`, `install.ps1`) — aparece em **português ou inglês**, conforme o idioma do sistema (`LC_ALL`/`LC_MESSAGES`/`LANGUAGE`/`LANG`; macOS: idioma preferido; Windows: idioma da interface); qualquer outro idioma cai no inglês. `ASTA_LANG=pt|en` força um. O `asta` repassa o idioma ao instalador, então os dois falam igual. Novos: `asta/termi18n.py` e `asta/term_en.py`.

### Alterado
- O passo do Rust dos instaladores não depende mais de o `cargo` já estar no PATH: a lógica vive no `asta native setup` (uma só para Linux, macOS e Windows). `asta doctor` mostra a versão do Rust e o idioma do terminal; o cartão de Desempenho (Configuração → Sistema) aponta para o `asta native setup`.

### Testes
- `tests/test_terminal_lang.py`: detecção de idioma (variantes do português, prioridade das variáveis, `ASTA_LANG`, `C`/`POSIX`), toda mensagem do código tem tradução (e os mesmos `{campos}`), saída e `--help` por idioma, o instalador recebe o idioma e a escolha do Rust, `native setup` (sim/não/pergunta/sem terminal/falhas), `find_tool`, comandos `native` e `--rust`, `install.sh` (sintaxe, detecção de idioma, toda mensagem bilíngue) e `install.ps1` (mensagens bilíngues). Os testes de terminal existentes fixam `ASTA_LANG=pt`.

### Limites conhecidos
- O `install.ps1` foi escrito com cuidado e conferido por testes de estrutura, mas **não foi executado num Windows de verdade** nesta sessão (não há PowerShell aqui); o `install.sh` foi executado e testado. No Windows, compilar o núcleo exige as Ferramentas de Build do Visual Studio (o ASTA avisa).

## [0.7.1] — 2026-11-06

### Corrigido
- **Atalhos de teclado da timeline (modo manual):** depois de mexer num campo do inspetor (velocidade, filtro, volume…) o foco ficava preso nele e **S, J, M, C, Del, Space deixavam de funcionar** até clicar fora — agora o foco sai do campo sozinho (e clicar na timeline também o solta). Botões da barra não roubam mais o foco (Space não aciona o último botão clicado). **Segurar uma tecla** (Del, S, J…) não repete a ação em rajada. **S** corta o que estiver sob o cursor mesmo quando a seleção não passa por ele. O **cursor pode ir além do fim** da timeline (para posicionar um clipe novo; antes travava no fim).
- **Mídias sumiam do bin** ao trocar de aba (ou ao entrar em «Editar do zero» e importar arquivos): a tela usava uma cópia velha do projeto. Agora a timeline sempre carrega o projeto atualizado, e um projeto com mídias abre o editor mesmo sem clipes.
- O preview mostrava o quadro preto no começo (por causa do fade de entrada); parado, agora mostra o quadro inteiro.

### Adicionado
- **Janelas da timeline redimensionáveis:** arraste as divisórias para mudar a **largura das mídias**, a **largura das propriedades** e a **altura monitor × timeline** (dois cliques voltam ao padrão), **trilhas mais altas/baixas** e **tela cheia do editor** (`F`; `Esc` sai). Os tamanhos ficam guardados no navegador.
- **Copiar, recortar e colar** clipes (`Ctrl+C`, `Ctrl+X`, `Ctrl+V` — cola no cursor), `Esc` limpa a seleção e volta à ferramenta de seleção.

### Testes
- `tests/browser/studio_ui.js`: foco depois do inspetor, copiar/colar, tecla segurada, Space após botão da barra, cursor além do fim, corte sob o cursor, redimensionar as três divisórias, lembrar o tamanho ao recarregar, tela cheia e edição manual com importação e troca de aba.

## [0.7.0] — 2026-11-06

### Adicionado
- **Studio — gere, edite e revise vídeos audiovisuais com IA** (nova seção, logo abaixo de Canvas). Tudo o que já existia continua igual; o Studio reaproveita os provedores de texto (Configuração → Provedores) e de mídia (Configuração → Mídia: imagem, vídeo, som, voz), inclusive o modo Demo offline e os modelos locais.
  - **Tipos de duração:** **Shorts/Reels** (até 2 min), **Curta** (até 30 min) e **Longa** (até 90 min) — mais **Personalizada** (qualquer duração, até 6 h). A duração é fácil de ajustar: minutos + segundos, controle deslizante e atalhos (30 s, 1 min, 5 min, 1 h 30…); passar do limite do tipo muda o tipo sozinho. Cada tipo começa no seu padrão (formato 9:16 nos Shorts, 16:9 nos demais) e planeja cenas do tamanho certo (≈8 s, ≈40 s, ≈90 s).
  - **Estilos:** Realista, Cartoon, Anime e Custom (você descreve o visual). O estilo entra em todos os prompts de imagem, junto com a aparência dos personagens da «bíblia» do projeto, para manter a continuidade.
  - **Tipos de projeto:** **Único** (começa e termina num vídeo) e **Série** (vários episódios; cada episódio recebe a bíblia da série — personagens, mundo, tom, fatos — e os resumos dos anteriores, e ao terminar atualiza a bíblia e escreve o seu resumo).
  - **Pipeline de geração cena a cena (multi-agente, multi-etapa):** o **Showrunner** escreve o roteiro (em atos, se forem muitas cenas) e, **para cada cena, um passo de cada vez antes de passar à próxima**: **recebe** (briefing + contexto + continuidade) → **analisa** (o Analista divide em planos, ajusta a narração à duração, define música e efeito) → **gera** (voz, imagens, movimento — Ken Burns leve ou o modelo de vídeo do provedor —, música e efeito) → **revisa** (verificações objetivas + Revisor de IA; se reprovar, aplica a correção e refaz só o que mudou) → **entrega** (coloca os clipes na timeline). A tela mostra o quadro de cenas ao vivo com os cinco passos de cada uma. Cena entregue fica salva: dá para **cancelar e continuar** de onde parou e **refazer uma cena sozinha** (a timeline se ajusta sem tirar o resto do lugar). Sem IA de texto (Demo) ou com resposta inválida, agentes determinísticos assumem.
  - **Edição automática:** vários anexos (vídeos, imagens, áudios) + um prompt + um **estilo de edição** — **Gameplay** (momentos de ação pelos picos de volume, cortes rápidos, zoom nos destaques), **Documentário** (cortes longos, transições suaves, título, narração em destaque), **Edit Phonk** (cortes na batida, câmera lenta/rápida, zoom, filtro granulado, música no talo), **Trailer** (ritmo que acelera, cartelas), **Vlog** (corta o tempo morto), **Tutorial** (remove pausas), **Clipe musical** (cortes no compasso) e **Apresentação de fotos**. Pipeline: **Analista** (papel de cada arquivo: filmagem, b-roll, música, narração; mede trocas de cena, picos de volume e silêncios com o ffmpeg) → **Diretor** (ritmo, ordem, destaques, trechos a evitar, títulos) → **Revisor** → montagem na timeline. Funciona também dentro de um projeto (como novo episódio, numa série).
  - **Timeline estilo Kdenlive:** bin de mídias (importar, arrastar para a timeline), **monitor** de preview com reprodução (vídeo, áudio, legendas, filtros e fades), **inspetor** de propriedades e trilhas (T1, V2, V1, A1–A3) com ferramentas de **cortar** (S ou lâmina C), **juntar** (J), **silenciar** (M), **excluir** e **excluir fechando o espaço**, duplicar, aparar no cursor, mover/aparar com **ímã** e modo **ripple**, texto, marcadores, velocidade (0,25×–4×), volume, fades, opacidade, escala/posição, ajuste (preencher/caber/esticar) e **filtros de cor** (P&B, quente, frio, vivo, VHS, cinema, phonk); travar/ocultar/silenciar trilhas, seleção por retângulo, menu de contexto, **desfazer/refazer**, zoom (Ctrl+roda) e **salvamento automático**.
  - **Exportação:** **Completo** (vídeo + áudio, MP4), **Somente vídeo** e **Somente áudio** (M4A, MP3 ou WAV), em 480p/720p/1080p; as exportações ficam listadas com abrir/baixar/excluir.
  - Novos: `asta/studio/` (esquema `asta.studio.v1`, armazenamento, pipeline, edição automática, exportação, ferramentas ffprobe/ffmpeg), rotas `/api/studio/*`, `asta/web/js/views/studio*.js`. O renderizador do Canvas ganhou clipes com **velocidade**, **mudo** e **filtros** e os modos **vídeo/áudio** (sem mudar nada para quem já usa).

### Corrigido
- O seletor de duração não embaralha mais os minutos e segundos enquanto você digita.

### Limites conhecidos
- A qualidade do vídeo final depende dos provedores de mídia escolhidos; no modo Demo as imagens, vozes e músicas são sintéticas. Vídeos muito longos (filmes de 90 min) geram centenas de planos e podem levar horas e custar bastante com provedores pagos — por isso a geração é retomável.
- O preview do navegador aproxima filtros e fades com CSS; a exportação (ffmpeg) é a referência. A edição automática não transcreve fala (usa picos de volume, trocas de cena e silêncios).

### Testes
- `tests/test_studio.py` (esquema, armazenamento, render com modos/velocidade/mudo/filtros, pipeline cena a cena com retomada e refazer cena, planejamento em atos, agentes de texto e correções do Revisor, série, edição automática por estilo, API e exportação completo/vídeo/áudio) e `tests/browser/studio_ui.js`.

## [0.6.3] — 2026-11-06

### Corrigido
- **Avatar que não respondia («O provedor não devolveu nenhum texto»).** Antes, bastava o streaming vir vazio para o avatar ficar mudo. Agora, numa conversa a dois, o ASTA tenta de outras formas antes de mostrar o erro: **(1)** repete **sem streaming** (alguns servidores/modelos só mandam a resposta inteira; um modelo que só «pensou» ganha mais espaço de resposta); **(2)** repete com um **pedido simplificado** — sem o papel `system` (modelos de template estrito, como Gemma e Mistral, devolvem vazio com ele) e com o `/no_think` dos modelos Qwen3; só então avisa, com o motivo. Nada de mensagem vazia no histórico.
- **Modelo local mudo com o modo de desempenho Leve.** Se o modelo GGUF embutido não devolve nenhum texto com flash attention / cache KV de 8 bits (depende da versão/build do llama-cpp), o ASTA o recarrega só com o carregamento básico, lembra disso para aquele modelo e tenta de novo — no streaming e fora dele.

### Testes
- Avatar: streaming vazio → sem streaming; só o pedido simplificado funciona; modelo que só «pensou»; tudo vazio continua explicando o erro. Modelo local: stream/chat vazios recarregam no modo básico.

## [0.6.2] — 2026-11-06

### Adicionado
- **Barra de abas do Chat que desliza para os lados**: com muitas abas, role com a **roda do mouse**, **arraste** a barra com o mouse/dedo ou use o gesto horizontal do touchpad; a aba da frente sempre fica visível. Clicar logo após arrastar não troca de aba sem querer.
- **Tela dividida, estilo Firefox — duas abas na mesma tela, lado a lado.** **Botão direito numa aba** → *Dividir a tela com uma aba nova* ou *Dividir a tela com…* (escolhe uma das outras abas). As duas abas viram um **grupo** na barra (ícone de colunas, borda tracejada entre elas) e aparecem em dois painéis, cada um com a própria rolagem e a resposta chegando em tempo real. A caixa de texto vale para o **painel com foco** (borda de destaque em cima; clique num painel para dar o foco a ele). Clicar numa aba de fora do grupo mostra só ela e o grupo continua na barra; clicar no grupo volta à tela dividida. *Desfazer a tela dividida* (botão direito) ou fechar uma das duas abas desfaz a divisão; a divisão volta depois de recarregar a página.

### Testes
- `tests/browser/chat_split_ui.js`: barra rolável (roda e arrastar), menu do botão direito, painéis lado a lado, foco e envio por painel, grupo na barra, aba fora do par, recarregar, desfazer, divisão com aba nova e fechar uma das duas. O teste `chat_stream_ui.js` ficou mais robusto (esperava a primeira resposta terminar antes de apagar a conversa).

## [0.6.1] — 2026-11-06

### Alterado
- **Todas as seções criam dentro da própria página, sem obrigar a ir ao Chat.** Mundos, Avatars, Jogos 2D e Rebuild ganharam, no topo, o mesmo compositor do Chat (texto, anexos, opções da ferramenta e Run) — com o acompanhamento e o resultado aparecendo na seção. Em Mundos, Jogos 2D e Rebuild, os botões «Novo…» e «Criar com IA» levam ao compositor da seção; «Atualizar» (num jogo ou mundo) coloca o compositor em modo atualização (com «× Criar um novo» para sair). Os botões do resultado («Novo jogo», «Tentar de novo»…) voltam para a seção de onde a criação partiu; criar pelo Chat continua igual. Voltar a uma seção com uma criação dela em andamento retoma o acompanhamento. O Canvas já criava na própria página (modal «Novo canvas»).
- A tela vazia do editor de Mundos aponta para o compositor da seção, e não mais para o Chat.

### Testes
- `tests/browser/sections_inline_ui.js`: cada seção cria e mostra o resultado sem sair dela (hash nunca vira `#/main`), «Atualizar» em modo atualização, Rebuild com aviso legal, e o Chat continua funcionando.

## [0.6.0] — 2026-11-06

### Adicionado
- **Rebuild com pipeline multi-agente e multi-etapa para melhorar a qualidade, principalmente com modelos locais pequenos.** A conversão determinística (que mantém a estrutura igual à do original) continua igual; depois dela, agentes de IA revisam **só o texto**, em etapas curtas: **Perfilador** (tom/cenário e nomes legíveis para eventos e mapas genéricos como `EV012`/`Map003`) → **Polidor** (falas em lotes de até 6: digitação, maiúsculas, pontuação e símbolos soltos; nunca traduz) → **Auditor** (desfaz mudanças que alteraram o sentido) → validação final. Novo `asta/rebuild/refine.py`; o `RebuildPipeline` agora usa o `Runner` dos demais pipelines (logs dos agentes vão no ZIP, em `agent_logs`).
  - **Feito para modelos pequenos:** entradas de poucas centenas de tokens, saída em JSON plano, temperatura baixa, lote que falha é refeito fala por fala, teto de 40 chamadas por reconstrução, só as falas que parecem ter problema são enviadas.
  - **A IA não pode estragar nada:** cada fala devolvida passa por validadores (marcadores `{x}`/`[x]`, números, tamanho, quebras de linha, semelhança de palavras sem acento — traduções e reescritas são recusadas) e nomes por um validador próprio; uma **trava estrutural** compara a «impressão digital» do jogo sem os textos antes e depois e, se algo além de texto mudou, devolve tudo ao resultado determinístico. Erro/queda do modelo só gera um aviso.
  - **Limpeza sem IA** (sempre roda): restos de códigos do motor (`\C[2]`, `\N[1]`, `{w}`, `{i}`…), acentos quebrados (UTF-8 lido como Latin-1) e espaços duplicados.
  - No compositor do Rebuild, a opção **Revisar o texto com IA** (ligada por padrão; também `refine: false` na API). Sem provedor de IA (modo Demo) as etapas de IA são puladas e só a limpeza roda. A tela de resultado mostra o resumo da revisão.

### Limites conhecidos
- Testado com um provedor falso e projetos sintéticos; a qualidade com modelos locais reais não foi medida. A IA corrige texto e nomes; não reescreve diálogos, não traduz e não reorganiza a estrutura (de propósito).

### Testes
- `tests/test_rebuild_refine.py`: limpeza, detecção, validadores, lotes, repetição fala a fala, Auditor, teto de chamadas, trava estrutural, visual novel, pipeline com/sem provedor, `refine: false` e provedor fora do ar.

## [0.5.1] — 2026-11-06

### Adicionado
- **Nova seção «Rebuild» na barra lateral** (logo abaixo de Canvas): lista só os jogos reconstruídos e tem o botão «Reconstruir um jogo». Pode ser ocultada em Configuração → Aparência como as demais; os atalhos Alt+N seguem a nova ordem (Rebuild = Alt+6, Biblioteca = Alt+7, Configuração = Alt+8).

### Corrigido
- A seção Rebuild não aparecia em quem já tinha a 0.5.0: o atualizador só reinstala quando o número da versão sobe. Esta versão (0.5.1) existe para que `asta` atualize sozinho; se a barra ainda não mostrar o Rebuild, rode `asta update --force` e recarregue a página (Ctrl+Shift+R).

## [0.5.0] — 2026-11-05

### Adicionado
- **Rebuild — reconstrução de jogos existentes em HTML/CSS/JS puro** (*Início → Rebuild*). Anexe um ZIP (ou arquivos soltos) e o ASTA reconstrói a **estrutura** do jogo com a **mesma organização do original**, num jogo que roda em qualquer navegador. **Só dois motores são suportados nesta versão:** **Ren'Py** (scripts `.rpy`: labels, diálogos, menus, jumps/calls, variáveis, `if`) e **RPG Maker 2000, 2003, XP, VX, VX Ace, MV e MZ** (mapas, eventos com páginas/condições, mensagens, escolhas, switches/variáveis, teleportes, lojas, batalhas, heróis, itens, inimigos, tropas, eventos comuns). Detecta o motor sozinho; ZIP desconhecido, criptografado ou compilado (`.rgss*a`, `.rpa`, `.rpyc`, MV/MZ criptografado) recebe uma mensagem clara.
  - Novos pacotes `asta/rebuild/`: leitor de `.rpy`, leitor de Marshal do Ruby (XP/VX/Ace), leitor binário LCF (2000/2003), leitor JSON (MV/MZ), conversor comum para o motor de RPG do ASTA e conversor Ren'Py → visual novel.
  - **Só a estrutura é reconstruída; arte, áudio e fontes originais nunca são lidos nem copiados.**
  - **Aviso legal no fim de toda reconstrução** (tela de resultado e `LEGAL-NOTICE.md` no ZIP, também anexado ao README do jogo): não publicar na Steam ou outras plataformas; uso pessoal apenas; qualquer problema legal é responsabilidade de quem reconstrói, não do criador/colaboradores do ASTA; e «mesmo com este aviso, não iremos impedir você de reconstruir, mas tenha consciência das suas ações». Rotas `POST /api/games/rebuild` e `GET /api/games/rebuild/notice`.
- **Núcleo Rust opcional (`asta/native`)**, só biblioteca padrão (sem crates), carregado por `ctypes`, com **equivalente em Python para toda função**. Acelera a síntese de áudio do Canvas (música, efeitos, voz → PCM 16 bits) trabalhando em buffers compartilhados (`array('d')`) em vez de um objeto Python por amostra: numa música de 20 s, de ~15 s para ~0,05 s. Comandos `asta native [build|status]`; `asta doctor` mostra o estado; `ASTA_NO_NATIVE=1` desliga e `ASTA_NATIVE_LIB` aponta uma biblioteca própria. Os instaladores (Linux/macOS/Windows) compilam sozinhos quando o `cargo` existe, sem nunca falhar por isso.
- **Modo de desempenho** (*Configuração → Sistema → Desempenho*; `settings.performance`): Automático (pelo hardware), Leve, Equilibrado, Máximo. No Leve: janela de contexto limitada (valor definido pelo usuário sempre vence), `mmap` e lote menor, flash attention + cache KV de 8 bits, **descarga automática de modelos ociosos** (padrão 10 min; até 3 min no Leve) e, nos modelos locais de imagem/vídeo, fatias de atenção/VAE e descarga para a CPU. Opções que a versão instalada do llama-cpp-python não conhece são puladas.

### Alterado
- `asta doctor` mostra o núcleo Rust e o modo de desempenho. O pacote inclui o código-fonte do núcleo (`native/Cargo.toml`, `native/src/*.rs`).
- Roadmap: «reescrever o backend em Rust» virou «levar mais trechos críticos para o núcleo Rust».

### Limites conhecidos
- O Rebuild foi testado com projetos sintéticos de cada motor; o leitor LCF (2000/2003) não foi validado em arquivos comerciais reais.
- O ganho do Rust foi medido só na síntese de áudio; a economia de RAM/VRAM do modo Leve não foi medida em GPUs ou modelos reais.

### Testes
- `tests/test_rebuild.py` (todos os motores, ZIP, avisos, API) e `tests/browser/rebuild_ui.js`; `tests/test_perf_native.py` (perfis, limites de contexto, descarga ociosa, fallback do carregamento do llama, equivalência Rust × Python, CLI).

## [0.4.5] — 2026-11-05

### Adicionado
- **Ctrl+J (⌘+J no Mac) abre uma nova aba na seção Chat**, de qualquer tela (de fora do Chat leva ao Chat já com a aba nova); vale junto com Alt+N, `/nova` e a paleta. Segue a opção de atalhos ligados/desligados. Aparece na ajuda (`?`) e na paleta.

### Alterado
- **O Chat não usa mais emojis nas respostas, para economizar tokens.** O prompt do Chat proíbe emojis (mesmo que o usuário use) e, como garantia, o ASTA **tira os emojis** da resposta — ao vivo e no texto salvo (pictogramas, bandeiras, teclas como 1️⃣, sequências com ZWJ, tons de pele). Símbolos comuns (✓, →, ©, ™, ★), acentos e outros alfabetos ficam. Vale só para o Chat (avatares e criações não mudam). Ao vivo, um espaço duplo pode aparecer onde o emoji estava, até a resposta terminar; o texto final sai sem ele.

### Testes
- Remoção de emojis (e o que não pode sumir), streaming, texto salvo e regra no prompt; Ctrl+J no navegador.

## [0.4.4] — 2026-11-05

### Alterado
- **Rodar `asta` (o comando de execução) agora também atualiza/instala tudo**, como o comando de instalação do Windows, macOS e Linux: antes de abrir, roda o instalador oficial (Python, ASTA, bibliotecas e pergunta dos modelos pré-instalados — ele pula o que já está em dia). Acontece **quando há versão nova publicada** e, mesmo sem ela, **no máximo a cada 24 h** (`ASTA_UPDATE_EVERY=<horas>`; `0` = a cada abertura). Depois de atualizar, o ASTA se reabre sozinho já na versão nova (no Windows o instalador continua numa janela nova e o ASTA fecha, para poder trocar os arquivos).
  - **Segurança para o dia a dia:** só vale para o ASTA instalado pelo instalador oficial (instalação manual/`pip`/editável nunca é mexida); **sem internet abre normalmente**; se a atualização falhar, abre como está; `asta --no-update` ou `ASTA_NO_UPDATE=1` desligam; sem laço de atualização.
- `asta update` continua existindo para atualizar na hora (`--force`, `--core`, `--extras`…).

### Testes
- `tests/test_cli.py`: versão nova atualiza e reabre (sem laço), em dia e checado há pouco só abre, `ASTA_UPDATE_EVERY=0`, nunca mexe em instalação manual / desligado / sem internet / falha, e o caso Windows.

## [0.4.3] — 2026-11-05

Versão de **auditoria**: percorri todas as seções (Chat, Mundos, Avatars, Jogos 2D, Canvas, Biblioteca, Configuração) como alguém que abre o ASTA pela primeira vez — pelo navegador (desktop e celular, tema escuro e claro) e pela API —, revisei os prompts internos e acrescentei as **abas do Chat**. Os mundos, os cinco gêneros de jogo, os avatares e o Canvas foram gerados e abertos (sem erros no console).

### Adicionado
- **Abas no Chat e o comando «Nova aba de chat».** Cada aba é uma conversa; dá para ter várias abertas e **uma resposta continua chegando em segundo plano** enquanto você usa outra aba (a aba ocupada mostra um indicador). Formas de abrir uma aba nova: **Alt+N**, a **paleta de comandos** (Ctrl+K → *Nova aba de chat*, que também funciona de outras telas e leva ao Chat), o botão **Nova aba**, o **+** da barra de abas, ou digitar **`/nova`** (ou `/new`) na caixa de texto. **Alt+W** fecha a aba da frente (a última nunca some; fechar uma aba não apaga a conversa, que continua no Histórico).
  - Cada aba guarda o seu rascunho; as abas abertas **voltam depois de recarregar a página** (na mesma ordem, com a mesma na frente); abrir pelo Histórico uma conversa que já tem aba só traz a aba para a frente; uma aba em branco é reaproveitada (nunca duas em branco). A barra de abas só aparece com duas ou mais abas (a tela continua limpa).
  - Quem sai da tela do Chat no meio de uma resposta e volta vê «Respondendo em segundo plano…» e a resposta aparece quando termina (antes parecia que a pergunta ficou sem resposta).
- **Prompt do Chat revisado:** responde no idioma do usuário, na medida certa; Markdown com moderação; receitas/planos concretos, matemática com os passos, código que funciona; admite quando não sabe em vez de inventar; sabe que **não navega na internet** sozinho e sugere o botão **Web** quando o assunto pede informação atual; lê os anexos pelo nome; mantém a regra do ativador das ferramentas de criação.
- **Regras de JSON nos agentes:** o preâmbulo de todos os agentes (mundo, avatar, jogo) agora pede aspas duplas, sem comentários, sem vírgula sobrando, **sem placeholders como «...»** e, se o modelo raciocina antes, que seja breve e termine com o JSON completo (menos respostas inválidas em modelos pequenos).

### Corrigido
- **A tela Mundos listava os jogos 2D como se fossem mundos** (e abria um deles — «Nenhum mundo para configurar» — em vez do mundo de verdade). Agora só aparecem mundos 3D.
- **Atualizar um jogo (Demo) trocava o nome dele pelo texto do pedido de mudança** («Adicione um final secreto»). O jogo mantém o nome.
- **Títulos do gerador offline terminavam no meio da frase** («Uma vila medieval à beira de um», «Um Jogo Curto De Aventura Com»): o título agora é a primeira frase, sem terminar numa preposição/artigo e só com a primeira letra maiúscula.
- **Um `settings.json` com um valor do tipo errado (editado à mão, ou uma chamada de API errada) derrubava a tela inteira**: `/api/state` passava a responder 500 e o ASTA não abria mais. As configurações agora são sempre normalizadas (na leitura e antes de gravar): objeto onde deveria haver objeto, número/texto/booleano no tipo certo.
- **Corpos de requisição que não são objetos JSON** (lista, texto, número) e listas com tipo trocado (`character_ids: 3`) causavam erro 500 em dezenas de rotas; agora respondem 400 com mensagem clara (ou são ignorados, no caso das listas).
- **Respostas dos agentes com «raciocínio» (`<think>…</think>`) contendo chaves** podiam ser lidas como o objeto JSON; trechos entre chaves que não são JSON («{exemplo}») eram o primeiro candidato. O extrator ignora o raciocínio e segue para o próximo objeto válido; resposta cortada continua sendo reportada.
- **Textos que apareciam em português na interface em inglês:** filtro «Mundos 3D» da Biblioteca, nome «Novo canvas», nome do modelo na resposta do Chat («Demo (offline, sem IA)»), avisos do modo Demo no resultado de avatares, e provedores do Canvas («Servidor compatível com OpenAI»). Textos antigos que ainda mandavam «gerar na tela principal» agora apontam para o Chat.
- **Configuração:** as nove abas escondiam as duas últimas (Aparência e Sistema) atrás de uma rolagem invisível; a página ficou mais larga e as abas quebram de linha. O título «Como posso ajudar?» do Chat estava cinza-claro demais.

### Alterado
- «Novo chat» virou **«Nova aba»** (o botão do topo, o comando da paleta e a ajuda de atalhos). `go('main', {fresh|newtab})` abre/reaproveita uma aba em branco em vez de substituir a conversa.

### Testes
- `tests/test_audit.py`: títulos do gerador offline, extrator de JSON, configurações corrompidas (e arquivo editado à mão), corpos inválidos, mundos × jogos, nome do jogo na atualização, **fuzz de todas as rotas `/api`** (nenhuma pode devolver 500 para corpos de tipo errado), prompts e textos antigos.
- `tests/browser/chat_tabs_ui.js` (Alt+N, `/nova`, paleta, Alt+W, rascunho por aba, respostas em paralelo e em segundo plano, abas que voltam, sair e voltar no meio da resposta), `tests/browser/audit_ui.js` (Mundos só com mundos, traduções, abas da Configuração, título do Chat, Demo honesto) e o teste de envio/streaming reescrito para as abas.

### Observação
- Continuam valendo os limites das versões anteriores: modelos de IA reais, a busca na internet e o 3D em GPU de verdade não foram testados aqui (servidores simulados e Chromium sem GPU). Nos jogos e mundos gerados pelo **Demo**, a história/fala é de regras, não de IA.

## [0.4.2] — 2026-11-05

Revisão do **modo Chat** — principalmente o envio dos prompts e a resposta do modelo em streaming — e o **painel das fontes pesquisadas**, no canto direito. Cada bug foi reproduzido (em teste ou no navegador) antes de corrigir.

### Corrigido
- **Texto embaralhado durante o streaming com modelos que «pensam»** (`<think>…</think>`: Qwen3, DeepSeek R1, gpt-oss…). Reproduzido: com os pedaços `<thi` · `nk>pensando</think>` · `Olá, tudo bem?` a tela mostrava `<thi tudo bem?`; e com o `</think>` sem abertura (o modelo já começa pensando) o raciocínio aparecia e a resposta vinha **cortada no meio**. Agora o ASTA segura no fim o começo de uma tag incompleta e, quando o texto visível muda, manda um evento `reset` que troca o texto inteiro (a resposta salva sempre foi a correta; só a tela errava).
- **Respostas longas deixavam o servidor cada vez mais lento:** a cada pedaço o texto inteiro era limpo de novo (custo quadrático). Agora é incremental (40 mil pedaços em menos de 2 s nos testes).
- **Textos colados com mais de 12.000 caracteres eram cortados em silêncio.** O limite passou a 60.000; o que cabe ao modelo é decidido pela janela de contexto.
- **O texto digitado perdia o foco ao enviar a primeira mensagem** (a caixa muda da tela inicial para o rodapé) — era preciso clicar de novo para continuar escrevendo. O foco e o cursor voltam.
- **A primeira pergunta ficava invisível até o servidor responder** (a tela só mudava no primeiro evento) e, com a busca na web ou um modelo carregando, nada indicava que algo acontecia. O balão «digitando» aparece na hora.
- **Trocar de conversa (ou criar um chat novo) no meio de uma resposta jogava o balão e o texto na outra conversa**, e a corrida entre «parar» e «sincronizar» podia reabrir a conversa antiga. Agora a resposta em andamento é encerrada antes da troca e nada vaza.
- **Depois de Parar (ou de uma falha do modelo) a pergunta ficava sem resposta e sem como pedir de novo** — só digitando tudo outra vez. Aparece o aviso **Responder**; ele também aparece ao reabrir uma conversa cuja última pergunta ficou sem resposta. **Esc** também para a resposta.
- **Falha no envio** (servidor recusou, conexão caiu antes de aceitar): o balão da pergunta ficava na tela. Agora ele some, o texto volta para a caixa e o erro aparece; os anexos só saem da caixa quando o servidor aceita a mensagem.
- **Conversa apagada em outra aba:** todo envio seguinte falhava com «Conversa não encontrada». Agora o Chat abre uma conversa nova e envia de novo.
- **Enter que confirma uma palavra no teclado japonês/chinês/coreano (IME) enviava a mensagem pela metade** em alguns navegadores (`keyCode 229`).
- **Desenho da resposta a cada pedaço:** o Markdown era refeito inteiro a cada pedaço recebido (travava respostas rápidas e fazia o texto selecionado piscar); agora é no máximo um desenho por quadro.
- **Markdown:** sub-listas (a indentação era perdida), endereços soltos (`https://…`) que viram link sem levar o ponto final, e `[1]`/`[1, 2]` que viram botões quando há fonte correspondente.

### Adicionado
- **Painel de fontes no canto direito do Chat:** lista **todas** as fontes pesquisadas, **na ordem em que a busca as devolveu**, agrupadas por pesquisa (Pesquisa 1, 2… com a consulta usada), cada uma com número, título (link que abre em nova aba), site, trecho e o selo **lida** quando a página foi lida por inteiro.
  - Abre sozinho quando chega uma pesquisa (em telas largas; em telas estreitas vira uma gaveta à direita), mostra «Pesquisando…» enquanto a busca roda e enche em tempo real. Botão **Fontes (n)** no topo para abrir/fechar; a escolha de fechar é lembrada.
  - Os botões `[n]` do texto da resposta e o botão **Fontes** sob a resposta levam à fonte no painel e a destacam; clicar no título de uma pesquisa leva à resposta correspondente. As fontes (com trecho e selo) ficam salvas no histórico.
- Atalho: **Esc** para a resposta.

### Alterado
- A tela do Chat agora é um painel de conversa + o painel de fontes lado a lado (`.chx-main` / `.chx-side`); os menus de modelo, ferramentas e pensamento rolam menos.
- `public_sources` (busca) devolve também `snippet` e `read`; as mensagens do Chat guardam `snippet`/`read` nas fontes. Novo evento SSE `reset` ao lado de `delta`.

### Testes
- `tests/test_chat_stream.py`: tags `<think>` cortadas de qualquer jeito (equivale a limpar o texto inteiro), `</think>` sem abertura, `<`/`<th…` que não são tags, linearidade em respostas longas, texto colado grande, falha no meio da resposta (a pergunta fica, nada pela metade, Responder funciona).
- `tests/browser/chat_stream_ui.js`: streaming em tempo real (o texto cresce), balão imediato, foco, `<think>`, Markdown, Parar/Esc → Responder, troca de conversa no meio, conversa apagada, falha de envio, IME e o painel de fontes (ordem, números, selo, citações, segunda pesquisa, fechar/lembrar, tela estreita).

### Observação
- Os testes de streaming usam um servidor simulado do LM Studio: não testei com um modelo real nem com a rede de saída (a busca na web segue testada só com respostas simuladas, como na 0.4.1).
- O painel lista as fontes **que o ASTA pesquisou para a resposta** (a busca é única por mensagem; as páginas lidas por inteiro levam o selo *lida*). O modelo não faz buscas por conta própria.

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

[Não lançado]: https://github.com/KMC1525/ASTA/compare/v0.8.6...HEAD
[0.8.6]: https://github.com/KMC1525/ASTA/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/KMC1525/ASTA/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/KMC1525/ASTA/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/KMC1525/ASTA/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/KMC1525/ASTA/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/KMC1525/ASTA/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/KMC1525/ASTA/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/KMC1525/ASTA/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/KMC1525/ASTA/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/KMC1525/ASTA/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/KMC1525/ASTA/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/KMC1525/ASTA/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/KMC1525/ASTA/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/KMC1525/ASTA/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/KMC1525/ASTA/compare/v0.4.5...v0.5.0
[0.4.5]: https://github.com/KMC1525/ASTA/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/KMC1525/ASTA/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/KMC1525/ASTA/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/KMC1525/ASTA/compare/v0.4.1...v0.4.2
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
