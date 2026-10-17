from pathlib import Path

base_dir = Path(__file__).parent.parent
last_run_date_path = f"{base_dir}/temp/last_run_date.txt"

DEFAULT_WEB_SCRAPING_CONFIG_PATH = f"config/scraping_rules.example.json"
DEFAULT_HIRING_RULES_PATH = f"config/hiring_rules.example.json"
