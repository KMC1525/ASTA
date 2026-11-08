### Text editors and office programs (Notepad, gedit, Kate, TextEdit, LibreOffice Writer/Calc, Word)
- For a document the user wants, creating the file directly (`create_file` .txt/.md/.docx/.xlsx/.pdf) is more reliable than typing into the program. Then open it with `open_app` (files=[path]) or `open_path` if the user wants to see it.
- If you must type: open the program, confirm with a screenshot, click inside the page, `type_text`, then save with `ctrl+s` (macOS `cmd+s`), type the full path in the name field and press `Return`. Verify the file with `list_dir`.
- LibreOffice convert without the GUI: `run_program` soffice with `--headless --convert-to pdf --outdir <dir> <file>`.
