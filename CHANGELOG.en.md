# Changelog

All notable changes to ASTA are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

> English translation of [`CHANGELOG.md`](CHANGELOG.md) (the Portuguese original is the reference). Mentions of Portuguese UI strings keep the original text in quotes.

## [Unreleased]

## [0.11.0] — 2026-11-06

### Added — Canvas
- **30 new nodes, 5 per type**: Text (template, join, edit, pick a piece, refine with AI), Image (resize/rotate, filters and color, text on image, collage, video frame), Video (cut, join clips, speed/reverse, look, images to video), Sound (cut, mix, effects, audio from video, repeat), Input (color/gradient, silence, link, text draw, date and project) and Output (final video, GIF, final audio, final image, gallery). They run on ffmpeg and Python with no model or key (only "Refine with AI" uses the text model).

### Changed
- **Palette reorganized**: Text, Image, Video, Sound, Input, Output (old and new nodes in the right groups).
- **Every node integrates**: a video now connects to image ports (its middle frame is used) — including the Image node's references and the Video node's start image; text, image, video and audio go into the Editor and the Gallery; every output type has a destination in old and new nodes. Old canvases open unchanged.
- Error messages of the new nodes cite the port name as shown on the node.

## [0.10.5] — 2026-11-06

### Added
- **Smaller quantizations for Media models** (Configuration → Media → Precision and download): besides fp32/fp16/bf16, each model's panel looks up on Hugging Face the **community's compressed versions** (8-bit, 4-bit/NF4, fp8…) linked to the original model, with each one's size, and "Use this one" switches the chosen model to that repository for download. The ones ASTA can load come first, smallest to largest; GGUF/AWQ/GPTQ show as unsupported there. Works for image, video, sound, voice and transcription. They are made by third parties and 8/4-bit need the bitsandbytes library (NVIDIA card).

## [0.10.4] — 2026-11-06

### Fixed
- **Canvas: generating an image with a local model that was not downloaded yet** only showed an error. Now, if the chosen model was not downloaded, ASTA uses another already-downloaded one for the same function (the default or a suggestion) and says so on the node; if none was downloaded, the error gets a "Download the model now" button (opens Configuration → Media at the precision choice). Nothing is downloaded silently. Applies to image, sound, voice, transcription and video.

## [0.10.3] — 2026-11-06

### Added
- **Sign in with your account on AI providers**: **OpenRouter** got an official OAuth/PKCE login ("Sign in with your account", no key to copy; "Disconnect"). For **Claude, ChatGPT, Grok, Gemini and Hugging Face**, which don't let third-party apps use the account or subscription login, the card has "Sign in and create the key" (opens their login already at the keys page). API keys keep working everywhere; the login only runs on the ASTA computer.

## [0.10.2] — 2026-11-06

### Fixed
- The repository's Releases tab was empty (the APK was only built when a Release was published by hand). The `android-apk` workflow now runs on every push to `main` that changes the version or the app and creates the `vX.Y.Z` Release with the APK by itself.

## [0.10.1] — 2026-11-06

### Added — Mobile without a computer
- **Android app (APK) from the repository**: `mobile-app/` folder (Capacitor shell) and an `android-apk` workflow that builds the APK and attaches it to every Release. A QR code in the README (en/pt-BR) and in Configuration → Mobile and tablet leads to `releases/latest`.
- The app asks for the ASTA address (pairing QR by camera or typing), remembers the last one and **checks Releases for a new version, asking "Download now" or "Later"**.
- Note: the app is only the window; ASTA itself keeps running on a computer/server/VPN; iPhone/iPad keep "Add to Home Screen". The APK is built by CI and was neither run on a real device nor built here.

## [0.10.0] — 2026-11-06

### Added — Mobile
- **Mobile app (PWA)**: ASTA installs on the phone/tablet (home-screen icon, full screen) and talks to the ASTA on your computer. Manifest, icons (including maskable and Apple), service worker and iOS/Android meta tags.
- **Install by QR code**: `asta mobile` shows the pairing QR in the terminal, and **Configuration → Mobile and tablet** shows the same QR on the PC screen; scanning installs and pairs. The README (en/pt-BR) gained a "Mobile and tablet" section (with a QR that opens the guide on your phone).
- **Pairing and safety**: outside localhost only paired devices get in (secret code in the QR, HttpOnly cookie); the local computer needs no pairing; proxies/tunnels also require pairing; "Generate new code" unpairs all. A dependency-free QR generator of our own (versions 1–10, checked with a real reader).
- **In-app updates**: on open, on return to the app, when the connection comes back and every 5 minutes the app asks `/api/version`; if the ASTA on your computer has a new version it **asks "Update now" or "Later"**. Works on Wi-Fi and mobile data (the device only needs to reach the computer). A network-first service worker cache lets it open offline.
- **Platforms, architectures and devices**: Android and Apple (iOS/iPadOS), any chip (ARM64 — Snapdragon, Apple A/M, MediaTek, Exynos, Tensor — and x86); smartphones, foldables, tablets and the like.
- **Adaptive interface**: the app detects the device type (phone, foldable, tablet, computer), orientation, fold state, width-based layout and platform, and adjusts by itself — 44px touch targets, no zoom-on-focus on iOS, safe areas (notch/gestures), landscape phone with a side menu, tablet/open foldable with more room, and hinge-split foldables with the menu on one screen and the content on the other.
- "Install the app" bar (native dialog on Android; "Add to Home Screen" instruction on iPhone/iPad).

### Notes
- The hinge split (Surface Duo etc.) and the native install dialog depend on device-browser features and could not be tested on real devices here; classification was tested with emulation (iPhone, Pixel, iPad, Galaxy Fold).
- Mobile data away from home requires the computer to be reachable from outside (VPN/tunnel); that is not part of this version.

## [0.9.4] — 2026-11-06

### Fixed
- **Automatic-edit Analyst and Director: "no JSON object in the answer"**. Handled causes: a model that "thinks" and never closes `<think>` (the JSON stayed hidden inside the reasoning — it is now searched there too); an empty or text-only answer (the retry repeats the exact expected format and the `/no_think` instruction asks Qwen3-like models to skip reasoning).
- When it still fails, the message shows the beginning of what the AI answered (or "answered empty"), so the model can be diagnosed.

## [0.9.3] — 2026-11-06

