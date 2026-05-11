@echo off
setlocal
cd /d "%~dp0\.."
docker compose -f docker-compose.local.yml up --build %*
