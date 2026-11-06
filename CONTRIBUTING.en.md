# Contributing to ASTA

*Português: [CONTRIBUTING.md](CONTRIBUTING.md) — keep both files in sync.*

Thanks for wanting to help! ASTA is meant to be **simple, light and free**. Before opening a PR, it is worth knowing the principles:

1. **No required dependencies.** The core uses only the Python standard library. Extra dependencies come in as *optional extras* (`pip install "asta[local]"`, `"asta[media]"`) and are imported only when used, with a clear message on how to install them.
2. **No build step.** The WebUI (`asta/web`) and the engines of the 3D worlds (`asta/runtime`) and 2D games (`asta/runtime2d`) are plain HTML/CSS/JS, with no bundler.
3. **Hardware lightness comes first.** Every new 3D feature must respect the budgets in `asta/agents/schema.py` (`BUDGETS`) and work at the `low` tier.
4. **The AI writes data, not code.** The agents produce validated JSON (`normalize_world`, `normalize_game`, `normalize_avatar`, `normalize_canvas`); the engines are reviewed code. Do not execute model-generated code — game conditions use their own grammar, with no `eval`.
5. **Local security.** No open CORS, no exposing keys to the browser, validate paths and `Host`/`Origin`.
6. **Free content, with one fixed line:** no content filters of ASTA's own, but no sexual content involving minors. In the avatars this is in the code (`asta/avatars.py`): someone who describes a minor stays SFW and platonic, and is not "aged up" — do not weaken that rule.

## Environment

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data --no-browser              # isolated data for development
python -m unittest discover -s tests -t .         # runs everything (no network)
```

The JavaScript engine tests and the browser tests (Chromium via Playwright, in `tests/browser`) run when Node.js and Playwright exist and are skipped otherwise; `ffmpeg` enables the Canvas and Studio video tests. CI installs Node 22.

**Rust core (`asta/native`):** optional and standard-library only (no crates). Every function needs a Python equivalent in `asta/native/__init__.py` with the same result. `cargo test --manifest-path asta/native/Cargo.toml` runs the Rust tests; `asta native setup` installs/updates Rust and compiles the core (`asta native build` only compiles); `ASTA_NATIVE_LIB=<path>` makes `tests/test_perf_native.py` compare Rust × Python. **Rebuild (`asta/rebuild`):** never read or copy the original game's art/audio, only the structure; keep the legal notice.

Python 3.9 is the minimum: do not use `match`, runtime `X | Y`, etc. (use `from __future__ import annotations`).

## Where to change things

| I want to… | File |
|---|---|
| Add an AI provider | `asta/providers/registry.py` (preset) — OpenAI-compatible APIs already work |
| Change what the agents do | `asta/agents/prompts.py`, `pipeline.py` |
| New structure/biome type | `schema.py` (lists) + `runtime/scene.js` (builder) + `rulebased.py` (Demo) |
| NPC behavior/actions | `runtime/actors.js`, `runtime/agent.js` |
| WebUI screens | `web/js/views/*.js` (the Portuguese phrase is the translation key; add it to `web/js/en.js` — `tests/test_i18n.py` fails if any is missing) |
| Chat (general conversation, history, creation-tool activator) | `assistant_chat.py`, `routes_chat.py`, `websearch.py` (web search), `providers/thinking.py` (thinking time per provider/model), `web/js/views/chat.js`, `web/js/modelpicker.js`, `web/js/markdown.js` (the creation tools live in `web/js/views/home.js`) |
| Avatars (cards, conversation director, voice) | `avatars.py`, `avatar_chat.py`, `routes_avatars.py`, `agents/avatar_pipeline.py`, `web/js/views/avatar*.js` |
| 2D games (a new genre or a rule) | `games2d/schema.py` (spec and validation), `agents/rulebased_games.py` (offline generator), `runtime2d/*.js` (engine); keep the condition grammar identical in Python (`parse_cond`) and JS (`G2.cond`) |
| Canvas: new node type | `canvas/schema.py` (`NODE_TYPES`, parameters), `canvas/engine.py` (execution), `web/js/canvas_nodes.js` (controls) |
| Pre-installed models (catalog) | `asta/preinstalled.py` (`CATALOG`: repository, file, quantization, size, auxiliary files) + translation of the `hint` in `web/js/en.js` |
| Canvas: new media provider | class in `canvas/media.py` + entry in `MEDIA_PRESETS` + a test with a simulated server in `tests/test_canvas.py` (see `MediaMock`) |
| Canvas video Editor | `canvas/render.py` (ffmpeg) and `web/js/canvas_timeline.js` (timeline and preview) |

## Tests and PRs

- Every fix/feature needs a test in `tests/` whenever possible.
- Describe **what** changed and **why**; record it in `CHANGELOG.md` under *Unreleased* (and in `CHANGELOG.en.md`). `README.md` is in English and `README.pt-BR.md` in Portuguese; `CONTRIBUTING.en.md` is the English twin of `CONTRIBUTING.md`: keep each pair in sync.
- Third-party API adapters: follow the service's public documentation and test against a simulated server — paid services cannot be tested in CI; say in the PR what you actually verified.
- 3D engine changes: attach a screenshot (before/after) — headless Chromium works (`--use-angle=swiftshader`).

## Versions and updating worlds

Each world keeps a *snapshot* of the engine from the moment it was generated (which is why the ZIP is portable). After updating ASTA, use **Library → ⋯ → Rebuild with the latest engine**.

## Studio (`asta/studio`)

- The project document (`asta.studio.v1`) belongs to the server: scenes, assets and episodes only change through jobs/routes; the browser saves only the metadata and the timeline (`PUT .../timeline`), so the editor's autosave never erases what a job has just generated.
- Every Studio AI agent (`pipeline.py`, `autoedit.py`) needs a deterministic equivalent (`rulebased.py` / `plan_edl`): Demo mode and invalid answers must not prevent delivery.
- The renderer is the Canvas one (`canvas/render.py`) with the extra fields `speed`/`mute`/`filter` and the `mode` parameter (`full|video|audio`); keep the old behavior when those keys are absent.
- Tests: `tests/test_studio.py` (uses `ffmpeg` and is skipped without it) and `tests/browser/studio_ui.js`. Synthetic media comes from `make_media()`.

## Terminal text (`asta/termi18n.py`, `asta/term_en.py`)

- Every text the terminal shows (the CLI and the `preinstalled`/`native` messages) uses `_("frase em português {field}", field=...)`; the English translation lives in `asta/term_en.py` (same key, same `{fields}`). A test checks that no message was left without a translation. Do not use `_` as a loop variable in those modules.
- The installers (`install.sh`, `install.ps1`) have their own `L pt en`; every `say/note/die` (`Say/Note/Die`) message must be bilingual — the test checks it.
- Rust lives in `asta native setup` (`asta/native/__init__.py`): the default is automatic (`ASTA_RUST=yes`, no question); `ask` asks and `no` skips.
