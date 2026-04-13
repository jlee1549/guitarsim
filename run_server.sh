#!/usr/bin/env bash
# run_server.sh — restart guitarsim server on exit
cd "$(dirname "$0")/server"
source .venv/bin/activate
while true; do
    echo "[$(date)] starting server..."
    python app.py --server 2>&1
    echo "[$(date)] server exited (code $?), restarting in 2s..."
    sleep 2
done
