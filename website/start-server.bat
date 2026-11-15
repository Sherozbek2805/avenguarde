@echo off
rem Starts the site on this computer and opens it in your browser. Close this window to stop it.
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 goto nonode
start "" http://127.0.0.1:8080/
node tools\serve.mjs 8080
goto end
:nonode
echo Node.js was not found. Trying Python instead.
start "" http://127.0.0.1:8080/
python -m http.server 8080 --bind 127.0.0.1
:end
pause
