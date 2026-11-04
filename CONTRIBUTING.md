# Contribuindo com o ASTA

Obrigado por querer ajudar! O ASTA é pensado para ser **simples, leve e livre**. Antes de abrir um PR, vale conhecer os princípios:

1. **Sem dependências obrigatórias.** O núcleo usa só a biblioteca padrão do Python. Dependências extras entram como *extras opcionais* (`pip install "asta[local]"`).
2. **Sem etapa de build.** A WebUI (`asta/web`) e o motor dos mundos (`asta/runtime`) são HTML/CSS/JS puros, sem bundler.
3. **Leveza de hardware vem primeiro.** Todo recurso 3D novo precisa respeitar os orçamentos em `asta/agents/schema.py` (`BUDGETS`) e funcionar no nível `low`.
4. **A IA escreve dados, não código.** Os agentes produzem JSON validado por `normalize_world`; o motor é código revisado. Não execute código gerado por modelos.
5. **Segurança local.** Nada de CORS aberto, nada de expor chaves ao navegador, valide caminhos e `Host`/`Origin`.
6. **Conteúdo livre, com uma linha fixa:** sem filtros próprios do ASTA, mas nenhum conteúdo sexual envolvendo menores.

## Ambiente

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data --no-browser              # dados isolados para desenvolvimento
python -m unittest discover -s tests -t .         # roda tudo (sem rede)
```

Python 3.9 é o mínimo: não use `match`, `X | Y` em tempo de execução, etc. (use `from __future__ import annotations`).

## Onde mexer

| Quero… | Arquivo |
|---|---|
| Adicionar um provedor de IA | `asta/providers/registry.py` (preset) — APIs compatíveis com OpenAI já funcionam |
| Mudar o que os agentes fazem | `asta/agents/prompts.py`, `pipeline.py` |
| Novo tipo de estrutura/bioma | `schema.py` (listas) + `runtime/scene.js` (construtor) + `rulebased.py` (Demo) |
| Comportamento/ações dos NPCs | `runtime/actors.js`, `runtime/agent.js` |
| Telas da WebUI | `web/js/views/*.js` (a frase em português é a chave de tradução; adicione em `web/js/en.js`) |

## Testes e PRs

- Toda correção/recurso precisa de teste em `tests/` quando possível.
- Descreva **o que** mudou e **por quê**; registre no `CHANGELOG.md` em *Não lançado*.
- Mudanças no motor 3D: anexe um screenshot (antes/depois) — o Chromium headless funciona (`--use-angle=swiftshader`).

## Versões e atualização dos mundos

Cada mundo guarda um *snapshot* do motor na hora em que foi gerado (por isso o ZIP é portátil). Após atualizar o ASTA, use **Biblioteca → ⋯ → Reconstruir com o motor mais recente**.
