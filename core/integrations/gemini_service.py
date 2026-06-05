import os
import json
import time
import re
import google.generativeai as genai
from core.logging.config import logger

def extract_job_details_via_gemini(post_content):
    """
    Calls Google Gemini API (gemini-3.5-flash) to extract structured job details from post text.
    Includes rate limit (429) backoff handling with up to 3 retries.
    Returns a list of dicts, or None if the API key is not set or an error occurs.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable is not set. Skipping AI extraction.")
        return None
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.5-flash")
    except Exception as e:
        logger.error(f"Error configuring Gemini SDK: {e}")
        return None

    prompt = f"""
Analyze the following LinkedIn post content and extract all job opportunities mentioned.
For each job opportunity found, extract the required fields. If any field is not mentioned, use an empty string.

You MUST respond with a JSON object. The JSON object MUST have a top-level key "jobs" containing an array of job items.
Each job item must have the following keys:
- job_title (string)
- email (string - MUST extract the exact email address found in the post text. Do NOT modify, autocomplete, or hallucinate the domain name under any circumstances.)
- job_id (string)
- location (string)
- experience_required (string)
- tech_stack (string)
- post_url (string)
- post_date (string)

Post Content:
\"\"\"
{post_content}
\"\"\"
"""
    
    max_retries = 3
    base_delay = 5.0
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            raw_content = response.text
            parsed = json.loads(raw_content)
            return parsed.get("jobs", [])
            
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "ResourceExhausted" in err_msg or "quota" in err_msg.lower():
                wait_time = base_delay * (2 ** attempt)
                match = re.search(r"retry in ([\d\.]+)s", err_msg)
                if match:
                    wait_time = float(match.group(1)) + 0.5
                else:
                    match_sec = re.search(r"seconds:\s*(\d+)", err_msg)
                    if match_sec:
                        wait_time = float(match_sec.group(1)) + 1.0
                
                logger.warning(f"Gemini API rate limited (429). Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                logger.error(f"Error calling Gemini API for structured extraction: {e}")
                return None
                
    logger.error("Gemini API structured extraction failed after max retries due to rate limiting.")
    return None
