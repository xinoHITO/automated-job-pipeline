
from pydoc import text
import sqlite3
from datetime import date, datetime, timedelta
import uuid

from .debug import log
from .job_model import JobModel
import dateparser
from colorama import Fore, Style

DATABASE_NAME = "db/scraped_jobs.db"
dedup_index: DedupIndex = None

class DedupIndex:
    def __init__(self,urls:set[str],keys:set[tuple]):
        self.urls = urls
        self.keys = keys

    def url_exists(self, url) -> bool: 
        return url in self.urls
    
    def job_exists(self,title:str,company:str,post_date:datetime) -> bool:
        key = (title.lower().strip(),company.lower().strip(),post_date)
        if post_date is None:
            return False
        return key in self.keys

    def add(self, job:JobModel):
        self.urls.add(job.url)
        date_obj = dateparser.parse(standarize_date(job.date_posted))
        key = (job.title,job.company,date_obj)
        if job.date_posted is not None:
            self.keys.add(key)

def _load_dedup_index(max_days: int):
    global dedup_index

    log(f"Generating dedup_index max_days:{max_days}")    

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT url, title, company, date_posted
        FROM jobs WHERE date_posted >= ?;
        """, (date.today() - timedelta(days=max_days),))
    urls:set[str] = set()
    keys:set[tuple] = set()
    for row in rows:
        url,title,company,date_posted = row
        if url:
            urls.add(url)
        if title and company and date_posted:
            date_obj = dateparser.parse(date_posted)
            key = (title.lower().strip(),company.lower().strip(),date_obj)
            keys.add(key)
    dedup_index = DedupIndex(urls,keys)
    log("Database dedup_index generated!")


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
    except Exception as e:
        log(f"Error getting jobs table - {e}")

    return all_jobs

def job_exists_in_db(job_title:str, company:str, date_posted:str, max_days_since_posted:int = 15):
    if dedup_index is None:
        _load_dedup_index(max_days_since_posted)
    date = standarize_date(date_posted)
    date_obj = dateparser.parse(date)
    return dedup_index.job_exists(job_title,company ,date_obj)    

def job_url_exists_in_db(url:str, max_days_since_posted:int = 15):
    if dedup_index is None:
        _load_dedup_index(max_days_since_posted)
    
    return dedup_index.url_exists(url)

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