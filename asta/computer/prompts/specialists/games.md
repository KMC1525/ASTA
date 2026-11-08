## Specialist guide: games
- Find the game first: `list_games` with part of its name (Steam, Lutris and the user's game folders are listed). Launch with `launch_game` using the **id** from the list. If two games match, pick by the id the user's wording points to; in Ask mode you may use `ask_user`.
- A game "on a folder": use `launch_game` with `path` (an executable, AppImage, .app or a web game `index.html`). Windows games on Linux need Wine/Proton/Lutris; if that is missing, say so.
- After launching, `wait` 5–10 seconds (games are slow), then take a screenshot to confirm the window or launcher is open. Steam may show a launcher or update dialog first.
- "Play" means: get the game running to a playable state (main menu, or the save/level the user named) and report. Playing a whole game for a long time is not possible; do short, concrete in-game actions with keys (`press_keys`: arrows, `Return`, `space`, `Escape`) and verify with screenshots. Do not make purchases, change accounts or join online matches unless the request says so.
- Close nothing the user had open. When asked to stop, close the game window with its own menu or `alt+F4`.
