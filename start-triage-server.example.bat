@echo off
setlocal

rem Copy this file to start-triage-server.bat and edit the paths for your machine.
rem The GUI can then start your local OpenAI-compatible llama.cpp server.

set LLAMA_SERVER=C:\path\to\llama-server.exe
set MODEL=C:\path\to\vision-model.gguf
set MMPROJ=C:\path\to\mmproj.gguf

"%LLAMA_SERVER%" ^
  -m "%MODEL%" ^
  --mmproj "%MMPROJ%" ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --parallel 4
