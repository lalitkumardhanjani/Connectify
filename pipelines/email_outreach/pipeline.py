import os
import openpyxl
from config.settings import JOB_TRACKER_FILE
from config.user_profiles import get_selected_user_config
from config.constants import DBA_KEYWORDS_DEFAULT
from core.integrations.selenium_driver import get_driver
from core.storage.database import init_scraper_store, update_status
from core.logging.config import logger
from core.utils.string_utils import parse_preferred_locations

from pipelines.email_outreach.services.scraper import LinkedInScraper
from pipelines.email_outreach.services.sender import send_email_via_gmail

def run_phase_one(scraper):
    """Executes email scraping from LinkedIn posts based on selected keyword list."""
    init_scraper_store()
    user_conf = get_selected_user_config()
    email_scraper_conf = user_conf.get("email_scraper", {})
    keywords = email_scraper_conf.get("keywords", DBA_KEYWORDS_DEFAULT)
    
    # Retrieve preferred locations from candidate profile
    profile = user_conf.get("profile", {})
    pref_location = profile.get("preferred_locations", "")
    locations = parse_preferred_locations(pref_location)
    if not locations:
        locations = [""]
    
    for loc in locations:
        for kw in keywords:
            search_query = f"{kw} {loc}".strip() if loc else kw
            logger.info(f"=== Processing keyword: '{kw}' at location: '{loc}' (Search query: '{search_query}') ===")
            if scraper.search_for_keyword(search_query):
                scraper.process_keyword(kw, timeout_seconds=60)
            else:
                logger.warning(f"Skipping query '{search_query}' due to navigation failure.")

def run_phase_two(scraper, review_mode=None):
    """Executes composing and sending emails via Selenium browser to discovered addresses."""
    if not os.path.exists(JOB_TRACKER_FILE):
        logger.warning(f"Excel database '{JOB_TRACKER_FILE}' not found – nothing to send.")
        return
        
    wb = openpyxl.load_workbook(JOB_TRACKER_FILE)
    ws = wb.active
    col_map = {cell.value: idx+1 for idx, cell in enumerate(ws[1])}
    email_col = col_map.get('Email')
    status_col = col_map.get('Status')
    
    if not email_col or not status_col:
        logger.error("Excel schema missing required columns.")
        return
        
    for row in range(2, ws.max_row + 1):
        status = (ws.cell(row=row, column=status_col).value or '').strip().lower()
        if status == 'sent':
            continue
        email = ws.cell(row=row, column=email_col).value
        if not email:
            continue
            
        logger.info(f"Processing email outreach for {email} (row {row})")
        sent = send_email_via_gmail(scraper.driver, email, review_mode=review_mode)
        if sent == "skipped":
            logger.info(f"Email to {email} skipped – leaving status unchanged.")
            continue
        elif sent == "quit":
            logger.info("Quitting email outreach pipeline as requested by user.")
            break
        elif sent:
            update_status(email, 'sent')
        else:
            logger.info(f"Email to {email} not sent – leaving status unchanged.")

def run_pipeline(phase="full", review_mode=None):
    """Orchestrates the entire Email Outreach pipeline process."""
    logger.info(f"Starting Email Scraper & Outreach Pipeline (Phase: {phase})")
    
    driver = get_driver()
    scraper = LinkedInScraper(driver)
    
    try:
        if not scraper.login():
            logger.error("Login failed – aborting Email Outreach pipeline.")
            return False
            
        if phase in ("full", "phase1"):
            logger.info("Executing Phase 1: Post email scraping...")
            run_phase_one(scraper)
            
        if phase in ("full", "phase2"):
            logger.info("Executing Phase 2: Email sending...")
            run_phase_two(scraper, review_mode=review_mode)
            
        return True
    except Exception as e:
        logger.exception(f"Unhandled error during pipeline execution: {e}")
        return False
    finally:
        logger.info("Closing browser session...")
        driver.quit()
        logger.info("Email Scraper & Outreach pipeline complete.")
        
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the Email Scraper and Outreach pipeline.")
    parser.add_argument("--phase", choices=["full", "phase1", "phase2"], default="full")
    parser.add_argument("--review", action="store_true", help="Review before sending emails")
    args = parser.parse_args()
    run_pipeline(phase=args.phase, review_mode=args.review)