### Fixed
- **Automatic editing: the Analyst and Director fell back to the automatic method (⚠)** when the AI answer was cut off — common with models that "think" before answering, because the token limit was small (900). The limit is now 3000, the request to the model is short and direct, a cut-off answer is retried with twice the room and, as a last resort, the valid part is used (anything missing takes the style's defaults).
- When an agent still needs the automatic method, the screen shows the reason ("the AI did not return valid JSON…") instead of only the ⚠.
- Applies to every agent: cut-off answers get more room on the retry.

## [0.9.2] — 2026-11-06

### Improved
- **Automatic editing, every style**, using per-genre editing techniques (YouTube/Shorts editing guides were researched; I can't watch the videos, so I used the practices they describe). Each style shows its "Technique" under the list and the AI Director receives that note.
  - **Gameplay**: opens with the best moment (hook with a zoom), then follows chronological order.
  - **Documentary and Vlog**: cutaways (b-roll) interleaved (every 2 and 3 shots), slow camera movement and pan; Vlog/Tutorial silence cuts leave a pad on speech.
  - **Phonk and Music video**: slower intro, a 'drop'/chorus with 1–2 beat cuts and a zoom on each cut, speed ramps only after the intro, closing in slow motion.
  - **Trailer**: final title card; **Photo slideshow**: varied timing and alternating zoom/pan.
  - No style repeats the same stretch while there is new material; music ducks under narration.
  - The Reviewer warns when material ran short and cuts repeated stretches.
- Fixed: a photo at the end could overshoot the target duration.

## [0.9.1] — 2026-11-06

### Added
- **Configuration → System**: a "Your PC's components" card with the type and name of each detected component (CPU, motherboard, computer, BIOS, GPUs, disks, audio, network, memory modules on Windows, RAM and operating system). Local, best-effort detection (Linux, macOS, Windows); nothing is sent anywhere.

## [0.9.0] — 2026-11-06

### Changed
- **Configuration reorganized**: 16 tabs in 4 groups — **General** (Appearance, Sections and shortcuts), **AI and models** (Providers, Media, Voice, Local models), **Sections** (Chat, 3D worlds, Avatars, 2D games, Canvas, Studio, Rebuild) and **System** (Performance, Data and backup, System). Each section tab has a header with a link to open the section and a "Reset this section's defaults" button.
- "Creative" was split into **Avatars** and **2D games**; Appearance now holds only theme, reading/comfort and language; System only hardware and version. Old links (`tab=creative`) keep working.

### Added
- **Per-section defaults** (applied whenever you create something new): **Studio** (project type, duration, style, aspect, language, motion, revisions, voice, captions, music, export quality/audio format, auto-edit style and duration), **Rebuild** (AI review on/off and the model-call limit), **Canvas** (starting template).
- **Sections and shortcuts**: what shows in the sidebar (including Studio and Rebuild), the start page, keyboard shortcuts and send key, with jump buttons to each section's tab.
- **Data and backup**: data folder (and the `asta folder` command), export/import settings (now including the Studio, Rebuild, Canvas and Performance defaults) and "Reset everything to default". **Performance** shows the Rust core status.
- The server stores `studio`, `rebuild` and `canvas` in the settings; they are part of export/import and reset (never `chat`, which holds search keys).

## [0.8.6] — 2026-11-06

### Changed
- **README (en/pt-BR)**: new “Terminal commands” section with the table of every command, highlighting `asta update` (Python, ASTA, libraries and Rust) and the new `asta folder`.

## [0.8.5] — 2026-11-06

### Added
- **`asta folder`**: opens ASTA's local data folder (`~/.asta`, or `--home`/`ASTA_HOME`) in the computer's file manager (Windows: Explorer; macOS: Finder; Linux: `xdg-open`). It creates the folder if it does not exist yet and prints the path. `--print` only prints the path; `--app` opens the installed program folder. Without a file manager (e.g. a headless server) it warns and shows the path. Text in Portuguese/English following the computer.

## [0.8.4] — 2026-11-06

### Changed
- **The English contributing guide is now `CONTRIBUTING.md`** — the file GitHub shows in the repository's “Contributing” tab (which shows only one). The Portuguese version moved to **`CONTRIBUTING.pt-BR.md`** (as with the README). `CONTRIBUTING.en.md` no longer exists; the links in the READMEs and guides were updated.

## [0.8.3] — 2026-11-06

### Changed
- **README updated** (English and Portuguese): it now presents the six tools (Studio and Rebuild included), the Studio and Rebuild sections in the interface table, the `ASTA_RUST` and `ASTA_LANG` variables, ffmpeg for Studio, the repository layout (`studio/`, `rebuild/`, `native/`) and the right links (the menu pointed to anchors that did not exist).
- **`CONTRIBUTING.en.md`**: full English translation of the contributing guide (`CONTRIBUTING.md` stays in Portuguese); the two reference each other and must be kept in sync.

## [0.8.2] — 2026-11-06

### Fixed
- **Studio: the preview video showed on top of dialogs** (e.g. “This project already has a timeline…” in automatic editing), breaking through the dark backdrop. The monitor now has its own stacking layer, and the editor's full screen sits below dialogs. Covered by a browser test.

## [0.8.1] — 2026-11-06

### Changed
- **Rust is now installed/updated automatically**, without asking, like the other code and libraries: `install.sh`, `install.ps1`, `asta update` and `asta native setup` install Rust if missing (rustup, in the user folder, no sudo), update it if present and recompile the core. This also applies without a terminal. `ASTA_RUST=no` (or `--rust no`) skips it and `ASTA_RUST=ask` asks again. If something fails (no internet, no compiler), it continues without Rust — ASTA works the same in Python.

## [0.8.0] — 2026-11-06

### Added
- **Optional Rust in the installers, in `asta` and in `asta update`.** New command **`asta native setup`**: installs Rust (rustup, minimal profile, stable toolchain, **in the user folder, no sudo**) if missing, **updates** it (`rustup update`) if already there and **recompiles** ASTA's fast core — the same core (`asta_core`) and any libraries `cargo` fetches, should there ever be some. Also `asta native install`, `asta native update`, `asta native build` and `asta native status`. `install.sh`, `install.ps1` and `asta update` run this step at the end (after the libraries and models) and **ask** in the terminal (`ASTA_RUST=ask`, the default; installing = default "no", updating what already exists = default "yes"); `ASTA_RUST=yes` (or `asta update --rust yes`) does it without asking and `ASTA_RUST=no` skips it. **Without a terminal Rust is never installed without permission** (it only updates if already present). It also works with `curl … | sh` (the question reads the real terminal). A freshly installed `cargo`/`rustup` is found even outside the PATH (`~/.cargo/bin`, `CARGO_HOME`). If the system compiler is missing, ASTA says what to install (Linux: `build-essential`; macOS: `xcode-select --install`; Windows: Visual Studio Build Tools). Everything is optional and never breaks the installation.
- **Terminal text in the computer's language.** Everything the terminal shows — `asta`, `asta update`, `asta libs`, `asta models`, `asta native`, `asta doctor`, `--help` and the **installers** (`install.sh`, `install.ps1`) — appears in **Portuguese or English**, following the system language (`LC_ALL`/`LC_MESSAGES`/`LANGUAGE`/`LANG`; macOS: preferred language; Windows: UI language); any other language falls back to English. `ASTA_LANG=pt|en` forces one. `asta` passes the language on to the installer, so both speak the same. New: `asta/termi18n.py` and `asta/term_en.py`.

### Changed
- The installers' Rust step no longer depends on `cargo` already being in the PATH: the logic lives in `asta native setup` (a single one for Linux, macOS and Windows). `asta doctor` shows the Rust version and the terminal language; the Performance card (Configuration → System) points to `asta native setup`.

### Tests
- `tests/test_terminal_lang.py`: language detection (Portuguese variants, variable priority, `ASTA_LANG`, `C`/`POSIX`), every message in the code has a translation (with the same `{fields}`), output and `--help` per language, the installer receives the language and the Rust choice, `native setup` (yes/no/ask/no terminal/failures), `find_tool`, `native` commands and `--rust`, `install.sh` (syntax, language detection, every message bilingual) and `install.ps1` (bilingual messages). The existing terminal tests pin `ASTA_LANG=pt`.

### Known limits
- `install.ps1` was written carefully and checked by structure tests, but **was not run on a real Windows** in this session (there is no PowerShell here); `install.sh` was run and tested. On Windows, compiling the core requires the Visual Studio Build Tools (ASTA warns about it).

## [0.7.1] — 2026-11-06

### Fixed
- **Timeline keyboard shortcuts (manual mode):** after touching an inspector field (speed, filter, volume…) focus stayed stuck in it and **S, J, M, C, Del, Space stopped working** until you clicked elsewhere — focus now leaves the field by itself (and clicking the timeline releases it too). Toolbar buttons no longer steal focus (Space does not trigger the last clicked button). **Holding a key** (Del, S, J…) no longer repeats the action in a burst. **S** cuts whatever is under the cursor even when the selection does not pass through it. The **cursor can go past the end** of the timeline (to place a new clip; it used to stop at the end).
- **Media vanished from the bin** when switching tabs (or after entering "Edit from scratch" and importing files): the screen used a stale copy of the project. The timeline now always loads the up-to-date project, and a project with media opens the editor even without clips.
- The preview showed a black frame at the start (because of the fade-in); when paused it now shows the full frame.

### Added
- **Resizable timeline windows:** drag the dividers to change the **media width**, the **properties width** and the **monitor × timeline height** (double-click resets), **taller/shorter tracks** and **editor full screen** (`F`; `Esc` leaves). Sizes are remembered in the browser.
- **Copy, cut and paste** clips (`Ctrl+C`, `Ctrl+X`, `Ctrl+V` — pastes at the cursor); `Esc` clears the selection and returns to the select tool.

### Tests
- `tests/browser/studio_ui.js`: focus after the inspector, copy/paste, held key, Space after a toolbar button, cursor past the end, cut under the cursor, resizing the three dividers, remembering the size on reload, full screen and manual editing with import and tab switching.

## [0.7.0] — 2026-11-06

### Added
- **Studio — generate, edit and review AI audiovisual videos** (new section, right below Canvas). Everything that existed stays as it was; Studio reuses the text providers (Configuration → Providers) and media providers (Configuration → Media: image, video, sound, voice), including the offline Demo mode and local models.
  - **Duration types:** **Shorts/Reels** (up to 2 min), **Short film** (up to 30 min) and **Feature** (up to 90 min) — plus **Custom** (any duration, up to 6 h). The duration is easy to adjust: minutes + seconds, a slider and shortcuts (30 s, 1 min, 5 min, 1 h 30…); going past the type's limit switches the type by itself. Each type starts at its default (9:16 for Shorts, 16:9 for the others) and plans scenes of the right size (≈8 s, ≈40 s, ≈90 s).
  - **Styles:** Realistic, Cartoon, Anime and Custom (you describe the look). The style goes into every image prompt, together with the characters' looks from the project "bible", to keep continuity.
  - **Project types:** **Single** (starts and ends in one video) and **Series** (several episodes; each episode receives the series bible — characters, world, tone, facts — and the recaps of the previous ones, and when finished updates the bible and writes its own recap).
  - **Scene-by-scene generation pipeline (multi-agent, multi-step):** the **Showrunner** writes the script (in acts when there are many scenes) and, **for each scene, one step at a time before moving on to the next**: **receive** (brief + context + continuity) → **analyze** (the Analyst splits it into shots, fits the narration to the duration, sets music and effect) → **generate** (voice, images, motion — light Ken Burns or the provider's video model —, music and effect) → **review** (objective checks + AI Reviewer; if rejected, applies the fix and redoes only what changed) → **deliver** (places the clips on the timeline). The screen shows the live scene board with each scene's five steps. A delivered scene is saved: you can **cancel and continue** from where it stopped and **redo a single scene** (the timeline adjusts without moving the rest). Without a text AI (Demo) or on an invalid answer, deterministic agents take over.
  - **Automatic editing:** several attachments (videos, images, audio) + a prompt + an **editing style** — **Gameplay** (action moments from volume peaks, fast cuts, zoom on highlights), **Documentary** (long cuts, soft transitions, title, voice-over up front), **Phonk edit** (cuts on the beat, slow/fast motion, zoom, grainy filter, music at full blast), **Trailer** (accelerating pace, title cards), **Vlog** (cuts dead time), **Tutorial** (removes pauses), **Music video** (cuts on the bar) and **Photo slideshow**. Pipeline: **Analyst** (each file's role: footage, b-roll, music, voice-over; measures scene changes, volume peaks and silences with ffmpeg) → **Director** (pace, order, highlights, stretches to avoid, titles) → **Reviewer** → timeline assembly. It also works inside a project (as a new episode, in a series).
  - **Kdenlive-style timeline:** media bin (import, drag to the timeline), preview **monitor** with playback (video, audio, captions, filters and fades), properties **inspector** and tracks (T1, V2, V1, A1–A3) with **cut** (S or razor C), **join** (J), **mute** (M), **delete** and **delete closing the gap**, duplicate, trim at the cursor, move/trim with **magnet** and **ripple** mode, text, markers, speed (0.25×–4×), volume, fades, opacity, scale/position, fit (fill/contain/stretch) and **color filters** (B&W, warm, cool, vivid, VHS, cinematic, phonk); lock/hide/mute tracks, marquee selection, context menu, **undo/redo**, zoom (Ctrl+wheel) and **autosave**.
  - **Export:** **Full** (video + audio, MP4), **Video only** and **Audio only** (M4A, MP3 or WAV), at 480p/720p/1080p; exports are listed with open/download/delete.
  - New: `asta/studio/` (schema `asta.studio.v1`, storage, pipeline, automatic editing, export, ffprobe/ffmpeg tools), `/api/studio/*` routes, `asta/web/js/views/studio*.js`. The Canvas renderer gained clips with **speed**, **mute** and **filters** and the **video/audio** modes (nothing changes for existing users).

### Fixed
- The duration field no longer scrambles minutes and seconds while you type.

### Known limits
- The final video quality depends on the chosen media providers; in Demo mode images, voices and music are synthetic. Very long videos (90-min features) generate hundreds of shots and can take hours and cost a lot with paid providers — that is why generation is resumable.
- The browser preview approximates filters and fades with CSS; the export (ffmpeg) is the reference. Automatic editing does not transcribe speech (it uses volume peaks, scene changes and silences).

### Tests
- `tests/test_studio.py` (schema, storage, render with modes/speed/mute/filters, scene-by-scene pipeline with resume and redo-scene, planning in acts, text agents and Reviewer fixes, series, automatic editing per style, API and full/video/audio export) and `tests/browser/studio_ui.js`.

## [0.6.3] — 2026-11-06

### Fixed
- **Avatar that did not answer ("The provider returned no text").** Before, an empty stream was enough to leave the avatar mute. Now, in a one-to-one chat, ASTA tries other ways before showing the error: **(1)** retries **without streaming** (some servers/models only send the whole answer; a model that only "thought" gets more room to answer); **(2)** retries with a **simplified request** — without the `system` role (strict-template models such as Gemma and Mistral return empty with it) and with Qwen3's `/no_think`; only then does it warn, with the reason. No empty message in the history.
- **Local model going mute with the Light performance mode.** If the built-in GGUF model returns no text with flash attention / 8-bit KV cache (depends on the llama-cpp version/build), ASTA reloads it with only the basic loading, remembers that for that model and tries again — both streaming and not.

### Tests
- Avatar: empty stream → non-streaming; only the simplified request works; a model that only "thought"; all-empty still explains the error. Local model: empty stream/chat reloads in basic mode.

## [0.6.2] — 2026-11-06

### Added
- **Chat tab strip that slides sideways**: with many tabs, scroll with the **mouse wheel**, **drag** the strip with mouse/finger or use the touchpad's horizontal gesture; the front tab is always kept in view. Clicking right after a drag does not switch tabs by accident.
- **Split view, Firefox style — two tabs on the same screen, side by side.** **Right-click a tab** → *Split the view with a new tab* or *Split the view with…* (pick one of the other tabs). The two tabs become a **group** in the strip (columns icon, dashed border between them) and show in two panes, each with its own scroll and live streaming. The text box applies to the **focused pane** (highlight border on top; click a pane to focus it). Clicking a tab outside the group shows only that tab while the group stays in the strip; clicking the group returns to the split view. *Undo split view* (right-click) or closing either tab undoes the split; the split comes back after reloading the page.

### Tests
- `tests/browser/chat_split_ui.js`: scrollable strip (wheel and drag), right-click menu, side-by-side panes, focus and sending per pane, group in the strip, tab outside the pair, reload, undo, split with a new tab and closing one of the two. `chat_stream_ui.js` became more robust (it waited for the first answer to finish before deleting the conversation).

## [0.6.1] — 2026-11-06

### Changed
- **Every section creates inside its own page, without forcing you to go to the Chat.** Worlds, Avatars, 2D games and Rebuild now have, at the top, the same composer as the Chat (text, attachments, tool options and Run) — with progress and the result shown in the section. In Worlds, 2D games and Rebuild, the "New…" and "Create with AI" buttons lead to the section's composer; "Update" (on a game or world) puts the composer in update mode (with "× Create a new one" to leave it). Result buttons ("New game", "Try again"…) return to the section the creation started from; creating from the Chat is unchanged. Coming back to a section with one of its creations in progress resumes the progress view. Canvas already created in its own page (the "New canvas" modal).
- The empty state of the Worlds editor points to the section's composer instead of the Chat.

### Tests
- `tests/browser/sections_inline_ui.js`: each section creates and shows the result without leaving it (the hash never becomes `#/main`), "Update" in update mode, Rebuild with the legal notice, and the Chat still works.

## [0.6.0] — 2026-11-06

### Added
- **Rebuild now has a multi-agent, multi-step pipeline to improve quality, especially with small local models.** The deterministic conversion (which keeps the original's structure) is unchanged; after it, AI agents proofread **only the text**, in short steps: **Profiler** (tone/setting and readable names for generic events and maps such as `EV012`/`Map003`) → **Polisher** (lines in batches of up to 6: typos, case, punctuation and stray symbols; never translates) → **Auditor** (undoes changes that altered the meaning) → final validation. New `asta/rebuild/refine.py`; `RebuildPipeline` now uses the same `Runner` as the other pipelines (agent logs go into the ZIP via `agent_logs`).
  - **Built for small models:** inputs of a few hundred tokens, flat JSON output, low temperature, a failed batch is retried line by line, a cap of 40 calls per rebuild, and only lines that look problematic are sent.
  - **The AI cannot break anything:** each returned line passes validators (`{x}`/`[x]` placeholders, numbers, length, line breaks, accent-free word similarity — translations and rewrites are refused) and names have their own validator; a **structural lock** compares the game's fingerprint without texts before and after and, if anything but text changed, restores the deterministic result. A model error/outage only produces a warning.
  - **AI-free cleanup** (always runs): engine code leftovers (`\C[2]`, `\N[1]`, `{w}`, `{i}`…), broken accents (UTF-8 read as Latin-1) and double spaces.
  - The Rebuild composer has a **Proofread the text with AI** option (on by default; `refine: false` in the API). Without an AI provider (Demo mode) the AI steps are skipped and only the cleanup runs. The result screen shows the review summary.

### Known limits
- Tested with a fake provider and synthetic projects; quality with real local models was not measured. The AI fixes text and names; it does not rewrite dialogue, translate or reorganize the structure (on purpose).

### Tests
- `tests/test_rebuild_refine.py`: cleanup, detection, validators, batches, line-by-line retry, Auditor, call cap, structural lock, visual novel, pipeline with/without a provider, `refine: false` and provider outage.

## [0.5.1] — 2026-11-06

### Added
- **New "Rebuild" section in the sidebar** (right below Canvas): lists only rebuilt games and has a "Rebuild a game" button. It can be hidden in Configuration → Appearance like the others; Alt+N shortcuts follow the new order (Rebuild = Alt+6, Library = Alt+7, Configuration = Alt+8).

### Fixed
- The Rebuild section did not show up for anyone already on 0.5.0: the updater only reinstalls when the version number goes up. This release (0.5.1) exists so `asta` updates itself; if the sidebar still lacks Rebuild, run `asta update --force` and reload the page (Ctrl+Shift+R).

## [0.5.0] — 2026-11-05

### Added
- **Rebuild — rebuild existing games in plain HTML/CSS/JS** (*Home → Rebuild*). Attach a ZIP (or loose files) and ASTA rebuilds the game's **structure** with the **same organization as the original**, as a game that runs in any browser. **Only two engines are supported in this version:** **Ren'Py** (`.rpy` scripts: labels, dialogue, menus, jumps/calls, variables, `if`) and **RPG Maker 2000, 2003, XP, VX, VX Ace, MV and MZ** (maps, events with pages/conditions, messages, choices, switches/variables, transfers, shops, battles, actors, items, enemies, troops, common events). The engine is detected automatically; an unknown, encrypted or compiled ZIP (`.rgss*a`, `.rpa`, `.rpyc`, encrypted MV/MZ) gets a clear message.
  - New `asta/rebuild/` package: `.rpy` reader, Ruby Marshal reader (XP/VX/Ace), LCF binary reader (2000/2003), JSON reader (MV/MZ), a common converter to ASTA's RPG engine and a Ren'Py → visual novel converter.
  - **Only the structure is rebuilt; original art, audio and fonts are never read or copied.**
  - **Legal notice at the end of every rebuild** (result screen and `LEGAL-NOTICE.md` in the ZIP, also appended to the game's README): do not publish on Steam or other platforms; personal use only; any legal problem is the responsibility of whoever rebuilds, not ASTA's creator/contributors; and "even with this notice, we will not stop you from rebuilding, but be aware of what you are doing". Routes `POST /api/games/rebuild` and `GET /api/games/rebuild/notice`.
- **Optional Rust core (`asta/native`)**, standard library only (no crates), loaded through `ctypes`, with a **pure-Python equivalent for every function**. It speeds up Canvas audio synthesis (music, effects, voice → 16-bit PCM) by working on shared buffers (`array('d')`) instead of one Python object per sample: a 20 s music track went from ~15 s to ~0.05 s. Commands `asta native [build|status]`; `asta doctor` shows the state; `ASTA_NO_NATIVE=1` turns it off and `ASTA_NATIVE_LIB` points at a custom library. The installers (Linux/macOS/Windows) build it automatically when `cargo` exists, never failing because of it.
- **Performance mode** (*Configuration → System → Performance*; `settings.performance`): Automatic (by hardware), Light, Balanced, Maximum. Light: capped context window (a user-set value always wins), `mmap` and a smaller batch, flash attention + 8-bit KV cache, **automatic unloading of idle models** (default 10 min; at most 3 min in Light) and, for local image/video models, attention/VAE slicing and CPU offload. Options the installed llama-cpp-python does not know are skipped.

### Changed
- `asta doctor` shows the Rust core and the performance mode. The package ships the core's source (`native/Cargo.toml`, `native/src/*.rs`).
- Roadmap: "rewrite the backend in Rust" became "move more hot paths to the Rust core".

### Known limits
- Rebuild was tested with synthetic projects for each engine; the LCF (2000/2003) reader was not validated against real commercial files.
- The Rust speed-up was measured on audio synthesis only; Light mode's RAM/VRAM savings were not measured on real GPUs or models.

### Tests
- `tests/test_rebuild.py` (all engines, ZIP, warnings, API) and `tests/browser/rebuild_ui.js`; `tests/test_perf_native.py` (profiles, context caps, idle unloading, llama load fallback, Rust × Python equivalence, CLI).

## [0.4.5] — 2026-11-05

### Added
- **Ctrl+J (⌘+J on Mac) opens a new tab in the Chat section**, from any screen (from outside Chat it takes you to Chat with the new tab); it works alongside Alt+N, `/nova` and the palette. It follows the shortcuts on/off option. It shows in the help (`?`) and in the palette.

### Changed
- **Chat no longer uses emojis in answers, to save tokens.** The Chat prompt forbids emojis (even if the user uses them) and, as a guarantee, ASTA **strips emojis** from the answer — live and in the saved text (pictograms, flags, keycaps such as 1️⃣, ZWJ sequences, skin tones). Common symbols (✓, →, ©, ™, ★), accents and other alphabets stay. Chat only (avatars and creations do not change). Live, a double space may appear where the emoji was, until the answer finishes; the final text comes out without it.

### Tests
- Emoji removal (and what must not disappear), streaming, saved text and the prompt rule; Ctrl+J in the browser.

## [0.4.4] — 2026-11-05

### Changed
- **Running `asta` (the run command) now also updates/installs everything**, like the Windows, macOS and Linux install command: before opening, it runs the official installer (Python, ASTA, libraries and the pre-installed-models question — it skips what is already up to date). It happens **when a new version is published** and, even without one, **at most once every 24 h** (`ASTA_UPDATE_EVERY=<hours>`; `0` = every launch). After updating, ASTA reopens itself on the new version (on Windows the installer continues in a new window and ASTA closes, so it can replace the files).
  - **Everyday safety:** it only applies to ASTA installed by the official installer (manual/`pip`/editable installs are never touched); **offline it opens normally**; if the update fails, it opens as is; `asta --no-update` or `ASTA_NO_UPDATE=1` turn it off; no update loop.
- `asta update` still exists to update right away (`--force`, `--core`, `--extras`…).

### Tests
- `tests/test_cli.py`: a new version updates and reopens (no loop), up to date and recently checked just opens, `ASTA_UPDATE_EVERY=0`, never touches manual install / turned off / offline / failure, and the Windows case.

## [0.4.3] — 2026-11-05

**Audit** release: I went through every section (Chat, Worlds, Avatars, 2D games, Canvas, Library, Configuration) like someone opening ASTA for the first time — in the browser (desktop and phone, dark and light theme) and through the API —, reviewed the internal prompts and added **Chat tabs**. Worlds, the five game genres, avatars and Canvas were generated and opened (no console errors).

### Added
- **Chat tabs and the «New chat tab» command.** Each tab is a conversation; you can keep several open and **an answer keeps arriving in the background** while you use another tab (the busy tab shows an indicator). Ways to open a new tab: **Alt+N**, the **command palette** (Ctrl+K → *New chat tab*, which also works from other screens and takes you to Chat), the **New tab** button, the **+** in the tab bar, or typing **`/nova`** (or `/new`) in the message box. **Alt+W** closes the front tab (the last one never disappears; closing a tab does not delete the conversation, which stays in History).
  - Each tab keeps its own draft; open tabs **come back after reloading the page** (same order, same one in front); opening from History a conversation that already has a tab just brings that tab to the front; a blank tab is reused (never two blank ones). The tab bar only shows up with two or more tabs (the screen stays clean).
  - Anyone who leaves the Chat screen in the middle of an answer and comes back sees «Answering in the background…» and the answer appears when it finishes (before, it looked like the question had been left unanswered).
- **Revised Chat prompt:** answers in the user's language, at the right length; Markdown in moderation; concrete recipes/plans, math with the steps, code that works; admits when it does not know instead of making things up; knows it **cannot browse the internet** by itself and suggests the **Web** button when the topic needs current information; reads attachments by name; keeps the rule of the creation-tools activator.
- **JSON rules for the agents:** the preamble of all agents (world, avatar, game) now asks for double quotes, no comments, no trailing commas, **no placeholders such as «...»** and, if the model reasons first, for that to be brief and end with the complete JSON (fewer invalid answers on small models).

### Fixed
- **The Worlds screen listed 2D games as if they were worlds** (and opened one of them — «No world to configure» — instead of the real world). Now only 3D worlds appear.
- **Updating a game (Demo) replaced its name with the text of the change request** («Add a secret ending»). The game keeps its name.
- **Offline generator titles ended in the middle of the sentence** («A medieval village by the shore of a», «A Short Adventure Game With»): the title is now the first sentence, never ending in a preposition/article and with only the first letter capitalized.
- **A `settings.json` with a value of the wrong type (hand-edited, or a wrong API call) took down the whole screen**: `/api/state` started answering 500 and ASTA would no longer open. Settings are now always normalized (when read and before saving): an object where an object belongs, number/text/boolean of the right type.
- **Request bodies that are not JSON objects** (list, text, number) and lists with the wrong type (`character_ids: 3`) caused a 500 error on dozens of routes; they now answer 400 with a clear message (or are ignored, in the case of lists).
- **Agent answers with «reasoning» (`<think>…</think>`) containing braces** could be read as the JSON object; brace spans that are not JSON («{example}») were the first candidate. The extractor ignores the reasoning and moves on to the next valid object; a truncated answer is still reported.
- **Texts that appeared in Portuguese in the English interface:** the Library «3D worlds» filter, the «New canvas» name, the model name in the Chat answer («Demo (offline, no AI)»), Demo-mode warnings in the avatar result, and Canvas providers («OpenAI-compatible server»). Old texts that still said «generate on the main screen» now point to Chat.
- **Configuration:** the nine tabs hid the last two (Appearance and System) behind an invisible scroll; the page is now wider and the tabs wrap onto a new line. The Chat title «How can I help?» was too light gray.

### Changed
- «New chat» became **«New tab»** (the top button, the palette command and the shortcuts help). `go('main', {fresh|newtab})` opens/reuses a blank tab instead of replacing the conversation.

### Tests
- `tests/test_audit.py`: offline generator titles, JSON extractor, corrupted settings (and hand-edited file), invalid bodies, worlds × games, game name on update, **fuzz of every `/api` route** (none may return 500 for wrong-typed bodies), prompts and old texts.
- `tests/browser/chat_tabs_ui.js` (Alt+N, `/nova`, palette, Alt+W, per-tab draft, parallel and background answers, tabs that come back, leaving and returning in the middle of an answer), `tests/browser/audit_ui.js` (Worlds with worlds only, translations, Configuration tabs, Chat title, honest Demo) and the send/streaming test rewritten for tabs.

### Note
- The limits of previous versions still apply: real AI models, internet search and 3D on a real GPU were not tested here (simulated servers and Chromium without GPU). In games and worlds generated by **Demo**, the story/dialogue comes from rules, not AI.

## [0.4.2] — 2026-11-05

Review of **Chat mode** — mainly sending prompts and the model's streaming answer — and the **searched-sources panel** on the right edge. Each bug was reproduced (in a test or in the browser) before being fixed.

### Fixed
- **Scrambled text while streaming with models that «think»** (`<think>…</think>`: Qwen3, DeepSeek R1, gpt-oss…). Reproduced: with the pieces `<thi` · `nk>thinking</think>` · `Hello, how are you?` the screen showed `<thi how are you?`; and with a `</think>` without an opening (the model already starts thinking) the reasoning showed up and the answer came **cut in the middle**. Now ASTA holds back the start of an incomplete tag at the end and, when the visible text changes, sends a `reset` event that replaces the whole text (the saved answer was always right; only the screen was wrong).
- **Long answers made the server slower and slower:** on every piece the whole text was cleaned again (quadratic cost). It is now incremental (40 thousand pieces in under 2 s in the tests).
- **Pasted texts over 12,000 characters were silently cut.** The limit became 60,000; what fits the model is decided by the context window.
- **Typed text lost focus when sending the first message** (the box moves from the home screen to the footer) — you had to click again to keep writing. Focus and cursor now come back.
- **The first question was invisible until the server answered** (the screen only changed on the first event) and, with web search or a model loading, nothing showed that something was happening. The «typing» bubble appears immediately.
- **Switching conversation (or creating a new chat) in the middle of an answer threw the bubble and text into the other conversation**, and the race between «stop» and «sync» could reopen the old conversation. Now the answer in progress is ended before the switch and nothing leaks.
- **After Stop (or a model failure) the question was left unanswered with no way to ask again** — only by typing everything again. The **Answer** notice appears; it also appears when reopening a conversation whose last question went unanswered. **Esc** also stops the answer.
- **Send failure** (server refused, connection dropped before accepting): the question bubble stayed on screen. Now it disappears, the text goes back to the box and the error appears; attachments only leave the box when the server accepts the message.
- **Conversation deleted in another tab:** every following send failed with «Conversation not found». Now Chat opens a new conversation and sends again.
- **Enter confirming a word on a Japanese/Chinese/Korean keyboard (IME) sent the message half-written** in some browsers (`keyCode 229`).
- **Drawing the answer on every piece:** the Markdown was redone entirely on each received piece (it froze fast answers and made selected text flicker); now it is at most one draw per frame.
- **Markdown:** sub-lists (indentation was lost), loose addresses (`https://…`) that become links without taking the final period, and `[1]`/`[1, 2]` that become buttons when there is a matching source.

### Added
- **Sources panel on the right edge of Chat:** lists **all** searched sources, **in the order the search returned them**, grouped by search (Search 1, 2… with the query used), each with number, title (link that opens in a new tab), site, snippet and a **read** badge when the page was read in full.
  - It opens by itself when a search arrives (on wide screens; on narrow screens it becomes a drawer on the right), shows «Searching…» while the search runs and fills in real time. A **Sources (n)** button at the top opens/closes it; the choice to close is remembered.
  - The `[n]` buttons in the answer text and the **Sources** button under the answer take you to the source in the panel and highlight it; clicking a search's title takes you to the matching answer. Sources (with snippet and badge) are saved in the history.
- Shortcut: **Esc** stops the answer.

### Changed
- The Chat screen is now a conversation pane plus the sources panel side by side (`.chx-main` / `.chx-side`); the model, tools and thinking menus scroll less.
- `public_sources` (search) also returns `snippet` and `read`; Chat messages store `snippet`/`read` in the sources. New SSE event `reset` alongside `delta`.

### Tests
- `tests/test_chat_stream.py`: `<think>` tags cut any which way (equivalent to cleaning the whole text), `</think>` without opening, `<`/`<th…` that are not tags, linearity on long answers, large pasted text, failure in the middle of the answer (the question stays, nothing half-written, Answer works).
- `tests/browser/chat_stream_ui.js`: real-time streaming (the text grows), immediate bubble, focus, `<think>`, Markdown, Stop/Esc → Answer, switching conversation in the middle, deleted conversation, send failure, IME and the sources panel (order, numbers, badge, citations, second search, close/remember, narrow screen).

### Note
- The streaming tests use a simulated LM Studio server: I did not test with a real model or with outbound network (web search is still tested only with simulated answers, as in 0.4.1).
- The panel lists the sources **ASTA searched for the answer** (the search is single per message; pages read in full carry the *read* badge). The model does not run searches on its own.

## [0.4.1] — 2026-11-05

**Chat with native web search and its own settings tab** (answer size, context window, thinking time).

### Added
- **Native web search in Chat (🌐 Web button)**, for any prompt and any model (cloud or local — the search belongs to ASTA, it does not depend on a provider feature):
  - it searches the question, **reads the first pages** and hands the model a block with **numbered sources**; the answer cites [1], [2] and shows clickable **Sources** chips, which are saved in the history. On follow-up questions ("and what is its price?") the model rewrites the query using the conversation context; today's date goes into the context.
  - **Engines:** *Automatic* (DuckDuckGo → Wikipedia, no key), DuckDuckGo, Wikipedia, **Brave Search** (key), **Tavily** (key) and **SearXNG** (your own instance). Keys stay on the server and never go back to the browser. Number of results, pages read in full and language are configurable; **Test search** button.
  - **Also in the creation tools:** with the tool on and Web lit, Run searches the prompt and attaches the references (limited to 6,000 characters) before starting the pipeline; if the search fails, it creates without it and warns.
  - **Security:** only `http(s)`; result pages on `localhost`, private networks, link-local (such as `169.254.169.254`) and reserved IPs are refused, **including on redirects**; results are treated as untrusted text (the model is instructed never to follow orders coming from the pages); size and time limits.
  - The button choice is remembered; *Configuration → Chat → Keep web search on by default* sets the starting point. With Demo (no AI) the search does not run and Chat explains why. Search failure → warning and the answer goes on with only what the model knows.
  - API: `POST /api/web/search` (titles, links and snippets) and `POST /api/web/context` (block for the prompt); `POST /api/chats/<id>/send` and `/regenerate` accept `"web": true` and emit the `search` and `sources` events.
- **Chat tab in Configuration:**
  - **Answer size (tokens)** — from 64 to 32,000, with shortcuts (500 · 2K · 6K · 16K). Applies only to the visible text: thinking goes beyond it.
  - **Context window (tokens)** — from 1K to 2M, with shortcuts (4K … 128K): the history sent to the model fits in it (after discounting system text, web sources and the answer); whatever exceeds it has the **oldest** messages cut first. Plus **remembered turns**, **creativity** and **custom instructions** (they go into every Chat conversation).
  - **Default thinking time** and the **web search** options (engine, results, pages read, keys, SearXNG, language).
- **Thinking time (Off · Slow · Medium · High · Extra high · Ultra)**, on a button **next to the model name — which only appears when the chosen model has the feature**:
  - **Claude** (3.7 and the 4/5 family): extended thinking, with a budget of 1,024 / 4,000 / 10,000 / 20,000 / 32,000 tokens **on top of** the answer size (temperature is not sent, as the API requires; the total respects the 32,000 output cap).
  - **OpenAI** (o-series, GPT-5), **Gemini 2.5+** (compatible endpoint), **gpt-oss** (LM Studio, Ollama, llama.cpp, custom) and reasoning models on **OpenRouter**: `reasoning_effort` (or `reasoning.effort`) low / medium / high — *Extra high* and *Ultra* use *high* with more token headroom (these providers only have three steps).
  - Models without the feature: no selector and nothing is sent. If a model refuses the mode, ASTA **redoes the request without it and warns**.
- Larger Chat menus (model and tools scroll less) and `settings.chat` gained `context_tokens`, `thinking`, `instructions` and `web`.

### Changed
- The "spent the limit thinking" notice now points to *Configuration → Chat* (raise the answer size or lower the thinking time). Chat notices are now translated.

### Tests
- `tests/test_websearch.py`: DuckDuckGo HTML parsing (ads out, redirects unwrapped), Wikipedia, Brave/SearXNG, engines without a key, automatic-mode fallback, private-host blocking, HTML → text, context block with limit, query rewritten on follow-ups, sources saved with the answer, search failure and Demo; per-model support, levels, budgets, request to Claude and `reasoning_effort` (with the retry when the model refuses); context window cutting the oldest; key secrets; routes.
- `tests/browser/chat_settings_ui.js`: Chat tab (fields, shortcuts, save), Web button (default, remember, persistent sources), thinking selector next to the model (only with a compatible model) and the search in a creation tool's prompt.

### Note
- **I could not test the search against the real internet** in this development environment (outbound network is blocked): DuckDuckGo was tested with sample HTML in the page's known format (`result__a`/`result__snippet`) and the other engines with simulated answers. If DuckDuckGo changes its HTML or asks for verification (CAPTCHA), Automatic mode falls back to Wikipedia and the message points to the keyed engines (Brave/Tavily) or SearXNG.
- The thinking modes follow each API's public documentation, without having been tested against a real Claude/OpenAI/Gemini; the tests use simulated servers.

## [0.4.0] — 2026-11-05

**Chat 2.0.** The **Main** screen became **Chat**: a clean, general-purpose conversation (cake recipe, studying, text, code…), with the model selector next to Run. The multi-agent creations are all still there, but now they only run **when you ask** — an activator.

### Added
- **Chat screen** in place of Main (the `#/chat` shortcut and menu order remain; the *Start screen* "Main" is now called "Chat"). Layout: **text box** on top; below it, **attachments on the left** and, **on the right, the model button and Run**. Attachments of any kind (click, drag-and-drop, paste) are read and used as context.
- **Model and provider selector** (button next to Run): lists providers (cloud and local), shows each one's models (for LM Studio, includes *Automatic*), accepts typing another name and leads to *Manage providers…*. The change is saved in `settings` (generation provider + model) and applies to the whole app.
- **Persisted general conversation**, with **streaming** answers and **Markdown** (lists, headings, tables, quotes, code with a *Copy* button; own renderer that only creates DOM nodes — HTML from the model is never interpreted, links only `http(s)`/`mailto`). **History** (the last conversation reopens by itself; *New chat*; delete), automatic title, **Stop** (Run turns into Stop; nothing half-written is saved), **Answer again** and copy. Honest notice when the engine is only **Demo** (no AI): Chat says it cannot really answer and points to the model selector.
  - API: `GET/POST /api/chats`, `GET/PUT/DELETE /api/chats/<id>`, `POST /api/chats/<id>/send` and `/regenerate` (SSE: `user, title, provider, notice, typing, delta, message, suggest, removed, error, end`), `GET /api/chat/providers`. Settings in `settings.chat` (`history_turns`, `temperature`, `max_tokens`).
- **Creation tools activator** (✦ *Create*): 3D World, Avatar, 2D Game and Canvas. **No agent/multi-agent/multi-step process runs by itself**: Chat only talks. If the request looks like a creation ("create a 2D game…"), it **suggests** the tool (strip with *Turn on 2D Game*), but only pre-fills the box — you are the one who runs it, by pressing **Run** with the tool on. You can turn it off (×) and go back to chatting. Each tool's options (genre, count, relationship, SFW/NSFW, perspective, base photo…) only show while it is on; updating a project from the Library opens Chat with the right tool already on.
- Command palette: **New chat**.

### Changed
- `home.js` now only holds the creation tools and the result screens (the `composer.js` composer became configurable: tools on the left/right, button label, swapping the action without losing text or attachments).
- The floating menu (`popover`) repositions itself when the list grows and never leaves the screen.

### Tests
- `tests/test_chat.py` (conversation, history, context, attachments, Stop/regenerate, activator detection without running, honest Demo, providers) and `tests/browser/chat_ui.js` (layout: attachments on the left and model + Run on the right; streaming and Markdown with no injected HTML; suggestion that does not run; model switch; Stop; history; and the tool's Run creating the game). The old browser tests now use the activator instead of the mode bar.

### Note
- The creation pipelines are the same as before; only **how** you reach them changed. Anyone who used the mode bar on the Main screen now turns the tool on in ✦ *Create*.
- With the **Demo** provider, Chat does not "understand" questions — Demo is rule-based. To really chat, pick a model in the selector.

## [0.3.3] — 2026-11-05

Review of the **Avatars** section, mainly the moment when the user talks to the avatar. Each item was reproduced (in a test or in the browser) before being fixed.

### Fixed
- **The whole answer vanished when the model started its line with the user's name or another participant's** (`Kaua: hi, how are you?`, imitating the history format): ASTA cut "everything from the other person's line on" and nothing was left, so the avatar "did not answer". Now, if only empty would remain, it removes the label and keeps the line; invented lines from the other person in the middle of the text are still cut.
- **There was no way to stop an answer in progress.** The send button now turns into **Stop** while the avatar answers: speech is interrupted, the "typing" bubble disappears and **nothing half-written is saved** in the history.
- **The screen was pulled down on every received piece**, even when you had scrolled up to read the history (mainly in free group conversation). Now it only follows if you are at the bottom; if you scrolled up, the **↓ New messages** button appears. Sending a message of your own always takes you to the bottom.
- **The conversation title stayed stuck on the avatar's old name.** Conversations without a chosen title now use the avatars' current name (a title you chose is kept); when saving *Configure conversation*, the side list updates immediately.
- **What you typed and did not send was lost** when switching conversation. The draft is now kept per conversation and comes back when reopened; the field respects the 6,000-character limit (before, text beyond that was silently cut).
- **Conversations with more than 8 avatars were silently cut** (the avatar list and the "New conversation" window allowed selecting more). Now the limit of 8 shows in the selection and the API answers with a clear error.
- When leaving the conversation, the `visibilitychange` listener stayed registered (one more every time the screen opened); it is now removed.

### Added
- **Actions on each message** (appear on hover or keyboard focus): **copy**, **edit** (in place; Enter/Ctrl+Enter saves depending on your send key, Esc cancels) and **delete**; on the last answer, **Answer again** — discards that round's answer(s) (in a group, all of them) and generates another from your last message, without duplicating it. Editing/deleting while the avatar is answering is refused with a notice (the edit applies to the next answers, since the history is resent to the model).
  - API: `POST /api/avatar-chats/<id>/regenerate` (SSE, `removed` event), `PUT` and `DELETE /api/avatar-chats/<id>/messages/<mid>`.
- **Memories:** besides "Forget everything", you can **forget a single memory** and **teach the avatar something** ("my birthday is in March"). API: `POST /api/avatars/<id>/memory` and `DELETE …/memory?index=N`.
- "Showing the last 200 messages" notice on long histories.

### Tests
- Label at the start of the line; redoing the answer (one-on-one and in a group, without duplicating the user's message, with no message to redo); editing and deleting (including refusal during an answer and ids from another conversation); memories; limit of 8; titles that follow the name. In the browser, with a simulated slow local server: stopping in the middle (button, bubble and history), answering again, editing, deleting, draft, smart scrolling, memories and renaming.

### Note
- I could not exercise voice conversation (microphone and synthesis) nor a real AI model here: the review of those parts was by reading the code, with no obvious problems beyond those listed.

## [0.3.2] — 2026-11-05

### Fixed
- **Creating an avatar from a photo/artwork stopped at the Analyst with «'url' field must be a base64 encoded image»** (seen with LM Studio). Local vision servers (LM Studio, Ollama, llama.cpp) reliably accept only PNG and JPEG and refuse the rest — GIF, WebP… — with this error; before, ASTA sent the image as it was and any refusal took down the whole creation. Now:
  - **the image type comes from the bytes**, not the name: a PNG declared as JPEG (or the reverse) is sent with the right type — this also applies to Claude, which refuses when the declared type does not match;
  - **on local servers, images that are not PNG/JPEG are converted to PNG** (first frame, with `ffmpeg` when it exists); with no way to convert, the image is left out with a note in the text instead of causing an error;
  - **if the server refuses the images anyway** (format, model without vision, error message about image/`url`/base64…), ASTA **repeats the call with text only** — in chat and in creation (also with streaming);
  - in the pipelines, this becomes a **warning** in the result (*"avatar_analyst: 1 image(s) could not be sent to the provider (unsupported format or model without vision); continued with text only"*) and the creation goes on (the look comes from the text and the image's dominant colors), instead of failing. Cloud providers keep receiving all formats.
- Tests: a simulated "demanding" local server (accepts only PNG/JPEG in a data URL and answers with the real error) covers GIF conversion, the real type of the bytes, an image with no possible conversion, total refusal with a text-only retry (normal call and streaming), an untouched cloud provider, Claude with the right type and avatar creation from a photo finishing with a warning.

### Note
- I do not have a real LM Studio here: the cause was inferred from the error message and from what these servers accept, and the fix covers the likely paths (format, wrongly declared type and general refusal). If the not-sent-image warning appears, the loaded model probably **has no vision** (it must be a "VLM" model, such as Qwen-VL, Gemma 3 or LLaVA) — creation continues, just without seeing the photo.

## [0.3.1] — 2026-11-05

### Added
- **New relationships for avatars: girlfriend, boyfriend, wife and husband** (`girlfriend`, `boyfriend`, `wife`, `husband`). They appear in the creation box (*Relationship:*), in the avatar editor and in the lists, and work in the API (`relationship` in `POST /api/avatars/generate` and in the cards). **All of them can be SFW or NSFW**, like any adult avatar: the content mode is still chosen separately (`content`), and the fixed rule applies to both — no sexual content involving minors.
  - The chat prompt describes each relationship: girlfriend/boyfriend/partner are affectionate, attentive, playful and romantic; **wife/husband** talk like someone sharing life with you (home, routine, plans), in an intimate and committed way.
  - **Gender is suggested by the relationship** when the card does not state a gender (girlfriend/wife → female; boyfriend/husband → male); what the card says always wins.
  - The AI-free generator (Demo) recognizes the relationships in the request — "a wife called Marta", "my husband Theo", "my girlfriend Nina"… — and writes each one's first message and replies. The agents' prompts (analyst, designer, system-prompt writer and reviewer) also know the four.
  - "Partner" (`partner`) still exists as a generic romantic relationship; old cards do not change.
- Character Card V2 export carries the new relationship (`extensions.asta.relationship`).

### Rules that still apply
- **A minor never has a romantic or marital relationship** (including the new ones): they become a friend, always SFW and platonic — by the age field or by any text in the card.
- A **real person** is still always SFW (the relationship is kept, sexual content does not exist).

### Fixed
- The *Relationship:* selector in the creation box cut the text ("Relationship: automatic" showed up half-visible); the maximum width increased to fit the options.

### Tests
- New and old relationships, suggested gender, SFW/NSFW on all, minor (by age and by text) and real person, chat prompts, Demo recognition (Portuguese and English), generation through the API in SFW and NSFW, editing, V2 export and, in the browser, the options in creation and in the editor, uncut text and the label in the list.

## [0.3.0] — 2026-11-05

General update focused on **personalization** and **user experience**. Everything that already worked stays the same: the default is exactly the usual look (dark theme, white accent, size 100%).

### Added — personalization (Configuration → new **Appearance** tab)
- **Dark / light / automatic theme.** Automatic follows the system and changes live. The appearance is applied by a script in `<head>` (`boot.js`) with the last stored value, **before the first frame** — no flash from dark to light. All the CSS was migrated from fixed colors to variables; the Canvas node graph, the video editor and the image viewer are **always dark** on purpose (like media editors).
- **Accent color:** 6 presets or any color; buttons, selections, progress bars and your bubble in the chat follow the color, with black or white text chosen by contrast.
- **Comfort:** interface size (90–150%, with no extra scrollbars), **compact** density, font (system, serif, monospace), chat text size and **reduce animations** (also respects `prefers-reduced-motion`).
- **Usage:** language (moved to the Appearance tab), **send key** — Enter or **Ctrl/⌘+Enter** — in the avatar chat and in the creation box (Shift+Enter and IME text composition are still respected), **start screen** (Main, any screen or "the last one I used") and keyboard shortcuts on/off.
- **Sidebar:** hide the screens you do not use (Main and Configuration never disappear; the current screen always shows; hidden ones remain reachable by search).
- **Backup and defaults:** *Export settings* (JSON **without API keys or tokens** — voices, Hugging Face and providers come out without secrets), *Import settings* (known sections only, validated values, **never** replaces the importer's keys) and *Restore appearance defaults* (never touches keys, avatars or projects). API: `GET /api/settings/export`, `POST /api/settings/import`, `POST /api/settings/reset`.
- Preferences live in `settings.ui` and are **validated** (`asta/uiprefs.py`): an invalid value, through the API or manual editing of `settings.json`, goes back to the default instead of breaking the interface (color only in hex, scale only among the allowed ones, etc.).

### Added — experience
- **Command palette (`Ctrl/⌘+K`)** and a *Search…* button in the sidebar: go to any screen or Configuration tab, chat with/edit an avatar, open a project or canvas, or run actions (new avatar, new creation, toggle theme, collapse the bar, export settings, see shortcuts, reload). Search ignores accents and case, navigation by arrows/Enter/Esc, announced as a dialog with a list of options.
- **Shortcuts:** `Alt+1…7` (screens), `Alt+B` (sidebar), `Alt+T` (theme), `?` (help with all shortcuts). They can be turned off; `Ctrl+K` always works.
- **First-time welcome:** choice of theme, color and language with live effect and the AI status (ready, or a Demo-mode notice with *Set up AI*). It shows up **only on a fresh install** (nothing created); anyone who already uses ASTA never sees it, and it can be revisited in *Appearance → Review the welcome*.
- **Accessibility:** focus ring visible only on keyboard, *Skip to content* link, automatic accessible name on icon-only buttons, dialogs with `role="dialog"` and focus returned to whoever opened them, announced notices (toasts), page title per screen (`ASTA — Library`…), `aria-current` in the sidebar.
- New screens and texts have an English translation.

### Fixed
- **Library → "Open" on a canvas** led to the canvas list instead of the editor (the address lacked `/edit/`).
- The chat's "Demo mode" strip showed the reason in Portuguese even with the interface in English.

### Tests
- Preferences (defaults, valid and invalid values, color, idempotence), sanitized saving/loading, export **with no secrets at all**, safe import (does not replace keys, ignores unknown sections, rejects wrong files), round trip between installations, restore defaults (voice and providers refused).
- Browser: theme (including applied before the first frame and live `auto`), color and contrast, scale without scrollbar, density, font, animations, sidebar, start screen and title, palette (open, search avatar, Enter, Esc), shortcuts (on/off), Ctrl+Enter vs. Enter in chat, export/restore and accessibility; welcome on a fresh install **and** its absence for those who already use it.

### Note
- I reviewed the light theme with screenshots of the main screens (Main, Configuration, Avatars, chat, Canvas), but **not every screen in every state**: if any color looks bad in light, the dark theme (default) is not affected.
- The interface size uses the CSS `zoom` property (Chrome, Edge, Safari and Firefox 126+); in browsers without it the adjustment simply has no effect.
- On phone screens, search (`Ctrl+K`) has no button (the bottom bar stayed as it was).

## [0.2.18] — 2026-11-05

Bug review of everything involving **avatars** and **AI providers** (cloud and local). Each item below was reproduced before being fixed and has a regression test (`tests/test_ai_regressions.py`).

### Fixed — AI providers
- **Local servers did not answer with a system proxy.** With `HTTP_PROXY` set (corporate network/VPN), calls to Ollama, LM Studio and llama.cpp on `127.0.0.1` went through the proxy, which cannot see the requester's machine. Now `localhost`, `127.x`, `::1`, private networks (192.168.x, 10.x, 172.16–31.x) and `.local` names are reached directly.
- **An address typed the usual way broke:** `localhost:11434` (without `http://`) gave the incomprehensible error *"Could not connect to completions: unknown url type"*; `http://localhost:11434` (Ollama without `/v1`) gave 404. Now ASTA completes the `http://` and, on local servers, the `/v1`; a truly invalid address shows *"Invalid address…"*; and the connection-failure message names the right server.
- **An error in the middle of streaming was swallowed** (the answer simply came back empty). Now the provider's error (rate limit, model that dropped…) shows up; on Claude, the streaming error shows the message instead of raw JSON.
- **Answer as a list of parts** (some OpenAI-compatible servers) broke with an internal error; it is now read normally.
- **Claude (Anthropic) with "creativity" above 1** (the interface goes up to 1.5) got a 400 error on every message — the API only accepts 0–1. The value is now capped.
- **An overloaded server took down the avatar's message.** 429/502/503/529 answers are now retried up to 2 times, respecting `Retry-After` (up to 8 s). Exhausted quota or credit (which also comes as 429) is **not** retried, nor are key errors.
- **Local model (embedded GGUF):** (1) long conversations overflowed the context window and the avatar stopped answering — now the history is trimmed (the avatar prompt and the current question stay; the rest goes in from newest to oldest) and `max_tokens` is limited to half the context; (2) an overflow anyway becomes a message with what to do (raise the context window) and, in the pipelines, the agent falls back to rules instead of taking down the generation; (3) llama.cpp errors become provider errors, not loose exceptions; (4) JSON mode now uses llama.cpp's JSON grammar (more reliable agent answers on small models), with a fallback for old versions; (5) the model list showed parts of split models and vision files (`mmproj`).
- **Test button with the Model field empty** secretly tested the saved model (making it impossible to test LM Studio's automatic mode). An empty field now means empty.

### Fixed — avatars
- **An empty answer vanished without notice.** When the model returned nothing, or spent the whole token limit «thinking» (`<think>…</think>`, common on LM Studio/Ollama), the avatar just stopped typing. In a one-on-one conversation the notice with the cause and what to do now appears (*"…spent the whole answer limit thinking… raise the Maximum tokens per answer"* or *"the provider returned no text…"*); in a group the avatar stays quiet.
- **History starting with the avatar's greeting** broke models with a strict template (Gemma, Mistral…: *"roles must alternate user/assistant"*). The conversation now always starts with the user.
- **An interrupted line was saved cut off in the history** (when you wrote in the middle of free conversation). It is now discarded.
- **Bold prefix** (`**Aya:** hi`) left a stray `**` in the message.
- **Unaccented mentions** were not recognized ("julia" did not call "Júlia"; "theo" did not call "Théo"): the turn director now ignores accents and case.
- **Minor rule — more complete detection.** It only caught "15 years old", "tem 15 anos" and "idade: 15"; it let through "uma garota de 15 anos", "jovem com 17 anos", "chica de 15 años", "15 aninhos", "criança", "adolescente", "colegial", "high school student", "menos de 18 anos"… Now all of them become SFW and friend-only. Ages of **other** people ("tem 2 filhos de 12 anos", "her 12-year-old son") and durations ("casados há 12 anos", "10 anos de experiência", "um casamento de 12 anos") do not cause a false positive.
- **Cards imported from SillyTavern/Janitor/Chub** come with `{{char}}`, `{{user}}`, `<BOT>`, `<USER>` and `<START>`, which went literally to the model. They are now replaced by the avatar's and the user's name (in the prompt and in the greeting); the stored card keeps the macros, so export stays compatible.
- **Deleting an avatar left ghost conversations** that, when opened, broke the chat screen. Now one-on-one conversations disappear, and in a group the avatar leaves (with their lines) and the conversation continues; the screen also goes back to the list if such a conversation is opened.
- **Invalid settings** (`history_turns`, `max_tokens`, `temperature`… with text or out of range, through the API or manual editing) broke every message; they are now limited. Same for an invalid `count` in avatar generation.
- **An unexpected model error cut the answer** in the middle of streaming; it now becomes a notice in the conversation. Malformed bodies on the conversation routes gave a 500 error; now 400.
- The system-prompt pipeline ignores a `system_prompt` that is not text (list/object), instead of saving `['a', 'b']`.

### Note
- In the cases I exercised, I found no problems in: chat rendering (there is no XSS: the model's text is inserted as text), PNG card import, long-term memory and avatar creation with malformed model answers — these flows were exercised and behaved well.
- The real local model (`llama-cpp-python`) and a real LM Studio/Claude are not in this environment: the tests use a simulated `Llama` (with the same context error as the original) and simulated HTTP servers.

## [0.2.17] — 2026-11-05

### Added
- **First-class LM Studio support to chat with avatars** (and for generation and NPCs). Before, LM Studio was just an OpenAI-compatible address you filled in by hand; now ASTA really talks to it:
  - **Automatic detection:** ASTA looks for the LM Studio server at `http://127.0.0.1:1234` (or the configured URL, with or without `/v1`; also on another machine on the network) and, with the *Characters* role on **Automatic**, uses LM Studio when it is running **with a model loaded** — before the embedded GGUF model and after the configured generation provider. The query has a short cache (8 s) so a turned-off server does not delay messages.
  - **Models:** uses the native `/api/v0/models` API (loaded/not-loaded state, `llm`/`vlm`/`embeddings` type, quantization, context) and falls back to `/v1/models` on old versions. Only **chat** models appear (embedding models are hidden), loaded ones first.
  - **Without choosing a model**, it uses the one loaded in LM Studio; **vision is turned on automatically** for `vlm` models (the user's manual choice still wins); optional API key.
  - **Errors that teach:** server off → *"Could not talk to LM Studio… go to Developer → Start Server (or lms server start) and load a model"*; no model loaded → lists what is installed; nonexistent model → specific message.
  - **Configuration → Providers → LM Studio:** detects the server (on/off indicator), lists the models (`●` loaded, `○` installed, `👁` vision), picks with one click and has the **Use for avatars** and **Use for generation** buttons; there is no manual vision box in that card anymore.
  - API: `GET /api/lmstudio` (state, models and what will be used); `asta doctor` shows LM Studio's state.
- **Reasoning hidden in chat:** models that write their reasoning together with the answer (`<think>…</think>`: Qwen3, DeepSeek R1…, very common on LM Studio and Ollama) no longer show that part in the avatars' messages, not even during streaming.
- Tests: a **fake LM Studio server** (native API, old API, with key, streaming) covers detection, the filtered list, the loaded model, vision, the user's choice, error messages, automatic choice (before the embedded model), avatar chat end to end and the Configuration card in the browser.

### Note
- There is no real LM Studio in this development environment: everything was tested against a simulated server that follows the API's public documentation (`/api/v0/models` and `/v1/chat/completions`). If any LM Studio version answers differently, the card shows the error and the generic OpenAI-compatible route still applies.
- LM Studio can load models on demand (JIT): when choosing an installed but not loaded model, it is usually loaded on the first message (the first answer takes a while).

## [0.2.16] — 2026-11-05

### Fixed
- **Avatars answered with generic pre-programmed phrases instead of using AI.** Cause: the *Characters (chat and voice)* role was fixed on **Demo** (the rule-based generator, no AI) and only changed if you switched it by hand — even with an AI provider configured in *Generation* or with the local model installed. Now:
  - the role's default is **Automatic** (`active.characters = "auto"`): it uses the **generation** provider if usable (cloud: with a key; local — Ollama, LM Studio, llama.cpp server, custom: with a model) and, if not, the **local text model** (the one chosen in *Hugging Face GGUF* or the pre-installed one, if the file exists and `llama-cpp-python` is installed). The old `demo` value of this role now means the same as Automatic; choosing a specific provider still forces that provider (and, if the key is missing, the error shows up, with no switch to another).
  - **Demo only comes in when no AI exists at all** — and the conversation shows a **"Demo mode: replies are pre-programmed, with no AI"** strip with the reason (for example, *"the local model Qwen3.8… is installed, but the llama-cpp-python library is missing: run asta libs --extras local"*) and the **Set up AI** button. When there is AI, a line says which model is answering ("Answers with … · model").
  - **avatar creation** and the **system-prompt pipeline** use the same rule (before, with Generation on Demo, they created generic rule-based cards); if there is no AI, creation proceeds on Demo but returns the notice.
  - 3D-world NPCs (also in the *Characters* role) now follow the same choice.
  - installing the pre-installed model no longer needs to switch the *Characters* role: it stays on Automatic and already follows the local model (only *Generation* is switched, as before).
  - API: `GET /api/avatars/engine` (which AI answers and, if Demo, why) and the SSE event `provider` at the start of each conversation round.
- Tests: provider choice (default, following generation, missing key or model, explicit choice respected, local model with and without the library, old `demo` value), conversation answered by the configured AI (simulated server) and conversation on Demo stating the reason, creation using the AI, and the notice strip in the browser.

### Note
- If you **want** Demo on purpose (trying without AI), just have no usable provider: there is no longer an option to force Demo only in conversations.
- To have free, local AI: install the pre-installed model (`asta models install`) **and** the library (`asta libs --extras local`, which compiles native code); without the library, the notice strip says exactly that. I could not exercise a real local model here (no `llama-cpp-python`): the model choice was tested, not generation with it.
- Answers from a small model still depend on its quality and on the avatar's system prompt (hence the system-prompt pipeline).

## [0.2.15] — 2026-11-05

### Added
- **Avatar creation also uses the system-prompt pipeline.** After Analyst → Designer → Reviewer, a new **System prompts** step runs the *Analyze → Generate → Review → Deliver* pipeline (the same as the editor's, from 0.2.14) **on each created avatar**, and the final text replaces the Designer's. The Designer's text is not discarded: it goes in as a starting point ("keep what is good"), together with the original request and, in groups, the other avatars' names (`knows`) so each one knows who they live with. Progress shows on the creation screen (*System prompts — Ana (1/2)*, then how many were corrected by the reviewer).
- The fixed rules apply in this step as well, by code: if the pipeline concludes the character is a **real person** or a **minor**, the avatar becomes SFW (a minor also becomes friend-only), even if the user and the Designer asked for NSFW; adult fictional characters keep NSFW. The pipeline's analyst can mark "real" even when the creation's analyst marked "fictional" (the more restrictive wins); the type chosen by the user still outweighs the model's guess.
- To skip the step (faster, fewer model calls): `prompt_pipeline: false` in `POST /api/avatars/generate`. It costs about 3 extra calls per avatar.
- Demo mode (no AI): the text already written is kept and only appearance, who the avatar knows, instructions and the real-person note are added, without repeating what is already there (pressing *Generate* again does not stack text).
- Tests: each avatar has its own analysis/generation/review, the Designer's draft and the group reach the writer, one avatar's correction round, turning off the step, rules (real and minor) after the pipeline and Demo mode.

### Note
- A creation with several avatars is slower with a real AI model (more calls). The pipeline with a real model was not exercised here: it was tested with a scripted provider and with Demo mode.

## [0.2.14] — 2026-11-05

### Added
- **Avatar system-prompt generation pipeline: Analyze → Generate → Review → Deliver.** In the avatar editor, the **Generate the system prompt with AI** card (name, personality, appearance and optional instructions) runs four steps, with each one's progress on screen:
  1. **Analyze** — works out who the character is (any kind: original, from a work, historical, robot, creature…; **real or fictional**; age; way of speaking; relationship with the user; limits; what SFW/NSFW mode allows; language);
  2. **Generate** — writes the system prompt from the analysis, keeping what the creator had already written that was good;
  3. **Review** — checks coherence with the card, voice, language, length, not mentioning being an AI and the fixed rules; if it fails, the writer fixes it **once** and the review runs again;
  4. **Deliver** — deterministic step: removes markdown fences, **applies the safety rules by code** (what the model says does not get around them) and, with `apply`, saves to the avatar.
  - Invalid or empty answer from an agent → rule-based fallback: it also works in Demo mode, without AI.
  - API: `POST /api/avatars/system-prompt` (job with SSE; `avatar_id` or `draft`, `instructions`, `content`, `character_type`, `detail`, `apply`).
- **Any type of character, real or fictional, in SFW and NSFW** — with a new fixed rule. New **character type** field (`character_type`: `fictional` | `real`) in the card, in the editor, in the creation box (*Type: automatic*, *Fictional character*, *Real person (always SFW)*) and in the generation API:
  - **fictional** (original or from a book/film/game/anime/myth…): SFW or NSFW, as long as adult;
  - **real person** (living or historical, famous or not, or the one in a photo): can be created, but **always SFW** — ASTA **does not create sexual content about real people** (they did not consent). The prompt presents them as a *respectful fictional interpretation*, never as the real person, without inventing private facts, scandals or lines as if they were real. The rule applies even to imported or hand-edited cards (`normalize_avatar` forces SFW) and in the conversation (the chat prompt also reminds of it);
  - the analyst can mark it on its own (photo of a person → real); **the user's explicit choice outweighs the model's guess**;
  - minors are still always SFW and platonic, in any type.
  - The exported Character Card V2 carries the type (`extensions.asta.character_type`) and it is read on import.
- Tests: real/fictional card and the rule in the V2 card, chat prompt, the full pipeline (Demo and with a scripted provider: steps in order, `apply`, real forced to SFW, minor forced to SFW even if the model disagrees, user's choice vs. model's guess, reviewer's correction round, final rejection, garbage/empty answers), the API and avatar creation (real = SFW, fictional = NSFW), and the editor in the browser.

### Note
- **Real person + NSFW does not exist**, by choice: if you ask for NSFW for a real person, ASTA creates the avatar in SFW and warns. This complements the old rule for photos (which were already SFW); adult fictional characters can still be NSFW.
- ASTA cannot confirm by itself that a typed name belongs to a real person: it depends on the analyst (model), the photo or your choice in *Character type*. If it is a real person, mark *Real person*.
- Avatar creation (Main → Avatar) still uses the earlier Analyst → Designer → Reviewer pipeline (now also with the character type); the new system-prompt pipeline is the one in the avatar editor and the API.

## [0.2.13] — 2026-11-05

### Fixed
- **Configuration kept showing "error loading dynamically imported module: …/js/quant.js"**, even after reloading the page and restarting ASTA. The `quant.js` file (labels for model quantizations) had the same name as a known tracking script (Quantcast, `quant.js`) that **ad and tracker blockers** — extensions such as uBlock Origin/AdBlock and Firefox's tracking protection — block by name. The browser refused only that file and the Configuration screen (which imports it) would not open; the server never had a problem. The file is now called **`model_labels.js`** (same content) and loads normally, even with those blockers on.
- The screen-load failure message (from 0.2.12) now also mentions that a **blocking extension** may be blocking a file, with what to do (disable for `localhost`).
- Tests: no WebUI file may use a known tracking-script name (`quant.js`, `analytics.js`, `track.js`, `pixel.js`…), and the browser recovery tests now block `model_labels.js`.

### Note
- I do not have your machine's browser or extensions, so **I did not reproduce the blocking**: the diagnosis comes from the error persisting only on that file, after reloading/restarting, and from the name matching an item on known blocklists. If Configuration still does not open after updating, the on-screen message names the file that failed; test with extensions disabled for `localhost` and tell me which file it is.
- The 0.2.12 explanation (page open during an update) was a hypothesis that was not confirmed as the cause of this case; its protections still apply to that other scenario.

## [0.2.12] — 2026-11-05

### Fixed
- **Configuration showed "Something went wrong: error loading dynamically imported module: …/js/quant.js"** instead of opening. The error happens when the browser cannot load one of the screen's files — typically because ASTA was updated (or restarted on a new version) with the page already open, and the page was left with files of a different version from the server's. Now:
  - if a screen does not load, the page **reloads itself once** (no loop) and the screen opens normally;
  - if it keeps failing, a clear message appears (*"Could not load this screen. This usually happens when ASTA is updated with the page open"*) with the **Reload page** button, the Ctrl+F5 / restart `asta` tip and the technical detail, instead of just the raw error;
  - if the server is restarted on a new version with the page open, the page reloads itself;
  - if ASTA was updated on disk but the running process is still the old one, the sidebar warns **"Version X installed: close ASTA and open it again"** (`/api/state` now reports `disk_version`).
- Tests: in the browser, the `quant.js` file is blocked (always, and only the first time) and Configuration must recover or explain; and the on-disk version in `/api/state`.

### Note
- **I could not reproduce the original failure** (here `quant.js` is served normally, even on 500 parallel requests, and the installable package includes all the files), so the exact cause on your machine is not confirmed. The fix covers the most likely scenario (page open with files from another version) and makes any load failure recoverable and explained. If the new message still appears after reloading and restarting `asta`, the technical detail shown in it (and the browser console, F12) say which file failed and why.

## [0.2.11] — 2026-11-05

### Added
- **Library — select several and delete.** The **Select** button (or *Select several* in an item's ⋯ menu) turns on selection mode: each card gets a checkbox, the bar shows how many items are checked and offers **Select the displayed ones** (respects search and filters), **Delete selected** (with confirmation) and **Cancel**. It works with worlds, 2D games, avatars, canvases and models. After deleting, ASTA leaves selection mode and reports how many items were deleted (and how much space was freed).
- **Local AI models in the Library.** Installed GGUF models (text, image, video, sound and music, voice and others — including the pre-installed ones) appear as cards, with type, quantization, size and the *pre-installed* mark; there is a **Local AI models** filter. Pre-installed ones show the catalog name (e.g. *Z-Image*), and support files (VAE, text encoder) appear together with the main model, not as loose models.
- **Deleting local models**, one at a time (the card's *Delete* button) or several (selection mode). A model split into parts is deleted entirely; when deleting a pre-installed one, its support files go with it. If a deleted model is still chosen in the settings, ASTA simply stops finding it — just pick another or download it again.
- API: `GET /api/library/models` (list) and `POST /api/library/models/delete` (`{"items": [{"kind", "name"}]}`; only deletes `.gguf` inside the models folder).
- **Terminal — ASTA asks before downloading the pre-installed models.** The installer (`install.sh`/`install.ps1`) and `asta update` list what is missing (with the size) and ask **yes or no** (`[y/N]`, Enter = no) before downloading. The question also works with `curl … | sh` (it reads from the real terminal). Answering *no* is stored in `~/.asta/preinstalled.json` and is not asked again; `asta models install` (without `--ask`) downloads whenever you want. With no terminal to ask (CI, scripts), nothing is downloaded and ASTA says how to download later.
  - `ASTA_MODELS=all|text|image` answers in advance (downloads without asking) and `ASTA_MODELS=none` skips; before, the default was to download everything without asking.
  - New `asta models install --ask`; what is already installed is still skipped and only what is missing is listed in the question.
- Tests: model listing/deletion (all types, split parts, support files, protection against paths outside the folder), the question (yes, no, remembering the refusal, no terminal, only what is missing), reading the answer with a **real terminal (pty)** with stdin occupied by a pipe, the real `install.sh` calling (or not) `--ask`, and the Library in the browser (models, selection, batch and one-by-one deletion).

### Changed
- The Library subtitle and the counter (now "item(s)") include local models.

### Note
- `install.ps1` (Windows) and reading `CONIN$` could not be run here; the Linux/macOS path (`/dev/tty`) is tested with a pty.
- Deleting a pre-installed model frees the space, but the installer only offers it again if you did not refuse before; to download again: `asta models install` or the button in *Configuration → Local models*.

## [0.2.10] — 2026-11-05

### Changed
- **Terminal — does not reinstall what is already installed.** The installer (`install.sh`/`install.ps1`), `asta update` and `asta libs` now find out what already exists and only update if needed:
  - **Python:** if already installed, it only asks the package manager (apt, dnf, yum, pacman, zypper, apk, Homebrew, winget) whether there is a newer version and reports the result (*"already at the latest version"* or *"updated: X → Y"*).
  - **Environment (venv):** reused; only recreated if Python changed version (as before).
  - **ASTA:** the installer queries the version published on `main` and **does not download or reinstall** if the installed one is the same (or newer). If the query fails (no internet) or the source is different (`ASTA_SOURCE`), it installs normally. `ASTA_FORCE=1` (or `asta update --force`) reinstalls anyway.
  - **Libraries (`asta libs`):** shows what is already installed (with the version) and installs only what is missing; the already installed ones go through a silent check and pip only touches them if there is a newer version. With no internet, what is already installed becomes a warning, not an error. The final summary says which were already installed.
  - **Pre-installed models:** still do not re-download files already in the folder.
  - New `ASTA_VERSION_URL`: changes the address the published version is read from (used in tests and forks).

### Added
- **32K context window on the pre-installed text models.** The pre-installed text model (`empero-ai/Qwen3.8-2B-Distill`, Q8_0) now runs with **32,768 tokens** of context by default, on any hardware tier. The other GGUF text models keep 2,048/4,096/8,192 depending on the hardware.
- **User-adjustable:** **Context window (tokens)** field in the *Hugging Face GGUF (embedded)* provider (*Configuration → Providers*), with suggestions from 4K to 128K, the *Use automatic* button and the effective value shown below the field; the pre-installed model's card shows the *Context 32K* chip. Minimum value 512, maximum ~1M; an invalid value goes back to automatic. The 32K default is computed on the fly and **never saved** in the settings — so installing or updating does not overwrite what you chose. Changing the value reloads the model in memory (`settings.providers.local_hf.n_ctx`).
- Tests: the context (default, adjustment, limits, invalid values, model reload, user configuration preserved), `asta libs` with libraries already installed, `asta update` skipping an already updated ASTA (and `--force`/`ASTA_FORCE`), and the real `install.sh` skipping/downloading ASTA according to the published version.

### Note
- A 32K window uses more memory (RAM) than the 2K–8K ones: on computers with little RAM, reduce the value in the field above. The real loading of the model with 32K context was not exercised in this development environment (no real `llama-cpp-python`); what is tested is the computation of the value and passing it to `Llama(n_ctx=…)`.
- The version check compares the number in `asta/__init__.py`: a fix published on `main` without raising the version is not downloaded by anyone who already has that number (use `ASTA_FORCE=1`).
- `install.ps1` (Windows) could not be run here; the logic was written mirroring `install.sh`, which is tested.

## [0.2.9] — 2026-11-05

### Added
- **Pre-installed models**: ASTA now comes with two local models, downloaded by the installer (and by `asta update`) with the quantization already defined — **only these two, for now**:
  - **text:** `empero-ai/Qwen3.8-2B-Distill` in **Q8_0** (official GGUF `empero-ai/Qwen3.8-2B-Distill-GGUF`, ~1.9 GB);
  - **image:** `Tongyi-MAI/Z-Image` in **Q4_K_M** (GGUF `unsloth/Z-Image-GGUF`, ~3.9 GB), together with the VAE (`ae.safetensors`) and the Qwen3-4B text encoder (Q4_K_M) it needs — ~6.2 GB in total.
- Installation: `install.sh` and `install.ps1` download both (`ASTA_MODELS=all`, default; `none` skips; `text`/`image` chooses one); `asta models install` / `asta models list`; **Pre-installed models** card in *Configuration → Local models* with one-click installation, progress and cancellation; `asta update` also checks. Already downloaded files are skipped, missing parts come back by themselves, disk space is checked first and a failure becomes a warning (ASTA stays installed). API: `GET /api/preinstalled` and `POST /api/preinstalled/install`.
- Once installed, the model is ready: the text one becomes the default generation and characters model and the image one becomes the Canvas image provider (*Local GGUF*) — **only if** you are still on the Demo provider and the library that runs the model is installed (`asta[local]`); otherwise your choice is kept and ASTA says what is missing.
- Z-Image already loads with the right VAE and text encoder and with `cfg_scale 4` and `sample_steps 30` (the node's "extra" field overrides).
- Tests: catalog, installation (with a simulated Hugging Face), automatic configuration, resume, CLI, API, GGUF provider with the catalog defaults and browser.

### Note
- Unlike the other local models (where ASTA asks for the quantization before downloading), on the pre-installed ones the quantization comes defined by the catalog; other quantizations are still available in the search on the same tab.
- ASTA **cannot run Z-Image in this development environment** (no GPU nor the real `stable-diffusion-cpp-python`): download and configuration are tested, but the loading argument names (`llm_path` etc.) and generation parameters follow stable-diffusion.cpp's documentation and may need adjusting depending on the library version — use the node's "extra" field.

## [0.2.8] — 2026-11-05

### Added
- **Avatars from a photo or artwork.** In the Avatar mode of the Main screen, the **Photo/art as base** option uses the attached images as the visual base: you can send **just the image** or add a text prompt and other attachments (documents, conversations…). Choose *one avatar per image* or *one person with all the images*.
  - The image defines the look (`looks`, hair color, appearance) — described by the configured vision model, or by dominant colors in Demo mode — and **becomes the avatar's portrait**; the text only adds name, personality and story. The number of avatars follows the images, not the model's guess.
  - ASTA **does not identify real people by their face**: the name comes from the text or, if there is none, from the file name (`luna_azul-01.png` → "Luna Azul").
  - **Safety:** a photo of a real person, or an image that cannot be identified as artwork, is **always SFW** (with a notice); NSFW only applies when the vision model classifies the image as fictional character art (`source_kind: "art"`). An image that seems to show a minor follows the fixed rule for minors (SFW and platonic, no "aging up").
  - API: `POST /api/avatars/generate` accepts `from_images` and `images_mode` (`each`|`one`).
- **GGUF models by type** (*Configuration → Local models*): **Text, Image, Video, Sound and music, Voice and Other** tabs, each with its own Hugging Face search (filtered by the repository's task), its own folder (`models/` for text — as always —, `models/image`, `models/video`, `models/sound`, `models/voice`, `models/other`), the same quantization selector and its own downloaded list. API: `kind` in `/api/hf/search`, `/api/hf/local` (also `all`), `/api/hf/download` and `DELETE /api/hf/local/<name>`; without `kind`, everything still applies to text.
- **"Local GGUF" provider in Canvas** (image and video): runs quantized GGUF (FLUX, Stable Diffusion, Wan…) through `stable-diffusion.cpp` (`stable-diffusion-cpp-python`, now in the `local`/`all` extra). *Use in Canvas* button on downloaded files; loading options (VAE, encoders…) in the node's "extra" field (`{"load": {"diffusion_model_path": "@model", "vae_path": "ae.safetensors"}}`).
- Tests: avatars from an image (one per image, one person, added text, SFW rule, validation), GGUF types (search, folders, list, deletion), GGUF provider with the simulated library and browser tests of the three flows.

### Note
- For **Sound, Voice and Other**, ASTA only downloads and organizes the GGUF files: there is no embedded engine to run them. GGUF video generation depends on the installed version of `stable-diffusion-cpp-python` offering that function (otherwise the node explains). The GGUF provider was only tested with the simulated library (there is no GPU nor the real library in this development environment).

## [0.2.7] — 2026-11-05

### Changed
- **ASTA always asks which quantization you want before downloading any local model.**
  - **GGUF models** (*Configuration → Local models*): no quantization comes pre-selected (the recommended one is only highlighted); the button stays disabled until you choose and, on click, a confirmation shows the quantization, the size and whether it fits your RAM. The `POST /api/hf/download` API now **requires the `quant` field** (e.g. `"Q4_K_M"`) and answers 400 without it — nothing is downloaded without an explicit choice.
  - **Canvas local models** (*Configuration → Media → Local Hugging Face*): before, first use silently downloaded the default model. Now you choose each type's model and the **precision (quantization): fp32, fp16 or bf16**, seeing the download size of each (with the one recommended for your computer: fp16 with a graphics card, fp32 without). Only the files of the chosen precision are downloaded (`.fp16` variants, no duplicate weights in other formats), with progress and cancellation between files.
  - The Canvas local provider **only loads models you downloaded** (always with `local_files_only` and at the chosen precision); for a model not downloaded, the node's error explains how to download it.

### Added
- Routes `GET /api/media/local/state`, `GET /api/media/local/options?model=` and `POST /api/media/local/download` (requires `precision`).
- Tests: mandatory choice in GGUF and in the API, file selection by precision, refusal of a model not downloaded and browser tests of both flows.

### Note
- Anyone who already used the Canvas local provider needs to download the model once through the new flow (the precision choice is recorded with the download).

## [0.2.6] — 2026-11-05

### Fixed
- **Windows:** after installing, typing `asta` gave *"The term 'asta' is not recognized as the name of a cmdlet…"*. Two causes in `install.ps1`:
  - the installer only wrote the user PATH and asked to open a new terminal; now the command also works **in the current terminal** (when using `irm … | iex`);
  - on an account with an empty user PATH, `$userPath.TrimEnd(';')` failed and, since 0.2.5 (`$ErrorActionPreference = 'Continue'`), that failure passed silently — PATH was never configured. The code now accepts an empty PATH and compares folders ignoring case and trailing slash.
- PATH is now configured **before** installing the libraries (which takes long), so the command exists even if the installer is interrupted at that step.
- If `asta` is still not recognized in the current terminal, the installer shows the command with the full path (`& '…\asta.exe'`) and explains what to do. `install.sh` (Linux and macOS) also shows the full path when the command's folder is not on PATH.

## [0.2.5] — 2026-11-05

### Fixed
- **Windows:** the install/update command (`install.ps1`) failed on Windows PowerShell 5.1 with `NativeCommandError` right after creating the environment (`python.exe : Traceback (most recent call last)` on the line `$old = & $venvPy -I -c "import asta; …" 2>$null`). On that PowerShell version, with `$ErrorActionPreference = 'Stop'`, any text an external program writes to stderr becomes an exception — even with `2>$null` — and, on the first install, `import asta` fails on purpose (ASTA is not installed yet). The installer now uses `'Continue'` and checks the errors that matter through `$LASTEXITCODE` and `-ErrorAction Stop`; the same goes for the calls to `pip`, `winget` and Python detection. A test ensures the global `Stop` does not come back.

## [0.2.4] — 2026-11-05

### Changed
- **Installing and updating now also installs and updates Python and its derivatives.** `install.sh` (Linux and macOS) and `install.ps1` (Windows):
  - install **Python 3.9+** if it is missing and **update it** on every run, using the system package manager — `apt`, `dnf`/`yum`, `pacman`, `zypper`, `apk` or Homebrew; `winget` on Windows. On Linux this includes `python3-venv` and `python3-pip`. It may ask for the password (`sudo`);
  - recreate ASTA's private environment when the new Python is a newer version (the libraries are reinstalled afterwards) or when the old environment is broken;
  - update the environment's `pip`, `setuptools` and `wheel` before installing ASTA and its libraries.
- `asta update` now runs the official installer (downloaded from the repository), so it updates **Python, ASTA and libraries** at once; on Windows the installer continues in a new window. On manual installs (`pip`, editable mode) or with no internet, it updates `pip`/`setuptools`/`wheel`, ASTA and the libraries and warns that the system Python is not managed by ASTA.
- `ASTA_PYTHON=keep` (and `asta update --no-python`) keeps the system Python as it is; `asta update --core` updates only ASTA and the Python tools.
- `asta doctor` also shows the `pip` and `setuptools` versions.
- Package metadata in the current setuptools format (SPDX license, `setuptools>=77`), without the deprecation warning during installation.

### Added
- `sh install.sh --python-only` (or `ASTA_STEP=python`, and `$env:ASTA_STEP = "python"` on Windows): only installs/updates Python and its tools.
- Installer tests with a simulated package manager (missing Python, update, `keep` mode, recreated environment) and of `asta update`; CI uses `ASTA_PYTHON=keep` in the installer job.

## [0.2.3] — 2026-11-05

### Changed
- **Installing and updating now also installs and updates all of ASTA's libraries.** `install.sh`, `install.ps1` and `asta update` now install/update, by default, the three groups of optional libraries — `docs` (more precise PDFs), `media` (local image, video, sound and voice models for Canvas) and `local` (embedded GGUF models) —, always together with their dependencies (`--upgrade-strategy eager`). Before, this only happened with `ASTA_EXTRAS` set and `asta update` did not touch the libraries.
- A library that fails (for example, `llama-cpp-python` without a compiler) becomes a warning with a hint on how to try again: ASTA and the other libraries still get installed.
- `ASTA_EXTRAS` now accepts `all` (default), `none` (only ASTA, without dependencies) or a list (`docs,media,local`).

### Added
- `asta libs [--extras …]` command: installs/updates only the libraries, reading the list from the installed ASTA version (so new libraries from future versions come in by themselves).
- `asta update --core` (only ASTA) and `asta update --extras …` (choose the libraries).
- `asta[all]` extra in the package (all libraries at once).
- Command-line and installer tests; CI installs with a light optional library and also only the core.

## [0.2.2] — 2026-11-05

### Added
- **Quantization choice** for local Hugging Face models (*Configuration → Local models*): ASTA identifies each GGUF file's quantization (Q2_K … Q8_0, IQ*, F16/BF16…), shows the expected quality, marks which ones fit your RAM and **recommends** a balanced option (usually Q4_K_M); you choose which to download and the button shows the size.
- Models split into parts (`-00001-of-00003.gguf`) are downloaded together, with summed progress, and show up as a single option; already downloaded parts are reused when resuming. Repositories with missing parts and vision projector files (`mmproj`) do not enter the quantization list.
- The **Downloaded** list shows each model's quantization and number of parts; deleting a split model removes all the parts. Before downloading, ASTA checks free disk space.
- API: `GET /api/hf/files` returns `quant`, `bits`, `quality`, `parts`, `files`, `sizes`, `fits` and `recommended`; `POST /api/hf/download` accepts `files` (and `sizes`), keeping the old `file` field.

## [0.2.1] — 2026-11-05

### Changed
- The **Characters** and **Worldbuilding** sections left the sidebar and now live inside **Worlds**, as tabs (`Worlds`, `Characters`, `Worldbuilding`; routes `#/worlds`, `#/worlds/characters` and `#/worlds/worldbuilding`). The old links (`#/characters` and `#/worldbuilding`) still work and open the matching tab.
- The sidebar has seven items: Main, Worlds, Avatars, 2D games, Canvas, Library and Configuration.
- README (English and Portuguese) updated with the new organization.

## [0.2.0] — 2026-11-05

Project overhaul: besides 3D worlds with agent NPCs, ASTA is now an **open source AI creation hub** with four modes — 3D worlds, **avatars**, **2D games** and media **Canvas** — all from the same prompt box and saved in the same library.

### Added

**Avatars** (text and voice conversation, inspired by Janitor and SillyTavern)
- Full avatar cards (`asta.avatar.v1`): relationship (friend, boyfriend/girlfriend, companion, mentor, other), age, gender, personality, appearance, scenario, first message, speech examples, optional system prompt, voice, how much they talk in groups and portrait (image upload or a drawn face that changes with mood). Imports/exports Character Card V2 (JSON and PNG).
- AI creation from text, images or any attached file — one avatar or several at once (Analyst → Avatar Designer → Reviewer → Save pipeline).
- **Single** (you ↔ 1 avatar) and **group** (you ↔ up to 8 avatars) conversations with a turn *director*: mentions, how much each one talks and **free conversation**, in which the avatars keep talking to each other without you asking (with a limit of consecutive lines and a pause).
- *Streaming* answers; spoken answers, dictation and hands-free voice conversation (browser voice or OpenAI-compatible STT/TTS servers); short- and long-term memory that the avatar itself notes down.
- SFW or NSFW per avatar. Fixed rule: avatars are adults; a card that describes a minor is never "aged up" — it stays strictly SFW and platonic (friend, never partner).

**2D games** (five genres, generated as validated data — `asta.game2d.v1`)
- Visual novel (Ren'Py style), RPG (RPG Maker style), platformer, side scroller (shooter and runner) and point & click.
- Attachments → Game analyst → Game designer → Reviewer → Packager pipeline, with rule-based generators as a fallback (a playable game always comes out).
- Pure-JS 2D engines (`asta/runtime2d`): procedural vector art, synthesized audio, touch controls, save/load; conditions with a safe grammar (no `eval`), identical in Python and JavaScript.
- Guarantees by test on the built-in generators: platformer levels are completed by a robot, the RPG is winnable and visual novels have branches and endings; everything the AI writes goes through validation and repair (start, goal, ground, checkpoints, broken references, reachable endings).
- ZIP delivery (`Game.html`, `code/`, `data/`, `ui/`, `prompts/`), game right inside ASTA, updating the same game and rebuilding with the latest engine.

**Canvas** (simple node flow for images, videos, sounds and voices)
- Node editor with pan/zoom, typed connections, results in the nodes themselves, execution with live progress and hash cache (only what changed is generated again). Several canvases, one per project; ZIP download.
- Nodes: Text, AI Text, Media, Image (generate/edit), Video, Sound, Voice, Transcribe, **Style Prompt**, **Style Folder** and **Editor**.
- **Style Prompt** and **Style Folder** apply to the whole project (or only where connected); the Style Folder is described by the configured vision model or by dominant colors.
- **Editor** (simulates a video editor): video/audio/text tracks, media bin, live preview, split/cut/move, fades, opacity, position, subtitles and MP4 export via `ffmpeg`; clips linked to nodes follow their latest output.
- Media providers: OpenAI (includes image editing, TTS, Whisper and Sora), OpenAI-compatible servers, ElevenLabs, Google (Gemini/Veo), Stability AI, Replicate, Hugging Face Inference, Stable Diffusion WebUI (local), local Hugging Face models (`pip install "asta[media]"`) and offline **Demo** (procedural images, synthesized sounds, Ken Burns video).
- Starter templates (Text → Image, → Video, With style, Full scene) and the composer's attachments become nodes when creating a canvas from the hub.

**Hub and interface**
- Main screen with the four modes; unified library (3D worlds, avatars, 2D games and canvases) with type filter, search and tags.
- Configuration: **Media** tabs (default provider per type, keys, addresses, models, connection test) and **Avatars and games**.
- Interface fully translated to English; a test guarantees no phrase is left untranslated.
- Phone navigation; HTTP *Range* support for video and audio.

**Tests**
- Suite grown from 40 to over 130 tests: avatars, 2D games (including engines in Node and a platformer robot), Canvas (schema, storage, adapters with a simulated server, engine, Editor with `ffmpeg`, API), translations and optional browser tests (Chromium via Playwright).

### Changed
- The **README is now in English** (`README.md`); the Portuguese version is in `README.pt-BR.md` (the old `README.en.md` was removed).
- The generation pipelines now share an executor (`Runner`) and the routes got their own modules per feature.
- Library projects gain the `kind` field (`world`, `game2d`); v0.1 projects keep working as 3D worlds.
- `asta doctor` also reports the optional Canvas components.

### Security
- Media sent to Canvas is identified by **content**, never by name or `Content-Type`; served files have their path validated.
- Media-provider keys use the same vault as the others (`settings.json`, permission `600`) and never go back to the browser.

## [0.1.0] — 2026-11-04

First version: the complete ASTA, end to end.

### Added

**WebUI** (black, minimalist, inspired by Grok; PT-BR and English)
- Left sidebar with `Main`, `Worlds`, `Characters`, `Worldbuilding`, `Library` and `Configuration`.
- Multimodal prompt: text + attachments of any kind (drag-and-drop, paste, upload with progress).
- Live follow-up of the agents (SSE); generation continues if you leave the screen.
- Character cards (name, tags, system prompt, voice, appearance) and worldbuilding cards (name, system prompt), with create/duplicate/import/export and AI-assisted creation. Imports Character Card V2/V3 (JSON and PNG).
- Library with search, automatic and custom tags, versions and updating the same game several times.
- World editor (biome, weather, time, NPCs, audio, interface, quality) that generates new versions without spending AI.

**Multi-agent generation**
- Multi-step pipeline: Analyst → Planner → Characters → Architect → Sound & UX → Reviewer (with review rounds) → Packager.
- Deterministic validation of everything the models produce and a hardware budget (low/medium/high); per-agent fallback to always deliver a playable world.
- Attachments: text/code, `docx`, `odt`, `pdf`, `xlsx`, `ods`, `csv`, `pptx`, `odp`, images (vision), audio (transcription via STT) and videos (frames + audio via `ffmpeg`).
- ZIP delivery: `code/`, `chars/`, `sound/`, `prompts/`, `ui/ux/`, `Game.html`, plus the world's `README.md` and `CHANGELOG.md`.

**World engine** (HTML + CSS + JS + three.js r159, works straight from `file://`)
- Procedural terrain with 10 biomes, water, sky with day/night cycle, stars, clouds, rain/snow/fog/storm, instanced vegetation and rocks, grass around the player, 17 structure types with collision and night lighting.
- First and third person, minimap, compass, touch controls.
- Adaptive quality: detects the hardware and adjusts resolution, shadows and distance in real time.
- 100% procedural audio: ambience by biome/weather, generative music by mood, footsteps and thunder.
- Persistence: position, time, memories and conversations saved and restored.

**AI characters**
- Text conversation (click or `E`) with *streaming*, short- and long-term memory, and actions (`follow`, `stay`, `go to`, `wave`, `dance`, `flee`).
- Voice conversation in any language: browser Web Speech or OpenAI-compatible STT/TTS servers (includes local models).
- Optional autonomy: NPCs decide on their own what to do.

**Providers**
- Claude (native API), ChatGPT, Grok, Gemini, OpenRouter, Hugging Face Inference, Ollama, LM Studio, llama.cpp server and any OpenAI-compatible endpoint.
- Hugging Face GGUF models: search, download with progress/resume and embedded execution (`asta[local]`).
- Offline Demo provider to try without a key.

**Installation and platforms**
- Windows, macOS and Linux. A single command installs **and** updates (`install.sh` / `install.ps1`); `asta update` also updates.
- Core with no dependencies beyond the Python standard library (3.9+).

**Security**
- Listens only on `127.0.0.1` by default; protection against DNS rebinding and CSRF; API keys never exposed to the browser; path validation.

[Unreleased]: https://github.com/KMC1525/ASTA/compare/v0.8.6...HEAD
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
