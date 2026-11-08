### Krita (digital painting)
- Open: `open_app` "Krita" (give an image/.kra path to open it). Krita is slow to start: `wait` 6–10 s, then screenshot.
- New canvas: `ctrl+n`, set Width/Height in the dialog fields (click, `ctrl+a`, type), confirm with the "Create" button or `Return`.
- Export as PNG/JPG: `ctrl+shift+e` is "Export…" in recent versions; otherwise File → Export. Save the editable file with `ctrl+s` (.kra).
- Command line works without the GUI for conversion: `run_program` krita with `--export --export-filename <out.png> <in.kra>`.
- Tools by shortcut: `b` brush, `e` eraser, `ctrl+z` undo, `[` / `]` brush size. Painting by dragging is not possible with click alone: for drawings, prefer generating the image with other tools and opening it in Krita.
