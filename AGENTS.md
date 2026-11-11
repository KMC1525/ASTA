# AGENTS.md — ASTA

Read this first, then follow [`docs/asta-principles.md`](docs/asta-principles.md) (why/what must never be violated) and [`docs/asta-dev-guide.md`](docs/asta-dev-guide.md) (how to work). If an idea conflicts with a principle, the principle wins. User/project-specific instructions in the active request also apply.

## Mission-critical rules (do not violate)

- Follow `docs/asta-dev-guide.md` and never propose changes that contradict `docs/asta-principles.md` (user data control, open source, local-first, optional user-controlled cloud, interoperability, AI in every tool, multi-agent/multi-step everywhere, federation direction).
- Before modifying any code: analyze architecture and related files first. Find existing tests for the area before implementing; add regression tests for fixed bugs.
- Preserve Python ↔ Rust parity: Rust core (`asta/native/`) is mandatory/standard-library-only; every Rust function needs a Python equivalent in `asta/native/__init__.py` with the same behavior. Interface (ABI) changes require bumping `ABI` in `asta/native/__init__.py` and `asta_abi_version` in `asta/native/src/lib.rs` while keeping old libraries working.
- Keep all user-facing/install surfaces in sync when behavior/install/commands/UI/limits change: `README.md` + `README.pt-BR.md` (same structure/content, EN/PT), `CHANGELOG.md` + `CHANGELOG.en.md` (per version `## [X.Y.Z] — YYYY-MM-DD`, user-visible changes + honest limits/what was not verified/tested), and all installers/executables for every platform (Windows `.exe`, macOS `.pkg`, Linux AppImage incl. arm64, Android `.apk`, Rust core per platform). Version lives in `asta/__init__.py` (`__version__`, currently `0.20.1`); changelog comes before release/version bump.
- Never remove existing functionality without explicit authorization. Never `push`, `merge`, or publish releases without explicit authorization. Prefer small, isolated, verifiable changes. Put finished work on `main` only via PR/merge or push as the repo owner authorizes (this repo's CI releases from `main`).

## Architecture (repo map, verified)

- **Local-first Python app** (core deps = stdlib only; extras in `pyproject.toml`). HTTP server local by default (`127.0.0.1`); CLI/entrypoint `asta` (`asta.cli:main`).
- **`asta/server.py`, `routes_*.py`, `jobs.py`** — local HTTP server, per-section routes, background jobs/SSE.
- **`asta/providers/`** — AI providers (OpenAI-compatible, Anthropic, GGUF local, LM Studio, Demo); token/output limits learned from provider (`limits.py`); local llama loading. One contract/provider must work across sections.
- **Sections / engines:** `agents/`, `studio/`, `canvas/`, `rebuild/`, `games2d/`, `avatars*.py`, `assistant_chat.py`; **Game Engine** `gameengine/`+`routes_engine.py`+`web/js/views/engine*.js` (scenes/nodes/maps as validated JSON, runtime in `gameengine/runtime/ge_*.js`); **Scriber** `scriber/`+`routes_scriber.py`+`web/js/views/scriber*.js` (block-JSON doc model, `.docx` via stdlib); **Computer Use** `computer/`+`routes_computer.py`; **Code** `code/`+`routes_code.py`; **Work** `work/`+`routes_work.py`+`web/js/views/work*.js`.
- **Cross-cutting:** `team.py`, `efforts.py`, `web/js/team_ui.js` (agent team for every section: 1–32 agents, effort Low→Omni; use `Runner.configure_team`/`team.from_config`, not custom selectors). `attachments.py`, `archives.py` (all attachment types, safe ZIP/RAR/7z/TAR extraction). `perf.py`, `scheduler.py`, `storage_opt.py` (perf modes, priority queue — local model: one generation at a time). `preinstalled.py` model catalog.
- **Rust core:** `asta/native/src/*.rs`, Cargo in `asta/native/Cargo.toml`, Python mirror/fallback in `asta/native/__init__.py` (v0.17 media/interface changes noted in dev guide). `asta native setup|build|status` manages it.
- **UI:** `asta/web/` plain HTML/CSS/JS (no build). Portuguese-first UI strings in `t('…')` with EN translations in `asta/web/js/en.js`. CLI/terminal strings via `_()` with translations in `asta/term_en.py` (`termi18n.py`). Installers use bilingual `L "pt" "en"`.
- **Install/release:** root `install.sh`, `install.ps1`; `installers/` (`windows/`, `macos/`, `linux/`, `release_notes.py`); `mobile-app/` (Capacitor + embedded Python/Chaquopy); CI `.github/workflows/ci.yml`, `release.yml` (release publishes installers + per-platform Rust core + `SHA256SUMS.txt`; driven from `__version__`/changelog).

## Development workflow & verification

- Python `>=3.9` (keep 3.9-compatible; avoid `match`, runtime `X|Y`). No mandatory deps in Python core; optional extras only.
- Targeted tests while developing: `python -m unittest tests.test_<area>`. Full suite: `python -m unittest discover -s tests -t .` (browser tests need Node + Playwright + Chromium; some tests need `ffmpeg`; CI context may differ — do not claim unverified). Rust: `cargo test --release --manifest-path asta/native/Cargo.toml`. i18n coverage: `node tests/js/i18n_check.mjs`.
- Every new UI/terminal/installer string must be translated (tests enforce). Regression fixes get a reproducing test. State clearly in docs/changelog what could not be tested (real devices, signing certs, external services).

## Required behavior & safety invariants

- **Multi-agent, multi-step everywhere:** every mode/section/tool has plan→do→check (validated JSON, deterministic fallback, logged agents). Every mode offers 1·4·8·12·16·20·24·28·32 agents and 8 effort levels (Low…Omni) via `asta/team.py`/`efforts.py`.
- **Content policy in ASTA:** no ASTA-added filters; modes/sections respect content settings and allow SFW/NSFW freely. Fixed limits that never change: **no sexual content involving minors** and **no sexual content about real people** (avatars enforce strictly; providers may have their own rules — warn, never bypass).
- **Treat inputs as untrusted:** files, packages, URLs, and AI output — validate paths/sizes/types/JSON (zip-slip/bombs, content-type checks). AI produces **data (JSON)** the engine validates, never executable code — except deliberate isolated cases (Game Engine Code tab runs only in sandboxed iframe/CSP no-network/no-same-origin; Code section runs project commands under fixed guards/allowlists, never shell, no secrets exposure, publish only after clean tests/review). Never add tools that execute AI-written shell/eval/script outside those guarded designs.
- **Computer Use:** AI returns validated JSON only; tools declare risk class and all paths go through guards; ASTA data/keys out of reach; single GUI lease. **Code:** path-constrained to project, argv allowlists, restricted git, sanitized env, GitHub token only in settings/redacted, publish irreversible with evidence. **Work:** sync server separate from WebUI (127.0.0.1), signed+encrypted `/peer/v1`, listen off by default, secrets never synced/exported/API (see `work/sync.py`, `manager.py`). **Scriber:** editor/import/AI output sanitized via block model (`docmodel.html_to_blocks`); nonfiction must not invent citations/data. **Game Engine:** AI writes validated data only; CSP/sandbox/path/content guards must not be weakened.
- **Local/privacy:** server loopback by default (mobile/app pairing/strict modes as designed), keys/secrets never exposed to browser, no telemetry, user context window choices not overridden (only warned), model output ceilings learned (`providers/limits.py`). Data in open formats under user-known locations; updates/uninstall must not delete user data.
- **Prompts/packaging:** section prompts (e.g. `computer/prompts`, `code/prompts`, `work/prompts`, `gameengine/prompts`, `scriber/prompts`) are package data — keep `pyproject.toml` `[tool.setuptools.package-data]` in sync when adding/changing them.
- **Honesty in docs/changelog:** mark unverified items (real devices, real headsets, real GitHub/Word, signing, external-service runs, estimates) explicitly; never claim what was not tested.

## When unsure

Prefer reading existing implementation + tests + config as source of truth over guessing. Keep edits minimal and consistent with surrounding patterns. If something important is undocumented and cannot be inferred, ask (brief, only what matters).