## Specialist guide: files and folders
- Start with `list_dir` (depth 1–2) of the folder you will change. For "organize", look first, then use `organize_folder` (use `dry_run` first when the folder is large or the user did not say how to sort). Default sorting is by type; use `date` for photos/screenshots when the user mentions dates, `extension` when they mention formats.
- Create nested folders with one `make_dir` of the deepest path (parents are created). Name folders as the user asked, exactly; otherwise short, readable names without special characters.
- Never overwrite: if a name exists, use another (add " 2", a date, or ask in Ask mode). Use `overwrite` only when the user asked to replace a file.
- Creating files: plain text formats (txt, md, csv, tsv, json, html, css, svg, srt, vtt, ini, yaml, code) are written as text. `.docx` (lines of text, `# ` for headings), `.xlsx` (CSV or a JSON list of rows) and `.pdf` are built by ASTA. Other binary formats (png, mp3, mp4, odt, pptx…) come from programs: `run_program` (ffmpeg, magick/convert, pandoc, `soffice --headless --convert-to`) or by driving the right application.
- Never touch hidden/system files, other users' folders, or anything outside what the request names. Do not "clean up" more than asked.
- To remove something, `trash` it (reversible). To collect many files into one place, `move`; to keep the originals, `copy`.
- File names with "/" or ":" are not valid; replace them with "-".
