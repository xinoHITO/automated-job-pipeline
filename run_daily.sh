#!/usr/bin/env bash

# Ensure the script can locate Docker
export PATH="$HOME/.docker/bin:$PATH"

OS="$(uname -s)"

# 1. Reset and launch Docker based on OS
if [ "$OS" = "Darwin" ]; then
    echo "Resetting Docker processes..."
    pkill -9 -f Docker || true

    echo "Launching Docker Desktop..."
    open -a "Docker"
elif [ "$OS" = "Linux" ]; then
    echo "Ensuring Docker service is running..."
    sudo systemctl start docker || echo "WARN: could not start docker via systemctl (sudo in cron?)"
fi

tries=0
until docker info >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 60 ]; then
        echo "ERROR: Docker daemon did not become ready after ~2 minutes. Aborting."
        exit 1
    fi
    sleep 2
done
echo "✅ Docker daemon is ready!"

echo "Changing to '$(dirname "$0")'"
# ─── 3. Go to the repo root (works from cron, which starts in $HOME) ───
cd "$(dirname "$0")" || exit 1

if [ ! -f .env ]; then
    echo "ERROR: .env not found in $(pwd). Copy .env.example and fill it in first."
    exit 1
fi

git pull || echo "WARN: git pull failed, continuing with local code"

# 4. Run your build and run pipelines
echo "📦 Building Docker image..."
docker build -t playwright-scraper:latest .

echo "🚀 Starting container..."
docker stop my-running-container || true
docker rm my-running-container || true
docker run --rm --env-file .env -v "$(pwd)"/scraper_logs:/app/output playwright-scraper:latest

echo "🎉 Docker container built and deployed successfully!"

echo "💤 Going to sleep now"
if [ "${SLEEP_AFTER_RUN:-0}" = "1" ]; then
    if [ "$OS" = "Darwin" ]; then
        pmset sleepnow
    elif [ "$OS" = "Linux" ]; then
        sudo systemctl suspend
    fi
fi