import os
import asyncio
import json
# api.py — Job Pipeline as a service
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
import secrets
from pydantic import BaseModel
from job_bot import JobBot
from job_bot import profiler
from dotenv import load_dotenv
import sqlite3
import uuid
from contextlib import asynccontextmanager
load_dotenv()

API_SECRET_TOKEN = os.environ.get("API_SECRET_TOKEN")
if API_SECRET_TOKEN is None or len(API_SECRET_TOKEN) == 0:
    API_SECRET_TOKEN = secrets.token_urlsafe(16)
    print(f"[WARN] API_SECRET_TOKEN not set — using a random one for this session: {API_SECRET_TOKEN}")

MAX_CONCURRENT_TICKETS = None
try:
    MAX_CONCURRENT_TICKETS = int(os.environ.get("MAX_CONCURRENT_TICKETS"))
except ValueError as e:
    print(f"Could not parse .env variable MAX_CONCURRENT_TICKETS - {e}")
finally:
    if MAX_CONCURRENT_TICKETS is None:
        MAX_CONCURRENT_TICKETS = 2


concurrency_limiter = asyncio.Semaphore(MAX_CONCURRENT_TICKETS)

# ── Schemas (documentación + validación automática en /docs) ──
class RunRequest(BaseModel):
    max_days: int = 15
    hiring_profile:str = "test"
    write_cover_letters: bool = False
    profiling:bool = False
    send_notification: bool = False

@asynccontextmanager
async def lifespan(app:FastAPI):
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            params,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    asyncio.create_task(run_pending_tickets())

    yield

def create_ticket(params:RunRequest=None):
    ticket_id = str(uuid.uuid4())

    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()
    params_json:str = None
    try:
        if params:
            params_json = params.model_dump_json()
    except Exception as e:
        print(f"Error when parsing RunRequest | id:{ticket_id} - {e}")

    cursor.execute(f"INSERT INTO tickets (id,status,params,result) VALUES (?,?,?,?)"
                ,(ticket_id ,"in queue",params_json, None)
                )
    
    conn.commit()
    conn.close()
    return ticket_id

def update_ticket_status(ticket_id:str, status:str,params:RunRequest=None, result:str=None):
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()
    params_json:str = None
    try:
        if params:
            params_json = params.model_dump_json()
    except Exception as e:
        print(f"Error when parsing RunRequest | id:{ticket_id} - {e}")

    if params_json:
        cursor.execute(f"UPDATE tickets SET status = ?, params = ?, result = ? WHERE id = ?"
                    ,(status, params_json, result, ticket_id)
                    )
    else:
        cursor.execute(f"UPDATE tickets SET status = ?, result = ? WHERE id = ?"
                    ,(status, result, ticket_id)
                    )
    conn.commit()
    conn.close()

def get_ticket(ticket_id):
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status,result FROM tickets WHERE id = ?",(ticket_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {"id":ticket_id,"status":row[0],"result":row[1]}

async def run_pending_tickets():
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE tickets SET status = 'in queue' WHERE status = 'running'")
        print(f"Rows marked for queue: {cursor.rowcount}")

        cursor.execute("SELECT id,params FROM tickets WHERE status = 'in queue'")

        for row in cursor:
            ticket_id, json_params = row
            params_dict = json.loads(json_params)
            params:RunRequest = None
            try:
                params = RunRequest.model_validate(params_dict)
                asyncio.create_task(_run_pipeline(params,ticket_id))
            except Exception as e:
                print(f"Couldn't parse params dict from DB - {e}")

        conn.commit()
    except Exception as e:
            # If either query fails, instantly roll back the entire cycle
            conn.rollback()
            print(f"Database cycle failed and rolled back: {e}")

    conn.close()

app = FastAPI(title="Job Pipeline API", version="0.1.0",lifespan=lifespan)


async def _run_pipeline(req: RunRequest, ticket_id:str):
    async with concurrency_limiter:
        result:list
        ticket_result:str = None
        try:
            update_ticket_status(ticket_id,"running")
            if req.profiling:
                profiler.start_profiling()
                try:
                    result = await JobBot.main(req.max_days,req.hiring_profile,req.write_cover_letters,send_notification=req.send_notification) or []
                finally:
                    profiler.end_profiling()
            else:
                result = await JobBot.main(req.max_days,req.hiring_profile,req.write_cover_letters,send_notification=req.send_notification)
            ticket_result = json.dumps(result, indent=2, ensure_ascii=False)
            update_ticket_status(ticket_id,"done",result=ticket_result)

        except Exception as e:
            update_ticket_status(ticket_id,"failed",result=str(e))

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Endpoints ──

@app.post("/run", status_code=200)
def run(run_config: RunRequest,
         background: BackgroundTasks, 
         request:Request,
         x_api_key: str = Security(api_key_header)):
    if API_SECRET_TOKEN is None:
        raise HTTPException(
            status_code=403,
            detail="API_SECRET_TOKEN not configured on server."
        )
    # Security check: Ensure the request contains the correct secret token header
    if x_api_key is None or x_api_key != API_SECRET_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized access attempt."
        )
    
    new_ticket_id = create_ticket(run_config)
    background.add_task(_run_pipeline, run_config,new_ticket_id)

    # Get the base domain dynamically (e.g., "http://127.0.0.1:8080")
    base_url = str(request.base_url)     
    # Strip any trailing slash and build the full status path cleanly
    poll_url = f"{base_url.rstrip('/')}/status?ticket_id={new_ticket_id}"

    return {"id":new_ticket_id,"status": "in queue","poll_url":poll_url}

@app.get("/status")
def status(ticket_id:str):
    ticket = get_ticket(ticket_id)

    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {"id:":ticket_id, "status":ticket["status"], "result":ticket["result"]}

@app.get("/jobs")
def jobs(ticket_id:str, min_score: int = 0):
    """Last pipeline results, optionally filtered by score."""
    ticket = get_ticket(ticket_id)
    result = json.loads(ticket["result"])
    filtered = [j for j in result if int(j.get("total_score", 0)) >= min_score]
    return {"count": len(filtered), "jobs": filtered}