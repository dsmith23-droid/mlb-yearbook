@echo off
cd /d "%~dp0"
echo Starting Yearbook V2 server...
start "" "http://localhost:8000/index_v2.html"
python server.py
