<div align="center">

# ASTA

**Create persistent, playable 3D virtual worlds inhabited by characters that are AI agents.**

A minimalist black WebUI inspired by Grok — describe a world (with text, images, video, audio, documents, spreadsheets…) and a team of AI agents plans, builds, reviews and delivers a ready-to-play game as a ZIP.

[Português](README.md)

`MIT` · `Windows` · `macOS` · `Linux` · `Python 3.9+` · `no required dependencies`

</div>

---

## What it is

ASTA is **open source and as free as possible**: it runs on your computer, needs no account or cloud, supports **SFW and NSFW** content (ASTA adds no filters of its own) and works with the models you choose — Claude, ChatGPT, Grok, Gemini, OpenRouter, Hugging Face or fully local models.

- **Playable 3D worlds** in first or third person (HTML + CSS + JS + three.js), as realistic as your hardware allows.
- **Every character/NPC is an AI agent** that thinks and acts: talk by **text** (click the character) or by **voice** in any language; they remember, follow you, flee, dance… and, with autonomy on, decide for themselves.
- **Multi-agent, multi-step generation**: Analyst → Planner → Characters → Architect → Sound & UX → Reviewer → Packager.
- **Delivers a ZIP** with `code/`, `chars/`, `sound/`, `prompts/`, `ui/ux/` and `Game.html`, plus the world's own `README.md` and `CHANGELOG.md`.
- **Library** of projects: update the same game as many times as you like; search and tags (automatic and custom).
- **Light by design**: core uses only the Python standard library; worlds adapt to the hardware (and tune quality in real time).

## Install

You only need **Python 3.9+**. The **same command installs and updates** (your data in `~/.asta` is never touched).

**Linux & macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex
```

Then, in any terminal:

```bash
asta
```

The WebUI opens at `http://localhost:8787`. To update, run the install command again (or `asta update`).
Optional extras: `ASTA_EXTRAS=local` (embedded GGUF models), `ASTA_EXTRAS=docs` (better PDF extraction).

## Getting started

1. **Try it with zero setup.** The default provider is **Demo** (offline, rule-based). Write a prompt on **Main** and send it — watch the agents work, then press **Play**.
2. **Plug in a real AI** in **Configuration → Providers**: paste a key (Claude, ChatGPT, Grok, Gemini…), *Load models*, pick one and *Test*. Or use **Ollama / LM Studio** (free, local).
3. **Create characters and worldbuildings** (or let the AI do it), attach files, generate, play — then open the **Library** and hit *Update* to evolve the same world.

## Sections

`Main` (prompt + live agents) · `Worlds` (configure generated worlds; each save is a new version, no AI used) · `Characters` (cards: name, tags, system prompt, voice) · `Worldbuilding` (general rules, also cards) · `Library` (projects with search and tags) · `Configuration` (providers, generation, voice, local Hugging Face models, system).

## The generated ZIP

```
Game.html   README.md   CHANGELOG.md
code/       3D engine (three.js r159), world data, NPC AI, audio
chars/      one .json per character + chars.js
sound/      procedural ambience/music + attached tracks
prompts/    your prompt, attachments and every agent's log
ui/ux/      theme and in-game interface config
```

**Controls:** WASD move · Shift run · Space jump · V toggle 1st/3rd person · E (or click) talk · M minimap · Esc release mouse. Touch controls on phones.

## Providers

Claude (native API) · ChatGPT / Grok / Gemini / OpenRouter / Hugging Face Inference (OpenAI-compatible) · Ollama / LM Studio / llama.cpp server / any OpenAI-compatible endpoint (local) · Hugging Face GGUF (embedded, `pip install "asta[local]"`) · Demo (offline).

## Content policy

ASTA adds **no content filters**: the default mode follows your prompt and worldbuilding, including adult themes when they fit; **SFW** mode keeps everything all-ages. Your chosen provider may still enforce its own rules. One fixed rule: no sexual content involving minors — it applies even in free mode.

## Development

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -t .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © 2026 KMC. Bundles [three.js](https://threejs.org) r159 (MIT).
