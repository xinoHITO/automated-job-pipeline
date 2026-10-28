# 1. Use the official Playwright Python base image (FIXED)
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy only the requirements first to leverage Docker caching
COPY requirements.txt .

# 4. Install Python dependencies without saving cache bloat
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your application code
COPY . .

# [CRUCIAL STEP]: Add this to ensure Python can resolve your "job_bot" package
ENV PYTHONPATH="/app"

RUN mkdir -p /app/db

# 6. Create a non-root user for security (Highly Recommended for Web Scraping)
RUN useradd -m scraperuser && chown -R scraperuser:scraperuser /app && chown -R scraperuser:scraperuser /app/db
USER scraperuser

# 7. Command to run your scraper
CMD ["python", "-m", "job_bot", "scrape-and-run"]
