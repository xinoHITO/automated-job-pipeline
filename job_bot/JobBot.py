import asyncio
import os
import json
import uuid
from colorama import Fore, Style
from datetime import datetime

from . import notion as notion
from . import webscraper as webscraper
from . import coverletterwriter as coverletterwriter
from . import globals
from . import debug
from . import filtering
from . import notification
from .profile import ProfileModel,load_profile

from .debug import log

import sqlite3
from .job_model import JobModel

async def main(days_since_job_posted: int,
         profile_name:str,
         write_cover_letter:bool,
         send_notification:bool = False
         ):
    temp_folder_path = f"{globals.base_dir}/temp/"
    os.makedirs(temp_folder_path,exist_ok=True)

    debug.clean_output_folder()

    profile:ProfileModel = None
    try:
        profile = load_profile(profile_name)
    except Exception as e:
        log(f"ERROR when loading profile:{profile_name}")
    if profile is None:
        raise Exception

    log("===== JOB BOT PIPELINE STARTING =====",True)
    log(f"max_days:{days_since_job_posted} | write_cover_letter:{write_cover_letter}")
    log(f"hiring_profile:{profile.name}")

    all_found_jobs = None

    # If the file exists, safely read and return it as a Python Dictionary
    try:
        with open(globals.SCRAPED_JOBS_PATH, "r", encoding="utf-8") as f:
            all_found_jobs = json.load(f)
    except json.JSONDecodeError as decode_err:
        log(f"[CRITICAL] {globals.SCRAPED_JOBS_PATH} contains invalid JSON syntax or typos! Check for missing commas or brackets. Error: {decode_err}")
        raise decode_err

    matched_results = []
    
    for idx, (job) in enumerate(all_found_jobs):        
        log(f"\n[{idx+1}/{len(all_found_jobs)}] Processing: {job['title']}...")
        
        # STEP 1: Fast Screening Pass (No cover letter generation)
        #log(f" └──> Running screening check using {FAST_FILTER_MODEL}...")
        #rules_cfg = filtering.load_scoring_rules()
        #filter_check = filtering.run_quick_filter(FAST_FILTER_MODEL, job,rules_cfg)      
         
        filter_check = filtering.run_hiring_rules(profile.hiring_rules,job["title"],job["description"],job["location"])
        
        if filter_check["match_status"] == "MATCH":
            log(Fore.GREEN +f" └──> [PASSED] Score:{filter_check['total_score']} Reason: {filter_check['reason']} " +Style.RESET_ALL)
            log(f" └──> Url:{job['link']}")
            cover_letter = "None"
            try:
                if write_cover_letter:
                    # STEP 2: Deep synthesis pass (Triggered only on confirmed match status)
                    log(f" └──> Writing cover letter synthesis...")
                    cover_letter = coverletterwriter.generate_cover_letter( profile.data_files,
                                                                            job['description'],
                                                                            profile.cover_letter_template)
                    log(" └──> [SUCCESS] Tailored cover letter written and saved."+Style.RESET_ALL)
            except Exception as e:
                log(f"{Fore.YELLOW}└──> [WARNING] Cover letter writer failed but job will be added{Style.RESET_ALL} - {e}")
                cover_letter = "None"
            
            matched_results.append({
                "date_posted": job['date_posted'],
                "date_found": datetime.now().strftime("%d-%m-%Y"),
                "job_title": job['title'],
                "company": job['company'],
                "location": job['location'],
                "link": job['link'],
                "match_reason": filter_check['reason'],                
                "total_score": filter_check['total_score'],
                "generated_cover_letter": cover_letter
            })
        else:
            log(Fore.RED + f" └──> [REJECTED] Score:{filter_check['total_score']} Reason: {filter_check['reason']}"+Style.RESET_ALL)
            log(f" └──> Url:{job['link']}")

        await asyncio.sleep(0.1)


    # Save output to project disk    
    output_filename = f"{debug.OUTPUT_FOLDER_PATH}/job_matches.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(matched_results, f, indent=2, ensure_ascii=False)

    notion.update_notion_database_with_file(output_filename)
    log(f"\n===== RUN COMPLETE =====\n Saved {len(matched_results)} matches to '{output_filename}'")

    if send_notification:
        notification.send_discord_notification(len(matched_results))

    return matched_results

async def scrape(days_since_job_posted:int):
    setup_job_table()

    temp_folder_path = f"{globals.base_dir}/temp/"
    os.makedirs(temp_folder_path,exist_ok=True)

    debug.clean_output_folder()

    log("===== JOB BOT SCRAPING PIPELINE STARTING =====",True)
    log(f"max_days:{days_since_job_posted}")

    scraping_rules = webscraper.load_scraping_rules()
    all_found_jobs_dict = await webscraper.scrape_all_job_sites(scraping_rules,days_since_job_posted)
    all_found_jobs:list[JobModel] = list(all_found_jobs_dict.values())
    json_str = json.dumps([job.model_dump() for job in all_found_jobs],indent=2,ensure_ascii=False)
    # Save output to project disk
    with open(globals.SCRAPED_JOBS_PATH, "w", encoding="utf-8") as f:
        f.write(json_str)
    insert_jobs(all_found_jobs)

    log(f"\n===== SCRAPE COMPLETE =====\n Scraped {Fore.GREEN}{len(all_found_jobs_dict)}{Style.RESET_ALL} jobs to '{globals.SCRAPED_JOBS_PATH}'")

def setup_job_table():
    try:
        conn = sqlite3.connect("tickets.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                date_posted DATE,
                description TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        log(f"Job table created successfully")
    except Exception as e:
        log(f"Error when creating jobs table - {e}")

def insert_jobs(new_jobs:list[JobModel]):
    try:
        conn = sqlite3.connect("tickets.db")
        cursor = conn.cursor()
        for new_job in new_jobs:
            new_job_id = str(uuid.uuid4())
            cursor.execute(f"""
                            INSERT INTO jobs (id,url,source_site,title,company,location,date_posted,description) 
                            VALUES (?,?,?,?,?,?,?,?)
                            ON CONFLICT(url)
                            DO UPDATE SET
                                title=excluded.title, 
                                company=excluded.company, 
                                location=excluded.location, 
                                date_posted=excluded.date_posted,
                                description=excluded.description,
                                scraped_at=CURRENT_TIMESTAMP;
                            """
                            ,(new_job_id ,new_job.url,new_job.source_site,new_job.title,new_job.company,new_job.location,new_job.date_posted,new_job.description)
                            )
        conn.commit()
        conn.close()
        log(f"Job table created successfully")
    except Exception as e:
        log(f"Error when inserting job - {e}")