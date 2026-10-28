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

if [ -f .env ]; then
    # Read line by line, splitting strictly on the first '=' character
    while IFS='=' read -r key value || [ -n "$key" ]; do
        
        # 1. Skip comments (lines starting with #) and empty lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        
        # 2. Clean up Windows carriage returns (\r) and trailing whitespaces
        key=$(echo "$key" | tr -d '\r[:space:]')
        
        # 3. Strip surrounding single or double quotes from the value if they exist
        value=$(echo "$value" | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        
        # 4. Safely export using an indirect variable assignment
        # This prevents Bash from evaluating code inside the value
        export "$key"="$value"

    done < .env
else
    echo "Warning: .env file not found. This machine won't go to sleep when run finishes"
fi

git pull || echo "WARN: git pull failed, continuing with local code"

# 4. Run your build and run pipelines
echo "📦 Building Docker image..."
docker build -t playwright-scraper:latest .

echo "🚀 Starting container..."
docker stop my-running-container || true
docker rm my-running-container || true
docker run --rm --env-file .env\
    -v "$(pwd)"/scraper_logs:/app/output\
    -v scraper_db:/app/db\
    playwright-scraper:latest 

#Optional copy the db volume to the project's folder if you want to inspect it
#docker run --rm -v scraper_db:/data -v "${PWD}:/out" alpine cp /data/scraped_jobs.db /out/    
echo "🎉 Docker container built and deployed successfully!"

if [ "${SLEEP_AFTER_RUN:-0}" = "1" ]; then
	echo "💤 Going to sleep now"

    if [ "$OS" = "Darwin" ]; then
        pmset sleepnow
    elif [ "$OS" = "Linux" ]; then
        sudo systemctl suspend
    fi
fi