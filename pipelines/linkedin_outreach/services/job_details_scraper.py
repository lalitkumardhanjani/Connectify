import os
import re
import json
import time
from urllib.parse import urlparse, parse_qs
import requests
from html.parser import HTMLParser
from core.logging.config import logger

class LDJSONParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.script_type = None
        self.ld_json_contents = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.in_script = True
            for name, value in attrs:
                if name == "type" and value == "application/ld+json":
                    self.script_type = value

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False
            self.script_type = None

    def handle_data(self, data):
        if self.in_script and self.script_type == "application/ld+json":
            self.ld_json_contents.append(data)

def is_valid_location(loc):
    if not loc or not isinstance(loc, str):
        return False
    loc = loc.strip()
    loc_lower = loc.lower()
    
    # Common UI keywords, forms, footer terms that get mistakenly extracted
    invalid_keywords = [
        "not specified", "n/a", "none", "null", "undefined", "unknown",
        "type", "input,", "input", "description", "count", "document", "support", 
        "search", "te", "view", "results", "apply", "careers", "job", "post",
        "cookie", "privacy", "terms", "submit", "login", "register", "signup",
        "discrimination", "illegal", "discuss", "dedicated", "policy", "browser",
        "javascript", "error", "website", "content", "page", "form", "select",
        "button", "click", "required", "optional", "details", "contact", "home"
    ]
    
    if loc_lower in invalid_keywords:
        return False
        
    if len(loc) > 40 or len(loc) < 2:
        return False
        
    # Check if contains any invalid phrases
    for keyword in ["illegal", "discrimination", "discuss", "dedicated", "cookie", "policy", "browser", "javascript", "unsupported"]:
        if keyword in loc_lower:
            return False
            
    return True

def is_valid_job_id(jid):
    if not jid or not isinstance(jid, str):
        return False
    jid = jid.strip()
    jid_lower = jid.lower()
    
    invalid_job_ids = [
        "n/a", "none", "null", "undefined", "unknown", "order", "view", "results", 
        "manila", "hyderabad", "bengaluru-ka", "apply", "job", "post", "careers", 
        "details", "page", "application", "input", "select", "button", "div", 
        "span", "class", "id", "href", "url", "http", "https", "error", "required",
        "submit", "form", "search", "document", "count", "support", "type"
    ]
    
    if jid_lower in invalid_job_ids:
        return False
        
    if len(jid) > 50 or len(jid) < 3:
        return False
        
    # If it contains spaces or symbols that aren't common in IDs
    if " " in jid or len(re.findall(r'[a-zA-Z0-9_\-]', jid)) < len(jid) * 0.8:
        return False
        
    return True

