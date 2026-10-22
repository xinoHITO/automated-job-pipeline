
import sqlite3
from datetime import datetime, timedelta
import uuid

from .debug import log
from .job_model import JobModel
import dateparser
from colorama import Fore, Style

DATABASE_NAME = "tickets.db"

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

def get_jobs(limit_date:datetime):
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

def insert_jobs(new_jobs:list[JobModel]):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        for new_job in new_jobs:
            new_job_id = str(uuid.uuid4())
            standarized_date = None
            try:
                date_obj = dateparser.parse(new_job.date_posted)
                standarized_date = date_obj.strftime('%Y-%m-%d')
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