<div align="center">

# ASTA

**The first open-source super app: one place to chat with any AI model, search the web, create 3D worlds whose NPCs are AI agents, talk to avatars, build 2D games and produce images, video, sound and voice — all on your computer.**

A minimalist black WebUI inspired by Grok. Describe what you want (with text, images, videos, audio, documents, spreadsheets…) and a team of AI agents plans, creates, reviews and delivers it: a playable 3D world, a companion to chat with, a complete 2D game, or a node flow that produces images, videos, sounds and voices.

[Install](#install) · [Getting started](#getting-started) · [Commands](#terminal-commands) · [Creation tools](#the-creation-tools) · [Studio](#studio--ai-audiovisual-videos-scene-by-scene) · [Providers](#ai-providers) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Português](README.pt-BR.md)

`MIT` · `Windows` · `macOS` · `Linux` · `Python 3.9+` · `no required dependencies`

</div>

---

## What it is

ASTA is the **first open-source super app**: a single app for chatting, researching, creating and playing, with every AI model you like in one place. It is **open source and as free as possible**: it runs on your computer, needs no account or cloud, supports **SFW and NSFW** content (ASTA adds no filters of its own) and works with the models you choose — Claude, ChatGPT, Grok, Gemini, OpenRouter, Hugging Face or fully local models.

It is a universal creation hub with six tools, started from the same prompt box or from their own sections:

| Mode | You get |
|---|---|
| 🌍 **3D worlds** | Playable, persistent 3D worlds (first or third person) inhabited by NPCs that are embedded AI agents. |
| 🙂 **Avatars** | Friends, girlfriends/boyfriends, wives/husbands, companions and mentors to chat with by **text and voice** — one at a time or **several talking to each other**. |
| 🎮 **2D games** | Complete 2D games of any kind: visual novels, RPGs, platformers, side scrollers, point & click adventures. |
| 🎬 **Studio** | **AI audiovisual videos, scene by scene** — Shorts/Reels, short films and features of any length, single or series, in Realistic, Cartoon, Anime or custom style, with **automatic editing** (Gameplay, Documentary, Phonk…), a **Kdenlive-style timeline** and export (full, video only, audio only). |
| ♻️ **Rebuild** | Rebuilds an existing **Ren'Py** or **RPG Maker (2000 → MZ)** game's *structure* in plain HTML/CSS/JS (personal use only). |
| 🧩 **Canvas** | A simple node flow (inspired by ElevenLabs Flow, much lighter than ComfyUI) to generate and edit **images, videos, sounds and voices**, with a built-in video **Editor** and project-wide **styles**. |

Everything you create lands in one **Library** of updatable projects.

- 🧠 **Multi-agent, multi-step generation** (Analyst → Planner → Designer → Reviewer → Packager) with deterministic validation and a rule-based fallback, so something playable is always delivered.
- 🪶 **Light by design**: the core uses only the Python standard library; there is no build step; worlds and games adapt to your hardware.
- 🔒 **Local and private**: the server listens on `127.0.0.1`, keys never reach the browser, and AI writes **data (JSON)**, never code that gets executed.

## Install

You don't even need Python: the installer **installs Python for you if it is missing** (3.9 or newer) and **updates it** on every run, together with its tooling (`pip`, `setuptools`, `wheel`, `venv`). The **same command installs and updates** everything (your data in `~/.asta` is never touched).

**Linux & macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/KMC1525/ASTA/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/KMC1525/ASTA/main/install.ps1 | iex
```

The Windows installer works on the Windows PowerShell 5.1 that ships with Windows as well as on PowerShell 7. The `asta` command is added to your `PATH` and works right away in the same terminal when you use the command above (other already-open terminals need to be reopened); if it is still not recognized, run it by its full path, which the installer prints (`%LOCALAPPDATA%\ASTA\app\venv\Scripts\asta.exe`). If it ever stops with an error, re-run the same command and open an issue with the text it printed.

Then, in any terminal (**running `asta` also updates/installs everything first** — Python, ASTA, libraries and pre-installed models — like the install command: when a new version is out and, otherwise, at most once every 24 h; offline it just opens; skip with `asta --no-update` or `ASTA_NO_UPDATE=1`; `ASTA_UPDATE_EVERY=<hours>` changes the interval):

```bash
asta
```

The WebUI opens at `http://localhost:8787`. To update, run the install command again (or `asta update`).

> **After updating, restart ASTA** (close it and run `asta` again) and reload the page (Ctrl+F5). A page left open across an update can show *"Could not load this screen"*: ASTA reloads it once by itself, and if that is not enough it explains what to do; the sidebar also warns when a newer version is installed than the one running.
>
> If a screen still fails to load, an **ad/tracker-blocking browser extension** (uBlock Origin, AdBlock, Firefox tracking protection…) may be blocking one of ASTA's files — turn it off for `localhost` and reload. (ASTA's own files no longer use names that these blockers filter, such as `quant.js`, but a strict list can still block something.)

**Installing and updating covers three layers:** (1) **Python** and its tools — installed or upgraded through your system's package manager (`apt`, `dnf`/`yum`, `pacman`, `zypper`, `apk` or Homebrew on Linux and macOS; `winget` on Windows), which may ask for your password (`sudo`); if the new Python is a newer version, ASTA's private environment is rebuilt for it automatically; (2) **ASTA** itself; (3) **all of ASTA's libraries**, described below. Set `ASTA_PYTHON=keep` to never touch the system Python.

**Nothing already installed is installed again.** The installer, `asta update` and `asta libs` detect what is already there and only update it when needed: Python is only upgraded if the package manager has a newer version; the private environment is reused; ASTA itself is **not downloaded again** when the installed version already matches the published one (`ASTA_FORCE=1` or `asta update --force` reinstalls anyway); libraries already installed are only checked and upgraded if a newer version exists (only missing ones are installed); already-downloaded models are skipped.

