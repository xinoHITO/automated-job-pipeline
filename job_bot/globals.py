import os
from pathlib import Path
base_dir = Path(__file__).parent.parent
last_run_date_path = f"{base_dir}/temp/last_run_date.txt"

WEB_SCRAPING_CONFIG_PATH = os.environ.get("WEB_SCRAPING_CONFIG_PATH")
if WEB_SCRAPING_CONFIG_PATH is None or len(WEB_SCRAPING_CONFIG_PATH) == 0:
    WEB_SCRAPING_CONFIG_PATH = f"config/scraping_rules.json"
    print(f"[WARN] WEB_SCRAPING_CONFIG_PATH not set — using a default value of: config/scraping_rules.json")

SCRAPED_JOBS_PATH = f"{base_dir}/scraped_jobs.json"