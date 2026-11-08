@echo off
rem ASTA (Windows): abre o ASTA com o Python que vem junto. Fechar esta janela encerra o ASTA.
setlocal
title ASTA
set "ASTA_ROOT=%~dp0"
set "ASTA_NATIVE_LIB=%ASTA_ROOT%native\asta_core.dll"
set "ASTA_INSTALLER=windows"
"%ASTA_ROOT%python\python.exe" -m asta %*
if errorlevel 1 pause