**Installing and updating also install and update all of ASTA's libraries** — the optional ones that unlock extra features (more accurate PDF reading, local image/video/sound/voice models for the Canvas, embedded GGUF language models). The first install can take a while and download several GB (PyTorch for the Canvas models); if you only want the lightweight core, set `ASTA_EXTRAS=none`. A library that fails to install (for example `llama-cpp-python` without a C++ compiler) only produces a warning: ASTA still works, and you can retry with `asta libs`.

<details>
<summary>Install options</summary>

| Variable | Effect |
|---|---|
| `ASTA_EXTRAS=all` (default) | installs/updates **every** library: `docs` + `media` + `local` |
| `ASTA_EXTRAS=none` | installs only ASTA itself (no dependencies at all) |
| `ASTA_EXTRAS=docs,media,local` | pick libraries: `docs` = more accurate PDF extraction (`pypdf`) · `media` = local image/video/sound/voice models for the Canvas (`torch`, `diffusers`, `transformers`…) · `local` = embedded GGUF models: text, image and video (`llama-cpp-python`, `stable-diffusion-cpp-python`) |
| `ASTA_MODELS` (unset) | the installer **asks you in the terminal (yes/no)** before downloading the **pre-installed local models** (see below); `all`, `text` or `image` downloads without asking, `none` skips them |
| `ASTA_PYTHON=auto` (default) | installs Python if missing and upgrades it (with `pip`, `setuptools`, `wheel`, `venv`) via the system package manager |
| `ASTA_PYTHON=keep` | never installs or upgrades the system Python (ASTA's own `pip`/`setuptools`/`wheel` are still kept current) |
| `ASTA_FORCE=1` | reinstall ASTA even if the installed version is already the latest published one |
| `ASTA_RUST=yes` (default) | **installs Rust for you** (rustup, in your user folder, no sudo) if missing, updates it and compiles ASTA's fast core; `no` skips it, `ask` asks first |
| `ASTA_LANG=pt\|en` | language of the terminal texts (default: your computer's language) |
| `ASTA_SOURCE=<url\|folder>` | install from another source (fork, branch, local folder) |
| `ASTA_APP_DIR`, `ASTA_BIN_DIR` | where the program and the `asta` command live |

Manual install: `pip install "asta @ https://github.com/KMC1525/ASTA/archive/refs/heads/main.zip"`.
**`asta folder`** opens ASTA's local data folder (`~/.asta`: chats, projects, media, models, settings) in your file manager (`--print` only prints the path, `--app` opens the installed program folder instead).
Command options: `asta --port 9000 --no-browser --home /other/folder` · `asta update` upgrades **Python, ASTA and all its libraries** by running the official installer (`--no-python` keeps the system Python, `--core` updates only ASTA and `pip`/`setuptools`/`wheel`, `--extras docs,media` chooses libraries; an ASTA installed by hand with `pip` updates everything except the system Python) · `asta libs` installs/upgrades just the libraries, `sh install.sh --python-only` just Python and its tools · `asta doctor` prints a diagnosis of your hardware and optional components. Libraries are upgraded together with their own dependencies, so the Canvas and local-model features stay current.

</details>

**Optional tools.** [`ffmpeg`](https://ffmpeg.org) unlocks video analysis, the Canvas video Editor export, the **Studio** (generation, automatic editing and export) and the offline Demo video. Everything else works without it.

## Terminal commands

| Command | What it does |
|---|---|
| `asta` | opens the WebUI (it also updates/installs everything first when due; skip with `--no-update`) |
| **`asta update`** | updates **Python, ASTA, all its libraries and Rust** to the latest versions by running the official installer (`--no-python`, `--core`, `--extras docs,media`, `--rust yes\|no`, `--force`) |
| **`asta folder`** | **opens ASTA's local data folder** (`~/.asta`: chats, projects, media, models, settings) in your file manager (`--print` only prints the path, `--app` opens the installed program folder) |
| `asta libs` | installs/updates the optional libraries (`docs`, `media`, `local`) |
| `asta models list\|install` | the pre-installed local models |
| `asta native setup` | installs/updates Rust and recompiles the fast core (also `install`, `update`, `build`, `status`) |
| `asta doctor` | environment diagnostics (hardware, Python, Rust, ffmpeg, providers, terminal language) |
| `asta version` · `asta --help` | version · all options |

The terminal texts follow your computer's language (Portuguese or English; `ASTA_LANG=pt\|en` forces one).

## Getting started

1. **Try it with zero setup.** The default provider is **Demo** (offline, rule-based). Open **Chat**, ask anything and press **Run** — or turn on a creation tool (✦ *Create*), describe what you want and press **Run** to watch the agents work and get **Play**, **Chat** or **Open**.
2. **Plug in a real AI** in **Configuration → Providers**: paste a key (Claude, ChatGPT, Grok, Gemini…), *Load models*, pick one and *Test*. Or use **Ollama / LM Studio** (free, local).
3. **For the Canvas**, choose image/video/sound/voice providers in **Configuration → Media** (OpenAI, ElevenLabs, Google, Stability AI, Replicate, Hugging Face, a local Stable Diffusion WebUI, or local Hugging Face models). Without any, the Demo provider lets you test whole flows offline.
4. Come back to the **Library** at any time and press *Update* to evolve the same project.

## Chat — the main screen

**Chat** is a clean, general-purpose assistant: ask for a cake recipe, study a topic, rewrite a text, debug code. The screen is just a text box with **attachments on the left**, the **model** button and **Run** on the right.

- **Model picker** (next to Run): switch provider *and* model in one click — Claude, ChatGPT, Grok, Gemini, OpenRouter, LM Studio, Ollama, the embedded GGUF model… The choice is saved and applies to the whole app.
- **Markdown replies, streamed live** (lists, tables, code blocks with *Copy*), a **Stop** button (Run turns into Stop, or press **Esc**; a half answer is never saved; the unanswered question gets an **Answer** button), **Reply again**, copy, and a **History** of conversations (the last one reopens by itself; *New chat* starts a blank one). Attach images, PDFs, spreadsheets, audio, video… — they are read and used as context.
- **Activator for the heavy stuff.** The multi-agent pipelines (3D world, avatar, 2D game, Canvas) **never start on their own**. Chat only talks; if you ask it to create something it *suggests* the matching tool, and nothing runs until **you** turn the tool on (✦ *Create* → pick one, or press the suggestion button) and press **Run**. Turn it off (×) to go back to plain chatting. The creation options (genre, count, relationship, SFW/NSFW, perspective…) appear only while the tool is on.
- **Web search, built in (🌐 Web button).** Turn it on and the Chat searches the web for your question, reads the first pages and gives the model numbered sources; the answer cites them as [1], [2] and shows clickable **Sources** chips (kept in the history). It works with **any model, local ones included**, and with **any prompt**: with a creation tool on, the prompt is searched too and the references travel with it. Engines: DuckDuckGo → Wikipedia by default (no key), Brave Search, Tavily or your own SearXNG. Follow-up questions ("and the price?") get a model-written search query. Result pages are read only from public hosts (no localhost/private networks, redirects included) and treated as untrusted text. *Configuration → Chat* has a **Test search** button.
- **Tabs.** Keep several conversations open at once, each in its own **tab**; an answer keeps streaming **in the background** while you use another tab. Open a new tab with **Alt+N** or **Ctrl+J**, the command palette (*Ctrl+K → New chat tab*, works from any screen), the **New tab** button / **+**, `Ctrl+J`, or by typing **`/new`** in the message box; **Alt+W** closes the front tab (closing never deletes the conversation — it stays in History). Tabs keep their own drafts and come back after a reload.
- **Split view (Firefox style).** Right-click a tab → *Split the view with…* to show two conversations side by side in the same screen, each pane with its own scroll and live streaming; the text box goes to the focused pane. The tab strip also slides sideways (mouse wheel, drag or touchpad) when you have many tabs.
- **Sources panel (right side of the conversation).** Every searched source is listed there **in the order the search returned them**, grouped by search (Search 1, 2… with the query used), each with its number, title (opens in a new tab), site, snippet and a *read* badge when the page was read in full. It opens by itself when a search arrives (a drawer on narrow screens), fills in live, and has a **Sources (n)** button in the top bar. The `[1]`, `[2]` marks in the answer are buttons that jump to and highlight the source.
- **Thinking time** (next to the model name, only when the chosen model supports it): **Off · Slow · Medium · High · Extra high · Ultra**. Claude gets extended-thinking budgets (1K → 32K tokens, on top of the answer size); OpenAI reasoning models (o-series, GPT-5), Gemini 2.5+, gpt-oss (LM Studio/Ollama) and reasoning models on OpenRouter get `reasoning_effort` (Extra high and Ultra use the provider's highest effort with more token headroom). Models without the feature show no selector and nothing is sent; if a model refuses the mode, ASTA retries without it and says so.
- **Chat settings** (*Configuration → Chat*): **answer size** (tokens), **context window** (what ASTA sends — oldest messages leave first), remembered turns, creativity, **custom instructions**, default thinking level and the web-search options.
- Without a provider the Demo engine is used and Chat says so honestly — it cannot really answer questions. Pick a model to fix it.

## The creation tools

### 🌍 3D worlds

Describe a world; ASTA delivers a **ZIP with a playable 3D game** (HTML + CSS + JS + three.js) that opens straight from a file.

- **Every character/NPC is an AI agent**: talk by **text** (click the character) or **voice**, in any language. They remember what you said, follow you, flee, dance… and, with autonomy on, decide for themselves.
- Pipeline: **Analyst → Planner → Characters → Architect → Sound & UX → Reviewer → Packager**.
- The agents output a **JSON world spec**; a **deterministic 3D engine** renders it. Every model output is validated (types, limits, hardware budget) and an agent that answers garbage is replaced by a rule-based generator.
- **Persistent**: position, time, memories and conversations are saved and restored. **Any hardware**: the game measures the machine and adapts resolution, shadows, vegetation and distance in real time.
- Controls: **WASD** move · **Shift** run · **Space** jump · **V** toggle 1st/3rd person · **E** (or click) talk · **M** minimap · **Esc** release the mouse. Touch controls on phones.

<details>
<summary>The generated ZIP</summary>

```
Game.html          open in the browser (works from a file, no server needed)
README.md          how to play + world summary
CHANGELOG.md       version history of this world
code/              3D engine (three.js r159), world data, NPC AI, audio
chars/             one .json per character (name, tags, system prompt, voice) + chars.js
sound/             sound.json (procedural ambience and music) + attached tracks
prompts/           your prompt, attachments and every agent's log (the "why" of everything)
ui/ux/             theme and in-game interface config
```

</details>

### 🙂 Avatars

Companions in the spirit of Janitor and SillyTavern, built into ASTA.

- **Complete avatar cards**: name, relationship (friend, **girlfriend, boyfriend, wife, husband**, partner, companion, mentor, custom — each romantic or married relationship can be **SFW or NSFW**; the relationship also suggests the gender when you leave it empty), age, gender, personality, appearance, scenario, first message, speech examples, optional full system prompt, group talkativeness, **voice** (pitch/rate/voice) and a **portrait** — upload one or use the drawn face that changes with the avatar's mood.
- **Create them with AI** from a text description, **images, or any attached file** (documents, spreadsheets, chat logs…): one avatar or **several at once** ("three college friends: Theo, Mia and Caio").
- **Single chat** (you ↔ one avatar) and **group chat** (you ↔ up to 8 avatars). In a group, a *director* decides who answers (mentions, talkativeness) and, with **free chat** on, the avatars **keep talking to each other on their own**, like a real group chat, until they pause and wait for you.
- **Text and voice**: streaming replies, speak replies out loud, dictate with the microphone, or hands-free **voice conversation** — browser speech for free, or any OpenAI-compatible STT/TTS server (cloud or local).
- **Memory**: short-term history plus long-term memories the avatar writes down by itself (you can read them and clear them).
- **SFW or NSFW per avatar.** One fixed rule that no setting changes: avatars are adults. If a card says (in the age field or in any text) that the character is a minor, ASTA never "ages them up": they stay strictly SFW and platonic — a friend, never a partner.
- **Any kind of character — real or fictional.** Pick the *character type*: **fictional** (original or from a book, film, game, anime, myth…) can be SFW or NSFW; a **real person** (living or historical, famous or not, or the one in a photo) can be created too, but is **always SFW**: ASTA does not create sexual content about real people (they did not consent), and portrays them only as a respectful *fictional interpretation* — never as the real person, with no invented private facts or quotes. In the creation box, *Type: automatic* lets the analyst decide; your explicit choice always wins. Minors stay SFW and platonic in every case.
- **A conversation you control.** *Stop* cuts a reply in the middle (nothing half-written is saved); every message has **copy, edit and delete**, and the last reply has **Reply again** (it replaces the old one); long histories do not yank you down while you read old messages (a *New messages* button appears instead); an unsent draft comes back when you return to the chat; in *Memories* you can **teach the avatar something** and **forget one memory** at a time; the conversation title follows the avatar's name if you rename it.
- **Avatars answer with real AI.** Chat replies come from an AI model — cloud (Anthropic, OpenAI, Gemini…) or local (Ollama, LM Studio, the embedded GGUF model, the pre-installed Qwen) — never from canned lines when an AI is available. *Configuration → Providers → Who does what → Characters* is **Automatic** by default: it uses your generation provider if it is usable (key or model set), otherwise the installed local text model (needs `llama-cpp-python`: `asta libs --extras local`). Avatar *creation* and the system-prompt pipeline use the same rule. **Demo** (pre-programmed replies, no AI) is used only when nothing else exists — and then the chat shows a *Demo mode* banner with the reason and a *Set up AI* button; with an AI, a line shows which model is answering. Pick a specific provider in the role to force it.
- **LM Studio for the avatars (and everything else).** Start the server in LM Studio (*Developer → Start Server*, or `lms server start`) and load a model: ASTA **detects it by itself** at `http://127.0.0.1:1234` (or the URL you set) — with the *Characters* role on **Automatic**, avatars already chat through it, ahead of the embedded GGUF model, no configuration needed. In *Configuration → Providers → LM Studio* press detect: you see whether the server is running, the chat models (loaded `●` first, installed `○`, vision `👁`; embedding models are hidden), pick one with a click and use *Use for avatars* / *Use for generation*. Without a chosen model ASTA uses the one loaded in LM Studio; vision comes from the model type (`vlm`); an optional API key and a server on another machine work too; if the server is off, the error says how to start it. Models that write their reasoning in `<think>…</think>` (Qwen3, DeepSeek R1…) have it hidden in the chat. `asta doctor` also reports LM Studio.
- **System-prompt pipeline (Analyze → Generate → Review → Deliver).** In the avatar editor, *Generate the system prompt with AI* runs 4 stages: (1) **Analyze** — who the character is (real or fictional, age, way of speaking, relationship, limits, content scope); (2) **Generate** — writes the system prompt; (3) **Review** — checks consistency, voice, language, length and the fixed rules, sending it back for one fix round if needed; (4) **Deliver** — cleans the text and applies the safety rules *in code* (a real person or a minor is forced to SFW whatever the model says). Works offline in Demo mode (rule-based), **runs automatically on every avatar you create** (a *System prompts* step after the Reviewer; skip it with `prompt_pipeline: false` in `POST /api/avatars/generate`) and is also available as `POST /api/avatars/system-prompt` (`avatar_id` or `draft`, `instructions`, `content`, `character_type`, `apply`).
- **Photos work with local vision models too.** Images are sent with their real type; local servers (LM Studio, Ollama, llama.cpp) get PNG/JPEG only (GIF/WebP are converted with `ffmpeg`), and if a server still refuses images ASTA retries with text only and shows a warning instead of failing. For ASTA to *see* the photo the loaded model must support vision (a "VLM": Qwen-VL, Gemma 3, LLaVA…).
- **Create from a photo or art**: turn on *Photo/art as base*, attach one or more images and send — with the image alone, or adding a text prompt and other attachments (documents, chat logs…). Pick *one avatar per image* or *one person built from all the images*. The image defines the look (hair, eyes, clothes, art style — described by your vision model, or by its dominant colors offline) and becomes the portrait; the text only adds name, personality and backstory. ASTA never identifies a real person from a face: it uses a name only if you give one (or the file name suggests it). **Photos of real people — and images that can't be identified as art — always stay SFW; NSFW only applies to art of fictional characters**, and an image that appears to show a minor follows the minors rule above.
- **Import and export** Character Card V2 (JSON and PNG), so your cards work in other tools too.

### 🎮 2D games

Describe a game (or attach scripts, images, documents) and a team of agents writes a **complete, playable game as data**, packaged as a ZIP that runs from a file or straight from ASTA — with the engine for the genre you asked for:

| Genre | What the engine does |
|---|---|
| **Visual novel** (Ren'Py style) | Branching story with choices, flags and several endings; auto mode, skip read text, history, save/load; expressive procedural characters and scenes. |
| **RPG** (RPG Maker style) | Tile maps, event pages with conditions and commands, dialogue, items, shops, a menu, saving and turn-based battles. |
| **Platformer** | Physics with coyote time and jump buffering, enemies, hazards, checkpoints, parallax; levels are validated, and the built-in generator's levels are **verified completable by a bot**. |
| **Side scroller** | Shooter or endless runner with waves, bosses and power-ups. |
| **Point & click** | Rooms with clickable hotspots, verbs (look, take, use, talk), inventory, use-item and dialogue puzzles. |

- The AI writes a **validated JSON spec** (`asta.game2d.v1`); conditions use a safe grammar with no `eval`; the engines are plain, auditable JS. Pipeline: **Attachments → Game analyst → Game designer → Reviewer → Packager**.
- All art is **procedural vector graphics** and all audio is synthesized, so games are tiny and need no assets. Touch controls included.
- Update the same game as many times as you like; old games can be rebuilt with the latest engine.

### 🧩 Canvas

A node flow to generate and edit **images, videos, sounds and voices**, kept deliberately simple: every node has one output, typed inputs, and a result you can see right on the node. Create **as many canvases as you want**, one per project.

| Node | What it does |
|---|---|
| **Text** · **AI text** | Write prompts, scripts and speech; let the active text model rewrite or expand them. |
| **Media** | Your own images, videos and audio. Drag files onto the canvas to create one. |
| **Image** | Generate, or **edit** images connected as references. |
| **Video** | From text, or animating a start image. |
| **Sound** | Sound effects or music. |
| **Voice** | Text to speech. |
| **Transcribe** | Audio or video to text, which can feed other nodes. |
| **Style Prompt** | A style *system prompt* that applies to the **whole project**. |
| **Style Folder** | Drop many images, videos and audios as **style reference** for the **whole project**; ASTA describes them with your vision model (or reads their dominant colors) and feeds that to every generator. |
| **Editor** | A **video editor** that supports every other node: tracks, a media bin, live preview, split/trim/move, fades, opacity, position, captions and **MP4 export** (needs `ffmpeg`). |

- **Smart execution**: nodes run in dependency order, results are cached by a hash of parameters, inputs, styles and model, and only what changed is regenerated. "Regenerate" gives you a new variation. A failed node never breaks the rest of the flow.
- **Style nodes** are global by default; turn *global* off to apply them only where connected, or tick *Ignore global styles* on a node.
- **Templates** to start fast: Text → Image, Text → Image → Video, With project style, and a full scene (script → image → video + narration + sound, assembled in the Editor).
- **Every file is yours**: a canvas is a folder (`canvas.json` + `assets/`) you can download as a ZIP.

## Studio — AI audiovisual videos, scene by scene

*Studio* (right below Canvas) generates, edits and reviews videos with a **multi-agent, multi-step pipeline**. It uses your text providers and your media providers (image, video, sound, voice — Demo works offline), and needs `ffmpeg`.

- **Duration types:** **Shorts/Reels** (up to 2 min), **Short film** (up to 30 min), **Feature** (up to 90 min) and **Custom** (up to 6 h). The duration is fully adjustable (minutes + seconds, slider, shortcuts).
- **Styles:** Realistic, Cartoon, Anime or **Custom** (you describe the look). **Projects:** **Single** (one video) or **Series** (episodes that share a "bible" — characters, world, tone — and recaps of earlier episodes).
- **Generation, one scene at a time:** a Showrunner writes the script (in acts for long videos) and **each scene** goes through *receive → analyze → generate → review → deliver* before the next one starts. Delivered scenes are saved: cancel and **continue**, or **redo a single scene**. The live scene board shows the five steps of each scene.
- **Automatic editing:** attach several videos/images/audio files + a prompt and pick an **editing style** — **Gameplay**, **Documentary**, **Phonk edit**, **Trailer**, **Vlog**, **Tutorial**, **Music video**, **Photo slideshow**. An Analyst, a Director and a Reviewer build the cuts (volume peaks, scene changes, silences, beat grid) and you refine them on the timeline.
- **Kdenlive-style timeline:** media bin, preview monitor, inspector and tracks with **cut** (`S` / razor `C`), **join** (`J`), **mute** (`M`), delete / ripple delete, duplicate, trim, **magnet**, ripple mode, text, markers, speed, volume, fades, color filters, lock/hide/mute tracks, **undo/redo**, zoom and autosave.
- **Export:** **Full** (MP4), **Video only** or **Audio only** (M4A/MP3/WAV) at 480p/720p/1080p.
- Honest limits: quality depends on your media providers (Demo is synthetic); a 90-minute feature means hundreds of shots (hours of work, and cost with paid providers); the browser preview approximates filters with CSS — the ffmpeg export is the reference.

## Rebuild — rebuild an existing game in plain HTML/CSS/JS

*Home → Rebuild.* Attach a game you already have (a **ZIP** or the loose files) and ASTA rebuilds its **structure** as a new game that runs in any browser with no engine, no installer and no external libraries. **This version supports only two engines:**

| Engine | Versions | What is read |
|---|---|---|
| **Ren'Py** | `.rpy` scripts | labels, dialogue, menus/choices, jumps/calls, variables and `if`s |
| **RPG Maker** | **2000, 2003, XP, VX, VX Ace, MV, MZ** | maps and their size, events (pages, conditions, messages, choices, switches/variables, transfers, shops, battles), actors, items, enemies, troops, common events |

The rebuilt game keeps the **same structure as the original** (same maps/labels, same event flow, same choices and conditions). It opens in ASTA's own 2D engines (RPG Maker → RPG engine, Ren'Py → visual novel) and exports as a ZIP like any other game.

- **Only the structure is rebuilt.** The original art, audio, fonts and other assets are **never read or copied**; the rebuilt game uses ASTA's own procedural visuals/sound. Encrypted or compiled packages (`.rgss*a`, `.rpa`, `.rpyc`, MV/MZ-encrypted assets) cannot be read — extract the plain project first.
- **Legal notice, shown at the end of every rebuild** (and written into the ZIP as `LEGAL-NOTICE.md`): do not publish the result on Steam or any other platform; it is for **personal use only**; any legal problem is the **responsibility of whoever rebuilds**, never of ASTA's creator or contributors; and *even with this notice, we will not stop you from rebuilding — but be aware of what you are doing.*
- **Multi-agent text review (optional, built for small local models).** After the deterministic conversion, a team of short, well-supervised agents proofreads **only the game's text**: a **Profiler** (one tiny call: tone + readable names for events/maps called `EV012`/`Map003`), a **Polisher** (batches of at most 6 lines: typos, case, punctuation, stray symbols — never translates or adds sentences) and an **Auditor** (second opinion that undoes changes that altered the meaning). Every returned line must pass validators (placeholders, numbers, length, word similarity) or the original stays; a failed batch is retried line by line; the number of model calls is capped; and a **structural lock** compares the game's structure (without texts) before and after — if anything but text changed, everything is reverted. Engine leftovers (`\C[2]`, `{w}`, broken accents) are cleaned without AI. Toggle it with *Proofread the text with AI* in the composer; without an AI provider only the automatic cleanup runs. A model that fails or goes offline never breaks the rebuild.
- Tested with synthetic projects for every engine; real commercial projects vary, so expect to touch up the result.

## Performance — Rust core and Light mode

ASTA's backend is still Python, now with an optional **Rust core** and a **performance mode** for modest PCs.

- **Rust core (`asta_core`).** A small, dependency-free Rust library (std only, no crates, loaded through `ctypes`) that does the heavy number crunching — currently the **audio synthesis** of the Canvas (music, effects, voice → PCM). It works on shared buffers instead of one Python object per sample: on our benchmark a 20-second music track went from ~15 s to ~0.05 s. **It is optional:** every function has a pure-Python twin, so without Rust nothing breaks. Enable it with **`asta native setup`** — it **installs Rust for you** (rustup, minimal profile, in your user folder, no sudo) if it is missing, **updates** it if it is already there and **recompiles** the core. The installers (`install.sh`, `install.ps1`) and `asta update` offer the same step: by default they do it **automatically**, like the other code and libraries (no question; `ASTA_RUST=ask` asks first, `ASTA_RUST=no` skips it). Also: `asta native install | update | build | status`, `asta update --rust yes|no`. The C toolchain is needed to compile (Linux: `build-essential`; macOS: `xcode-select --install`; Windows: Visual Studio Build Tools) — ASTA tells you when it is missing. `asta native` / `asta doctor` show whether it is active; `ASTA_NO_NATIVE=1` turns it off.
- **Performance mode** (*Configuration → System → Performance*): **Auto** (by hardware tier), **Light**, **Balanced** or **Maximum**. Light mode caps the local model's context window (a value you set by hand always wins), loads weights with `mmap` and a smaller batch, uses **flash attention and an 8-bit KV cache** (about half the attention-cache memory) when the llama-cpp build supports it, **unloads idle models** (configurable) and, for local image/video models, enables attention/VAE slicing and CPU offload — which lowers **VRAM** peaks. Options an older llama-cpp-python does not know are skipped automatically.
- Honest limits: the Rust speed-up is measured on audio synthesis only; the RAM/VRAM savings of Light mode come from documented llama.cpp/diffusers features and were not benchmarked on real GPUs or models here.
- **Terminal language.** Everything the terminal prints — `asta`, `asta update`, `asta doctor` and the installers — is shown in **your computer's language** (Portuguese or English; any other language falls back to English). `ASTA_LANG=pt|en` forces one.

## The interface

| Section | What it is for |
|---|---|
| **Chat** | The main screen: general-purpose chat with a model picker, attachments and history — and, when you turn a creation tool on, the prompt box for 3D worlds, avatars, 2D games and Canvas with the live view of the agents. |
| **Worlds** | Everything about 3D worlds in three tabs: **Worlds** (customize generated worlds: biome, weather, time, day/night cycle, NPCs, audio, interface, quality — each save is a new version **without spending AI**), **Characters** (cards for NPCs and the player: name, tags, system prompt, voice, appearance; import/export JSON and PNG cards, Character Card V2/V3) and **Worldbuilding** (general rules for worlds — setting, tone, conventions — also stored as cards). |
| **Avatars** | Your avatar cards, plus single and group conversations. |
| **2D games** | Your games: play, download, update. |
| **Canvas** | Your canvases and the node editor. |
| **Studio** | Your video projects (single or series): generate scene by scene, automatic editing, the timeline editor and export. |
| **Rebuild** | Rebuild Ren'Py / RPG Maker games and see the ones you rebuilt. |
| **Library** | Everything you created as updatable projects, plus the **local AI models you installed**, with search and automatic + custom tags. Press *Select* to pick several items and delete them at once; models can be deleted one at a time or in bulk. |
| **Configuration** | Providers, media providers, **Chat** (answer size, context window, thinking time, web search), generation, avatars and games, voice, local Hugging Face models, **appearance** and system. |

### Make it yours (Configuration → Appearance)

- **Theme:** dark (default), **light** or **automatic** (follows your system, live). The look is applied before the first frame, so it never flashes. The Canvas node graph and the video editor stay dark on purpose, like media editors.
- **Accent color:** 6 presets or any color; buttons, selections and your chat bubble follow it (text contrast is picked automatically).
- **Comfort:** interface size 90–150%, comfortable or compact density, system/serif/monospace font, avatar chat text size, and **reduce animations** (also respects your system setting).
- **Usage:** interface language, **send with Enter or Ctrl+Enter** (chat and creation box), **start screen** (Chat, a specific screen or *the last one I used*), keyboard shortcuts on/off.
- **Sidebar:** hide the screens you do not use (*Chat* and *Configuration* always stay; hidden ones remain reachable by search).
- **Command palette — `Ctrl/⌘ + K`:** type to jump to any screen or Configuration tab, chat with or edit an avatar, open a project or canvas, or run an action (new avatar, toggle theme, export settings…). Shortcuts: `Alt+1…7` screens, `Alt+B` sidebar, `Alt+T` theme, `Ctrl+J`/`Alt+N` new Chat tab, `Alt+W` close it, `?` help.
- **Backup:** *Export settings* (a JSON **without API keys or tokens**), *Import* on another computer, and *Reset appearance defaults* (keys, avatars and projects are never touched).
- **First run:** a short welcome lets you pick theme, color and language and shows whether an AI is ready — only on a fresh install, never for people who already use ASTA.
- Accessibility: visible keyboard focus, a *skip to content* link, accessible names on icon buttons, dialogs announced as such, and page titles per screen.

## How generation works

```
 prompt + attachments ──► Analyst ──► Planner / Designer ──► Builders ──► Reviewer ──► Package
 (text, images, video,    understands  plans the project     create the   critiques,    ZIP / card /
  audio, docs, sheets…)   the request  and its budget        content      asks fixes    library entry
```

- All pipelines share one runner: JSON repair, retries, per-agent rule-based fallback and live events (SSE). The **Demo** provider recognizes every agent, so you can watch complete pipelines offline.
- **Attachments** become context: text/code, `.docx/.odt/.pdf`, `.xlsx/.ods/.csv`, `.pptx/.odp`, images (vision), audio (transcription through your configured STT server) and video (frames and audio via `ffmpeg`, if installed).
- **Updates**: the same project gains version *N+1* (stable ids, so memories are preserved), with history in the project's own `CHANGELOG.md`.

## AI providers

**Text models** (worlds, avatars, games, AI-text nodes):

| Provider | Type | Notes |
|---|---|---|
| Claude (Anthropic) | cloud | native API, with vision |
| ChatGPT (OpenAI) · Grok (xAI) · Gemini (Google) · OpenRouter | cloud | OpenAI-compatible API |
| Hugging Face Inference | cloud | `router.huggingface.co` |
| **LM Studio** | **local** | free; detected automatically (server + loaded model), see Avatars |
| Ollama · llama.cpp server · vLLM · any compatible endpoint | **local** | free; pick the model from the list |
| Hugging Face GGUF (embedded) | **local** | downloads the `.gguf` straight from Hugging Face and runs inside ASTA (`pip install "asta[local]"`) |
| Demo | offline | rule-based generator to test everything without a key |

**Robustness.** Local servers (Ollama, LM Studio, llama.cpp, anything on `localhost` or your home network) are always reached directly — never through the system proxy (`HTTP_PROXY`); an address typed as `localhost:11434` works (ASTA adds `http://` and `/v1`); overloaded cloud servers (429/503/529) are retried with `Retry-After` (an exhausted quota is not retried); long avatar conversations are trimmed to fit a local model's context window instead of failing; and a model that answers nothing — or spends the whole token limit "thinking" — gets a clear warning in the chat instead of silence.

You choose one model **to generate** (the most capable) and another **for the characters and avatars** (a fast, cheap one is enough).

**Local models and quantization.** *Configuration → Local models* searches Hugging Face for GGUF models. Each repository offers the same model in several **quantizations** (Q2_K … Q8_0, F16): fewer bits mean a smaller, faster file that needs less RAM, but lower quality. ASTA reads the quantization of every file, labels its quality, marks which ones fit your RAM, **recommends** a balanced one (usually Q4_K_M) and makes you **pick the one to download**: nothing is preselected and the download only starts after you choose and confirm, with progress, resume and a disk-space check. Models split into several parts (`-00001-of-00003.gguf`) are downloaded together and shown as one entry, and the quantization of each downloaded model is shown in the *Downloaded* list.

**Media models** (Canvas), configured per type in *Configuration → Media* and overridable on every node:

| Provider | Image | Video | Sound | Voice | Transcription | Notes |
|---|:-:|:-:|:-:|:-:|:-:|---|
| OpenAI | ✅ | ✅ | | ✅ | ✅ | gpt-image (with edits and references), TTS, Whisper, Sora (experimental) |
| OpenAI-compatible servers (xAI, Together, LocalAI, Kokoro, faster-whisper…) | ✅ | | | ✅ | ✅ | any `/images`, `/audio/speech`, `/audio/transcriptions` endpoint |
| ElevenLabs | | | ✅ | ✅ | ✅ | realistic voices, sound effects, music (experimental) |
| Google (Gemini / Veo) | ✅ | ✅ | | | | same key as Gemini; Veo is experimental |
| Stability AI | ✅ | | | | | core, ultra, SD 3.5 |
| Replicate | ✅ | ✅ | ✅ | ✅ | | thousands of models; ASTA reads each model's schema and only sends what it accepts |
| Hugging Face Inference | ✅ | | ✅ | ✅ | ✅ | same token as the text provider |
| **Stable Diffusion WebUI** (local) | ✅ | | | | | AUTOMATIC1111 or Forge started with `--api` |
| **Hugging Face local** (embedded) | ✅ | ✅ | ✅ | ✅ | ✅ | diffusers + transformers inside ASTA (`pip install "asta[media]"`); video needs a GPU |
| **GGUF local** (embedded) | ✅ | ✅ | | | | quantized GGUF image/video models via stable-diffusion.cpp (`pip install "asta[local]"`); video depends on the library version |
| **Demo** (offline) | ✅ | ✅ | ✅ | ✅ | | procedural images, synthesized sound, babble "voice", Ken Burns video (needs `ffmpeg`) |

**Pre-installed models.** ASTA comes with two local models ready to run on your computer, offered by the installer (and by `asta update`) with their quantization already set:

| Type | Model | Quantization | Download |
|---|---|---|---|
| Text | [`empero-ai/Qwen3.8-2B-Distill`](https://huggingface.co/empero-ai/Qwen3.8-2B-Distill) (GGUF: `Qwen3.8-2B-Distill-GGUF`) | **Q8_0** | ~1.9 GB |
| Image | [`Tongyi-MAI/Z-Image`](https://huggingface.co/Tongyi-MAI/Z-Image) (GGUF: `unsloth/Z-Image-GGUF`) | **Q4_K_M** | ~6.2 GB (model + VAE + Qwen3-4B text encoder) |

They are the only two for now. Install them from *Configuration → Local models → Pre-installed models* with one click, or with `asta models install` (`asta models list` shows the status); the installer and `asta update` **ask you in the terminal (yes/no)** before downloading them (answering *no* is remembered and not asked again; `asta models install` downloads whenever you want; `ASTA_MODELS=all|text|image` answers in advance and `ASTA_MODELS=none` skips them; without a terminal to ask, nothing is downloaded). When the model's library is installed (`asta[local]`) and you are still on the Demo provider, ASTA makes them the default text model / Canvas image provider; if you already chose another provider, your choice is kept. Already-downloaded files are never downloaded again.

**Context window.** The pre-installed text model starts with a **32K-token (32,768) context window**. You can change it any time in *Configuration → Providers → Hugging Face GGUF (embedded) → Context window (tokens)* (leave it empty or press *Use automatic* to go back to the default). Other local text models use 2K/4K/8K depending on your hardware unless you set a value. Bigger windows use more RAM; changing the value reloads the model.

**GGUF models by type.** The *Local models* tab is split into **Text, Image, Video, Sound and music, Voice and Other**. Each type has its own Hugging Face search (filtered by the repository's task), its own folder (`models/`, `models/image`, `models/video`, …), the same quantization picker and its own *Downloaded* list. Text models run ASTA itself (`llama.cpp`); **Image and Video GGUF models (FLUX, Stable Diffusion, Wan…) run in the Canvas through `stable-diffusion.cpp`** (provider *GGUF local*, `pip install "asta[local]"`): press *Use in the Canvas* on a downloaded file. Extra load options (VAE, text encoders…) go in the node's *Advanced → extra parameters* (`{"load": {"diffusion_model_path": "@model", "vae_path": "ae.safetensors"}}`). For **Sound, Voice and Other** ASTA currently only downloads and organizes the files — there is no built-in engine to run them yet.

**Local Canvas models also ask first.** The embedded Hugging Face provider never downloads anything silently: in *Configuration → Media* you pick the model for each type and then its **precision (quantization)** — fp32 (original, works on CPU), fp16 or bf16 (half the size, meant for a graphics card) — seeing the download size of each before anything is fetched. Only the files of the chosen precision are downloaded, and only models you downloaded are loaded.

A node's *Advanced* section takes a free **JSON of extra parameters** merged into the provider request, so any model-specific option is reachable.

> The adapters for third-party services follow each service's public documentation and are tested against simulated servers; the Demo and local paths are tested end to end. If a provider changes its API, please open an issue.

## Free content

ASTA **adds no content filters**: the default mode follows your prompt and your worldbuilding, including adult (NSFW) themes when they fit, without lectures; **SFW** mode keeps everything all-ages. The provider you choose may still have its own rules. There are **two fixed rules**, even in free mode: no sexual content involving minors, and no sexual content about real people (real-person avatars are always SFW; adult fictional characters can be NSFW).

## Privacy and security

- Everything runs locally. The server listens **only on `127.0.0.1`** by default (`--host 0.0.0.0` exposes it to the network and warns you).
- API keys live in `~/.asta/settings.json` (permission `600`) and are **never** sent back to the browser.
- Protection against *DNS rebinding* (`Host` check) and cross-site requests (`Origin` check); uploads and served files go through path validation; uploaded media is identified by content, not by name.
- Worlds and games do not run AI-generated code: the model writes **data** (JSON), and the engine is the same auditable code every time.

## Repository layout

```
asta/
  cli.py  server.py  storage.py  jobs.py  cards.py  builder.py  attachments.py  voice.py  hf.py
  providers/     Anthropic, OpenAI-compatible, local GGUF, Demo (text models)
  agents/        shared runner + pipelines (worlds, avatars, 2D games), prompts, schemas, rule-based generators
  runtime/       3D engine: three.js, terrain, sky, weather, actors, audio, NPC AI
  runtime2d/     2D engines: visual novel, RPG, platformer, side scroller, point & click
  games2d/       2D game spec: schema, validation, packaging
  avatars.py  avatar_chat.py  routes_avatars.py    avatar cards, chat director, API
  assistant_chat.py  routes_chat.py  websearch.py  general-purpose Chat (history, streaming, tool suggestion, web search)
  canvas/        node schema, store, engine, media providers, timeline renderer, procedural Demo
  studio/        video projects: schema, scene-by-scene pipeline, automatic editing, export, ffmpeg tools
  rebuild/       Ren'Py / RPG Maker readers and converters (+ the optional AI text review)
  native/        optional Rust core (std only) with a Python twin for every function
  perf.py  termi18n.py  term_en.py   performance modes · terminal language (pt/en)
  web/           the WebUI (plain HTML/CSS/JS, no build)
tests/           unittest suite (API, pipelines, engines, providers, Canvas) + optional browser tests
install.sh  install.ps1
```

## Development

```bash
git clone https://github.com/KMC1525/ASTA && cd ASTA
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
asta --home ./asta-data                            # isolated development data
python -m unittest discover -s tests -t .          # offline test suite
```

Browser tests (Chromium via Playwright) and the JavaScript engine tests run automatically when Node.js (and Playwright) are available, and are skipped otherwise. See [CONTRIBUTING.md](CONTRIBUTING.md) (Portuguese: [CONTRIBUTING.pt-BR.md](CONTRIBUTING.pt-BR.md)). The change history is in [CHANGELOG.md](CHANGELOG.md).

## Roadmap

- Attached images as textures/signs inside 3D worlds.
- More structure types and biomes; interiors; roads and rivers.
- Local multiplayer (several players in the same world).
- AI-generated behavior scripts in a sandbox.
- Export a world as a desktop/mobile app.
- Ideas on the table (not scheduled): moving more hot paths to the Rust core; shared (multi-user) Studio projects.

## License and credits

[MIT](LICENSE) © 2026 KMC. Bundles [three.js](https://threejs.org) r159 (MIT) in `asta/runtime/vendor`.

---

> **AI-generated notice:** this entire project was generated and reviewed using the AI **Claude** by Anthropic, and only models from the **Claude Sonnet 5.0+** line were used.