def extract_details_from_html(html_text, url):
    """
    Parses Job ID, Location, and Experience from the job posting HTML.
    """
    job_id = ""
    location = ""
    experience = ""

    # 1. Parse JSON-LD JobPosting schema
    parser = LDJSONParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass

    job_data = {}
    for content in parser.ld_json_contents:
        try:
            data = json.loads(content)
            if isinstance(data, list):
                data = data[0]
            if isinstance(data, dict) and (data.get("@type") == "JobPosting" or "JobPosting" in str(data.get("@type"))):
                job_data = data
                break
        except Exception:
            pass

    # Extract from schema
    if job_data:
        # Location from schema
        loc_obj = job_data.get("jobLocation")
        if loc_obj:
            if isinstance(loc_obj, dict):
                addr = loc_obj.get("address")
                if isinstance(addr, dict):
                    loc_parts = []
                    for field in ["addressLocality", "addressRegion", "addressCountry"]:
                        val = addr.get(field)
                        if val:
                            loc_parts.append(str(val))
                    location = ", ".join(loc_parts)
                elif isinstance(addr, str):
                    location = addr
            elif isinstance(loc_obj, list) and loc_obj:
                first_loc = loc_obj[0]
                if isinstance(first_loc, dict):
                    addr = first_loc.get("address")
                    if isinstance(addr, dict):
                        location = addr.get("addressCountry") or ""
                else:
                    location = str(first_loc)
            else:
                location = str(loc_obj)

        # Job ID from schema
        id_obj = job_data.get("identifier")
        if id_obj:
            if isinstance(id_obj, dict):
                job_id = str(id_obj.get("value") or "")
            else:
                job_id = str(id_obj)

    # 2. Fallbacks and enhancements
    # Try to extract Job ID from URL path or query parameters
    if not is_valid_job_id(job_id):
        parsed_url = urlparse(url)
        # Search query params (e.g. opportunityId, job_id, reqId, role)
        qs = parse_qs(parsed_url.query)
        for param in ["opportunityId", "jobId", "job_id", "reqId", "role", "id"]:
            if param in qs and qs[param]:
                job_id = qs[param][0]
                break
        
        # Search URL path segments (e.g. jobs/8576246002, post/e756352a...)
        if not is_valid_job_id(job_id):
            path_segments = [seg for seg in parsed_url.path.split("/") if seg]
            for i, seg in enumerate(path_segments):
                if seg in ["jobs", "job", "post", "role"] and i + 1 < len(path_segments):
                    job_id = path_segments[i + 1]
                    break
            if not is_valid_job_id(job_id) and path_segments:
                # If there's a segment with a mix of digits and characters, it could be the ID
                for seg in reversed(path_segments):
                    if re.match(r'^[a-f0-9\-]{24,}$', seg) or re.search(r'\d+', seg):
                        job_id = seg
                        break

    # Requisition ID pattern from text
    if not is_valid_job_id(job_id):
        id_patterns = [
            r'(?:job|req|reference|posting|requisition)\s*(?:id|number|no|#)?\s*[:\-#]?\s*([A-Za-z0-9_\-]+)',
            r'JR\d+',
            r'NTT\d+[A-Z0-9]+'
        ]
        for pat in id_patterns:
            matches = re.findall(pat, html_text, re.IGNORECASE)
            if matches:
                cand = matches[0].strip()
                if is_valid_job_id(cand):
                    job_id = cand
                    break

    # Location pattern from text
    if not is_valid_location(location):
        loc_patterns = [
            r'(?:location|workplace|office|based in)\s*[:\-#]?\s*([A-Z][a-zA-Z\s,]{2,30})',
            r'([A-Z][a-zA-Z\s,]{2,30})\s*\|\s*(?:Remote|Hybrid|On-site)',
            r'(?:Remote\s*-\s*India|Remote\s*,\s*India|India\s*-\s*Remote|India\s*,\s*Remote)',
        ]
        for pat in loc_patterns:
            matches = re.findall(pat, html_text, re.IGNORECASE)
            if matches:
                cand = matches[0].strip()
                if is_valid_location(cand):
                    location = cand
                    break

    # Experience requirement pattern from text
    exp_patterns = [
        r'(\d+(?:\s*-\s*\d+)?\s*\+?\s*years?)\s*(?:of)?\s*experience',
        r'experience\s*(?:of)?\s*(\d+(?:\s*-\s*\d+)?\s*\+?\s*years?)',
        r'(\d+\+?\s*yrs?)',
    ]
    for pat in exp_patterns:
        matches = re.findall(pat, html_text, re.IGNORECASE)
        if matches:
            experience = matches[0].strip()
            break

    # Sanitize outputs
    if job_id:
        job_id = re.sub(r'[^\w\-]', '', job_id).strip()
    if location:
        # Strip HTML tags if any got caught
        location = re.sub(r'<[^>]*>', '', location).strip()
        # Collapse multiple spaces
        location = re.sub(r'\s+', ' ', location)
    if experience:
        experience = re.sub(r'\s+', ' ', experience).strip()

    return {
        "job_id": job_id if is_valid_job_id(job_id) else "N/A",
        "location": location if is_valid_location(location) else "Not Specified",
        "experience": experience or "Not Specified"
    }

def scrape_job_details(url):
    """
    Downloads the page using requests with fallback.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        # Avoid heavy assets, fetch just the HTML text
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return extract_details_from_html(res.text, url)
    except Exception as e:
        logger.warning(f"Error requesting {url} directly: {e}")
        
    # Fallback to headless selenium if requests fail or returns empty details
    driver = None
    try:
        from selenium.webdriver.chrome.options import Options
        # Patch chrome options for headless mode dynamically
        original_add_argument = Options.add_argument
        def patched_add_argument(self, arg):
            original_add_argument(self, arg)
            if arg == "--no-sandbox":
                original_add_argument(self, "--headless=new")
        Options.add_argument = patched_add_argument
        
        from core.integrations.selenium_driver import get_driver
        driver = get_driver("chrome-profile-details-extractor")
        driver.get(url)
        time.sleep(3)
        html = driver.page_source
        return extract_details_from_html(html, url)
    except Exception as se:
        logger.error(f"Headless browser scraper fallback failed for {url}: {se}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
                
    return {"job_id": "N/A", "location": "Not Specified", "experience": "Not Specified"}
