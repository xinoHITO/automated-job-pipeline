
import sqlite3
from datetime import datetime, timedelta
import uuid

from .debug import log
from .job_model import JobModel
import dateparser
from colorama import Fore, Style

DATABASE_NAME = "tickets.db"
DB_JOB_CACHE: dict = {}
DB_JOB_URL_CACHE: dict = {}

def create_job_table():
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                source_site TEXT,
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

def get_jobs(days_since_job_posted:int = 30):    
    limit_date =  datetime.now() - timedelta(days=days_since_job_posted)
    all_jobs:list[JobModel] = []
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT url,title,company,location,date_posted,description from jobs WHERE DATE(date_posted) >= DATE(?);
        """,(limit_date,))
        for row in cursor:
            url,title,company,location,date_posted,description = row
            job = JobModel(url=url,title=title,company=company,location=location,date_posted=date_posted,description=description)
            all_jobs.append(job)

        conn.commit()
        conn.close()
        log(f"Job table created successfully")
    except Exception as e:
        log(f"Error getting jobs table - {e}")

    return all_jobs

def __update_cache(max_days_since_posted:int = 15):
    jobs = get_jobs(max_days_since_posted)
    log(f"Generating DB_JOB_CACHE max_days:{max_days_since_posted}")    
    DB_JOB_CACHE.clear()
    DB_JOB_URL_CACHE.clear()
    for job in jobs:
        key = (job.title,job.company,job.date_posted)
        DB_JOB_CACHE[key] = job
        DB_JOB_URL_CACHE[job.url] = job
    log("Database JOB_CACHE and URL_CACHE generated!")

def job_exists_in_db(job_title:str, company:str, date_posted:str, max_days_since_posted:int = 15):
    if len(DB_JOB_CACHE.keys()) == 0:
        __update_cache(max_days_since_posted)
    date = standarize_date(date_posted)
    key_to_check = (job_title,company,date)
    
    result = DB_JOB_CACHE.get(key_to_check,None)
    if result is not None:
        log(f"{Fore.RED}DUPLICATE FOUND IN DB!{Style.RESET_ALL} - title:{job_title} | company:{company} | date_posted:{date}{Style.RESET_ALL}")
    else:
        log(f"{Fore.GREEN}No duplicate found in DB{Style.RESET_ALL} - {Fore.YELLOW}{job_title}{Style.RESET_ALL} | {Fore.CYAN}{company}{Style.RESET_ALL} | {date}")
    return result is not None

def job_url_exists_in_db(url:str, max_days_since_posted:int = 15):
    if len(DB_JOB_URL_CACHE.keys()) == 0:
        __update_cache(max_days_since_posted)
    
    result = DB_JOB_URL_CACHE.get(url,None)
    if result is not None:
        log(f"{Fore.RED}URL DUPLICATE FOUND IN DB!{Style.RESET_ALL} - url:{Fore.MAGENTA}{url}{Style.RESET_ALL}")
    else:
        log(f"{Fore.GREEN}No URL duplicate found in DB{Style.RESET_ALL} - url:{Fore.MAGENTA}{url}{Style.RESET_ALL}")
    return result is not None


def insert_jobs(new_jobs:list[JobModel]):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        for new_job in new_jobs:
            new_job_id = str(uuid.uuid4())
            standarized_date = None
            try:                
                standarized_date = standarize_date(new_job.date_posted)
                cursor.execute(f"""
                                            INSERT INTO jobs (id,url,source_site,title,company,location,date_posted,description) 
                                            VALUES (?,?,?,?,?,?,?,?)
                                            ON CONFLICT(url)
                                            DO UPDATE SET
                                                title=excluded.title, 
                                                company=excluded.company, 
                                                source_site=excluded.source_site,
                                                location=excluded.location, 
                                                date_posted=excluded.date_posted,
                                                description=excluded.description,
                                                scraped_at=CURRENT_TIMESTAMP;
                                            """
                                            ,(new_job_id ,new_job.url,new_job.source_site,new_job.title,new_job.company,new_job.location,standarized_date,new_job.description)
                                            )
            except Exception as e:
                log(f"Error when inserting job in DB - invalid date in job | {Fore.CYAN}{new_job.company}{Style.RESET_ALL} | {Fore.YELLOW}{new_job.title}{Style.RESET_ALL}  | {new_job.date_posted} - {Fore.RED}{e}{Style.RESET_ALL}")
            
        conn.commit()
        conn.close()
        log(f"Job table created successfully")
    except Exception as e:
        log(f"Error when inserting job - {e}")

def standarize_date(date_text:str):
    date_obj = dateparser.parse(date_text)
    standarized_date = None
    if date_obj:
        standarized_date = date_obj.strftime('%Y-%m-%d')
    return standarized_date