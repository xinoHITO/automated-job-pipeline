import asyncio
import os
import json
from colorama import Fore, Style
from datetime import datetime

from . import notion as notion
from . import webscraper as webscraper
from . import coverletterwriter as coverletterwriter
from . import globals
from . import debug
from . import filtering
from . import notification

from .debug import log

# 4. MULTI-MODEL PIPELINE MASTER CONTROLLER
async def main(days_since_job_posted: int,
         write_cover_letter:bool, 
         scraping_rules_path:str = globals.DEFAULT_WEB_SCRAPING_CONFIG_PATH, 
         hiring_rules_path:str = globals.DEFAULT_HIRING_RULES_PATH,
         send_notification:bool = False):
    COVER_LETTER_TEMPLATE = os.environ.get("COVER_LETTER_TEMPLATE", f"config/coverLetterTemplate.example.txt")
    CV_FILE = os.environ.get("CV_FILE", f"{globals.base_dir}/data/resume.pdf")
    PORTFOLIO_FILE = os.environ.get("PORTFOLIO_FILE", f"{globals.base_dir}/data/portfolio.pdf")

    temp_folder_path = f"{globals.base_dir}/temp/"
    os.makedirs(temp_folder_path,exist_ok=True)

    debug.clean_output_folder()

    log("===== JOB BOT PIPELINE STARTING =====",True)
    log(f"max_days:{days_since_job_posted} | write_cover_letter:{write_cover_letter}")
    log(f"scraping rules:{scraping_rules_path}")
    
    all_found_jobs = await webscraper.scrape_all_job_sites(f"{globals.base_dir}/{scraping_rules_path}",days_since_job_posted)
    matched_results = []
    
    for idx, (key,job) in enumerate(all_found_jobs.items()):        
        log(f"\n[{idx+1}/{len(all_found_jobs)}] Processing: {job['title']}...")
        
        # STEP 1: Fast Screening Pass (No cover letter generation)
        #log(f" └──> Running screening check using {FAST_FILTER_MODEL}...")
        #rules_cfg = filtering.load_scoring_rules()
        #filter_check = filtering.run_quick_filter(FAST_FILTER_MODEL, job,rules_cfg)        
        filter_check = filtering.run_hiring_rules(f"{globals.base_dir}/{hiring_rules_path}",job["title"],job["description"],job["location"])
        
        if filter_check["match_status"] == "MATCH":
            log(Fore.GREEN +f" └──> [PASSED] Score:{filter_check['total_score']} Reason: {filter_check['reason']} " +Style.RESET_ALL)
            log(f" └──> Url:{job['link']}")
            cover_letter = "None"
            try:
                if write_cover_letter:
                    # STEP 2: Deep synthesis pass (Triggered only on confirmed match status)
                    log(f" └──> Writing cover letter synthesis...")
                    try:
                        with open(f"{globals.base_dir}/{COVER_LETTER_TEMPLATE}","r",encoding="UTF-8") as r_cover_letter:
                            sample_cover_letter = r_cover_letter.read()
                    except Exception as e:
                        log(f"Error when reading sample txt files:{e}")        
                        exit(1)
                    cover_letter = coverletterwriter.generate_cover_letter([CV_FILE,PORTFOLIO_FILE],
                                                                            job['description'],
                                                                            sample_cover_letter)
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

