import os
import requests
from datetime import datetime
import shutil
from contextlib import ExitStack
from dotenv import load_dotenv

from . import globals
from .debug import log
load_dotenv()

def send_discord_notification(exported_jobs:int = 0):
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if DISCORD_WEBHOOK_URL is None:
        return

    output_folder= "output"
    archive_path= None
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")
    try:
        # Check if the folder exists and actually contains files
        if os.path.exists(output_folder) and os.listdir(output_folder):
            # Bundles the folder into a zip file named "scraper_logs.zip"
            # shutil.make_archive returns the full path to the created .zip file
            archive_path = shutil.make_archive("scraper_logs", "zip", f"{globals.base_dir}/{output_folder}")

            # Define the text message payload (equivalent to the -F "content=...")
            message_content = (
                f"🚀 **Scraper Run Finished Successfully!**\n"
                f"📅 Timestamp: `{timestamp}`\n"
                f"💼 Exported {exported_jobs} jobs.\n"
                f"📁 Attached below is today's execution log.\n"
            )
            # Set up the form data
            data = {
                "content": message_content
            }


            # Open the zip file and send it via multipart form request
            with open(archive_path, "rb") as f:
                files = {
                    "file[0]": ("job_bot.log", open(f"{globals.base_dir}/output/job_bot.log")),
                    "file[1]": ("job_matches.json", open(f"{globals.base_dir}/output/job_matches.json")),
                    "file[2]": (os.path.basename(archive_path), f)
                }
                response = requests.post(DISCORD_WEBHOOK_URL, data=data, files=files)


        else:
            # Fallback if the folder is missing or empty
            fallback_msg = f"⚠️ **Scraper Run Finished at {timestamp}, but the logs folder was empty or missing!**"
            requests.post(DISCORD_WEBHOOK_URL, json={"content": fallback_msg})
            log("Logs folder was empty or missing. Sent warning message instead.")
    finally:
        # Cleanup: Delete the local zip file so it doesn't linger on your disk
        if archive_path and os.path.exists(archive_path):
            os.remove(archive_path)

    # Check if it was successful
    if response.status_code in (200, 204):
        log("Webhook and file sent successfully!")
    else:
        log(f"Failed to send webhook: {response.status_code} - {response.text}")
