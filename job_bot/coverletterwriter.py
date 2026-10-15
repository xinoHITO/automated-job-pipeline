import os
import time
from google.genai import Client, errors
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from . import globals
from . import debug as debug
from .debug import log

SLEEP_BETWEEN_REQUESTS = 4

def log_retry(retry_state):
    error = retry_state.outcome.exception()
    log(f'Retry #{retry_state.attempt_number} failed: {error}. Sleeping {retry_state.next_action.sleep:.1f}s')

def should_retry_gemini_error(exception):
    """Custom filter to target ServerErrors and specific ClientErrors (like 429)."""
    
    # 1. Always retry on Server Errors (HTTP 5xx)
    if isinstance(exception, errors.ServerError):
        return True
        
    # 2. Only retry on Client Errors (HTTP 4xx) if it's a 429 Rate Limit
    if isinstance(exception, errors.ClientError):
        # google-genai exceptions expose the HTTP status code via .code
        if exception.code == 429:
            log("Rate limit (429) hit. Queueing retry...")
            return True
            
    return False

@retry(
    retry=retry_if_exception_type(should_retry_gemini_error),
    wait=wait_exponential(multiplier=30, min=30, max=300),
    stop=stop_after_attempt(3),
    before_sleep=log_retry
)

def _call_gemini(client, model, uploaded_files, prompt):    
    return client.chats.create(model=model).send_message(message=[*uploaded_files, prompt])

def generate_cover_letter(pdf_paths: list[str], job_description: str, cover_letter_template:str, sleep_time = SLEEP_BETWEEN_REQUESTS):
    client = Client()
    uploaded_files = []
    for pdf_path in pdf_paths:
        uploaded_file = client.files.upload(file=pdf_path)
        uploaded_files.append(uploaded_file)
        
    prompt = f"""
    You are an expert career consultant and professional copywriter. 
    Your task is to write a highly compelling, tailored cover letter based on the provided materials.
    
    Target Job Description:
    \"\"\"{job_description}\"\"\"
    
    Cover letter template:
    \"\"\"{cover_letter_template}\"\"\"

    Instructions:
    1. Align the candidate's core achievements from their resume and portfolio PDFs directly to the needs of the job description.
    2. Write in a confident, authentic, and professional tone. Avoid clichés or corporate buzzword fluff.
    3. Keep the cover letter under 2000 characters
    4. Keep it to roughly 3 structural paragraphs: Introduction mapping to the role, structural body mapping past success to their open problems, and a concise call to action.
    5. In the job description prioritize the sections titled "Your Responsibilities", "Requirements" , "Essential Skills" , "Qualifications" , "You bring", "What you will do" when mapping past the candidate's past successes and projects to the company's needs
    6. If possible but with less priority address the sections called "Bonus Points", "Nice to haves" or similar with the candidate's past experience or projects
    """
    debug.write_debug_file("prompt.txt",prompt)
    response_text = ''
    try:
        log(' └──> Attempting Primary Model (gemini-3.5-flash-lite)...')
        response_text = _call_gemini(client, 'gemini-3.5-flash-lite', uploaded_files, prompt).text
    except Exception as e:
        log(f' └──> Primary failed after retries. Switching to Backup (gemini-3.1-flash-lite)... Error: {e}')
        try:
            response_text = _call_gemini(client, 'gemini-3.1-flash-lite', uploaded_files, prompt).text
        except Exception as e2:
            log(f' └──> Backup model also failed: {e2}')
            raise e2
        
    for uploaded_file in uploaded_files:
        client.files.delete(name=uploaded_file.name)
    log(' └──> ✨Cover letter generated successfully ✨')
    log(f' └──> ⏳ Waiting {sleep_time}s to respect rate limits...')
    time.sleep(sleep_time)
    return response_text