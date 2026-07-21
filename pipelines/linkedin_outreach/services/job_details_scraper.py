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

def get_clean_text(html):
    """
    Strips script, style, comments, and HTML tags to get clean visible text.
    Collapses multiple whitespaces and handles common entities.
    """
    if not html:
        return ""
    # Remove script and style elements
    text = re.sub(r'<script\b[^>]*>([\s\S]*?)</script>', ' ', html, flags=re.IGNORECASE)
    text = re.sub(r'<style\b[^>]*>([\s\S]*?)</style>', ' ', text, flags=re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r'<!--([\s\S]*?)-->', ' ', text)
    # Replace HTML entity codes
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    # Strip HTML tags
    text = re.sub(r'<[^>]*>', ' ', text)
    # Collapse multiple whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

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
        "button", "click", "required", "optional", "details", "contact", "home",
        "mapsettings", "found", "interaction", "around the world"
    ]
    
    if loc_lower in invalid_keywords:
        return False
        
    if len(loc) > 80 or len(loc) < 2:
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

def extract_from_html_tags(html_text):
    """
    Extracts location values from common metadata tag selectors and semantic layout classes.
    """
    location = ""
    # 1. Standard og/meta tags
    meta_pats = [
        r'<meta\s+[^>]*name=["\']location["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*property=["\']og:locality["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*name=["\']city["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*name=["\']country["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*name=["\']twitter:label1["\']\s+content=["\']Location["\'][^>]*>\s*<meta\s+[^>]*name=["\']twitter:data1["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*name=["\']twitter:data1["\']\s+content=["\']([^"\']+)["\'][^>]*>\s*<meta\s+[^>]*name=["\']twitter:label1["\']\s+content=["\']Location["\']'
    ]
    for pat in meta_pats:
        m = re.search(pat, html_text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if is_valid_location(cand):
                location = cand
                break

    # 2. Specific Greenhouse / Lever classes
    if not location:
        class_pats = [
            r'<div\s+[^>]*class=["\']location["\'][^>]*>([^<]+)</div>',
            r'<span\s+[^>]*class=["\']location["\'][^>]*>([^<]+)</span>',
            r'<div\s+[^>]*class=["\']posting-categories["\'][\s\S]*?<div\s+[^>]*class=["\']location["\'][^>]*>([^<]+)</div>',
            r'<div\s+[^>]*class=["\']posting-category\s+location["\'][^>]*>([^<]+)</div>'
        ]
        for pat in class_pats:
            m = re.search(pat, html_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r'<[^>]*>', '', cand).strip()
                if is_valid_location(cand):
                    location = cand
                    break
    return location

def extract_details_from_html(html_text, url, visible_text=None):
    """
    Parses Job ID, Location, and Experience from the job posting HTML.
    Uses browser's visible_text directly if provided (essential for dynamic SPAs parsed via Selenium).
    """
    job_id = ""
    location = ""
    experience = ""

    # Get clean visible text
    clean_text = visible_text if visible_text is not None else get_clean_text(html_text)

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

    # 2. Try metadata / class HTML elements
    if not is_valid_location(location):
        location = extract_from_html_tags(html_text)

    # 3. Extract Job ID from URL path or query parameters (relying on redirected final URL)
    if not is_valid_job_id(job_id):
        parsed_url = urlparse(url)
        # Search query params case-insensitively, cleaning up any HTML ampersand encoding artifacts
        query_str = parsed_url.query.replace("&amp;", "&").replace("&amp;amp;", "&")
        qs = {k.lower().strip().replace("amp;", ""): v for k, v in parse_qs(query_str).items()}
        for param in ["opportunityid", "jobid", "job_id", "reqid", "role", "id"]:
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
            r'\b(?:job|req|reference|posting|requisition|position)\b\s*(?:id|number|no|#)?\s*[:\-#]?\s*\b([A-Za-z0-9_\-]+)',
            r'\bJR\d+\b',
            r'\bNTT\d+[A-Z0-9]+\b'
        ]
        for pat in id_patterns:
            matches = re.findall(pat, clean_text, re.IGNORECASE)
            if matches:
                cand = matches[0].strip()
                if is_valid_job_id(cand):
                    job_id = cand
                    break

    # 4. Fallbacks to production-grade extractors from post_extractor.py
    if not is_valid_location(location):
        try:
            from core.utils.post_extractor import extract_location as ext_loc
            cand = ext_loc(clean_text)
            if is_valid_location(cand):
                location = cand
        except Exception:
            pass

    if not experience or experience.lower() in ("not specified", "n/a"):
        try:
            from core.utils.post_extractor import extract_experience as ext_exp
            cand = ext_exp(clean_text)
            if cand:
                experience = cand
        except Exception:
            pass

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
    Downloads the page using requests with fallback to headless selenium.
    Uses the final resolved redirected URL to accurately extract path parameters.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    details = {"job_id": "N/A", "location": "Not Specified", "experience": "Not Specified"}
    
    try:
        # Avoid heavy assets, fetch just the HTML text
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            # Pass the final redirected URL (res.url) instead of the original short URL
            details = extract_details_from_html(res.text, res.url)
            # Optimization: Bypass Selenium ONLY if requests successfully found BOTH location and Job ID (since SPAs return blank HTML with ID parsed from URL)
            if details["location"] != "Not Specified" and details["job_id"] != "N/A":
                return details
    except Exception as e:
        logger.warning(f"Error requesting {url} directly: {e}")
        
    # Fallback to headless selenium if requests fail or return incomplete details
    if details["location"] == "Not Specified" or details["job_id"] == "N/A" or details["experience"] == "Not Specified":
        logger.info(f"Requests returned incomplete details for {url}. Falling back to Selenium headless Chrome...")
        driver = None
        profile_suffix = f"chrome-profile-details-extractor-temp-{int(time.time() * 1000)}"
        try:
            from core.integrations.selenium_driver import get_driver
            driver = get_driver(profile_suffix, headless=True)
            driver.get(url)
            # Wait up to 10 seconds for dynamic AJAX / Single Page App content to load
            from selenium.webdriver.support.ui import WebDriverWait
            try:
                WebDriverWait(driver, 10).until(lambda d: len(d.find_element(by="tag name", value="body").text) > 1000)
            except Exception:
                pass
            html = driver.page_source
            try:
                visible_text = driver.find_element(by="tag name", value="body").text
            except Exception:
                visible_text = None
            # Pass the final browser URL (driver.current_url) and the gold-standard browser visible text
            selenium_details = extract_details_from_html(html, driver.current_url, visible_text=visible_text)
            
            # Keep whichever details are better
            if selenium_details["location"] != "Not Specified":
                details["location"] = selenium_details["location"]
            if selenium_details["job_id"] != "N/A":
                details["job_id"] = selenium_details["job_id"]
            if selenium_details["experience"] != "Not Specified":
                details["experience"] = selenium_details["experience"]
        except Exception as se:
            logger.error(f"Headless browser scraper fallback failed for {url}: {se}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            # Clean up the temporary profile folder to avoid disk bloat
            try:
                from config.settings import get_user_dir
                profile_dir = os.path.join(get_user_dir(), profile_suffix)
                if os.path.exists(profile_dir):
                    import shutil
                    shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass
                
    return details
