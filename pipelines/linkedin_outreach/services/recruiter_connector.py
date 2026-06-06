import os
import sys
import time
import random
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config.settings import LINKEDIN_CONNECT_LOG_FILE
from config.user_profiles import get_selected_user_config, get_global_settings, substitute_template_variables
from core.integrations.selenium_driver import get_driver
from core.storage.database import load_jobs_for_referral, update_status_by_id
from core.logging.config import setup_logger

# Reuse Selenium action helper functions from the main connector module
from pipelines.linkedin_outreach.services.connector import (
    login_to_linkedin,
    find_people_with_connect_button,
    send_connection_request,
    go_to_next_page
)

logger = setup_logger(LINKEDIN_CONNECT_LOG_FILE)

def get_recruiter_message(company=None, first_name=None, resume_link=None):
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    recruiter_conf = user_conf.get("recruiter_outreach", {})
    
    template = recruiter_conf.get("message_template")
    if not template:
        template = "Hi {first_name}, let's connect! I saw you handle Talent Acquisition at {company}. I am looking for DBA opportunities. My resume: {resume}"

    if not resume_link:
        resume_link = profile.get("resume_url", "")
    
    extra_vars = {
        "{company}": company or "the company",
        "{resume}": resume_link or "",
        "{first_name}": first_name or "there",
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()

def run_recruiter_connector():
    logger.info("=" * 60)
    logger.info("LinkedIn Recruiter Outreach Automation Starting...")
    
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    
    recruiter_conf = user_conf.get("recruiter_outreach", {})
    review_mode = recruiter_conf.get("review_mode", True)
    daily_limit = int(recruiter_conf.get("daily_limit") or 5)
    interval = int(recruiter_conf.get("interval") or 120)
    target_count = int(recruiter_conf.get("target_count") or 2)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    resume_link = user_conf.get("profile", {}).get("resume_url", "")
    
    logger.info(f"REVIEW_MODE  : {review_mode}")
    logger.info(f"DAILY_LIMIT  : {daily_limit}")
    logger.info(f"INTERVAL     : {interval}")
    logger.info(f"TARGET_COUNT : {target_count}")
    logger.info("=" * 60)

    job_data = load_jobs_for_referral(status_filter='Asked for Referral')
    if not job_data:
        logger.error("No jobs with status 'Asked for Referral' found in database. Exiting...")
        return

    logger.info(f"Loaded {len(job_data)} jobs with status 'Asked for Referral'.")

    try:
        driver = get_driver()
    except Exception as e:
        logger.error(f"Error starting Chrome: {e}")
        sys.exit(1)

    total_requests_sent = 0

    try:
        driver.get("https://www.linkedin.com/feed/")
        if not login_to_linkedin(driver, email, password):
            logger.error("Failed to login to LinkedIn. Exiting...")
            sys.exit(1)

        for job in job_data:
            if total_requests_sent >= daily_limit:
                logger.info(f"Daily limit of {daily_limit} reached for this run. Stopping.")
                break

            company = job.get('CompanyName') or ''
            job_id = job.get('JobID') or ''

            logger.info("\n" + "=" * 60)
            logger.info(f"Processing Recruiter Outreach for: {company}")
            logger.info("=" * 60)

            # Search strategy: Company Name + Talent Acquisition
            search_query = f"{company} Talent Acquisition"
            logger.info(f"Searching LinkedIn for: '{search_query}'")
            
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={search_query.replace(' ', '%20')}&origin=FACETED_SEARCH"
            driver.get(search_url)
            time.sleep(4)

            # Send connect requests to recruiters found in search results
            page_number = 1
            company_requests_sent = 0
            max_recruiters_per_company = target_count

            while company_requests_sent < max_recruiters_per_company and total_requests_sent < daily_limit:
                logger.info(f"\nProcessing search page {page_number} for recruiters")
                remaining_limit = min(max_recruiters_per_company - company_requests_sent, daily_limit - total_requests_sent)
                
                people = find_people_with_connect_button(driver, max_people=remaining_limit)

                if not people:
                    logger.warning("No connectable recruiter profiles found on this page")
                    if not go_to_next_page(driver):
                        logger.warning("No more pages available")
                        break
                    page_number += 1
                    continue

                for person in people:
                    if company_requests_sent >= max_recruiters_per_company or total_requests_sent >= daily_limit:
                        break
                    try:
                        first_name = person.get('name', 'unknown').split()[0] if person.get('name') else "there"
                        message = get_recruiter_message(
                            company=company,
                            first_name=first_name,
                            resume_link=resume_link,
                        )
                        if len(message) > 300:
                            message = message[:297] + "..."

                        sent = send_connection_request(driver, person, message, review_mode=review_mode)
                        if sent == "skipped":
                            logger.info(f"Skipping recruiter connect request to {person.get('name', 'unknown')}")
                            continue
                        elif sent == "quit":
                            logger.info("Quitting recruiter outreach loop as requested by user.")
                            return
                        elif sent:
                            company_requests_sent += 1
                            total_requests_sent += 1
                            logger.info(f"Recruiter connect requests sent: {company_requests_sent}/{max_recruiters_per_company} for {company}")
                            logger.info(f"Total connect requests sent in this run: {total_requests_sent}/{daily_limit}")
                    except Exception as e:
                        logger.warning(f"Failed sending recruiter connect request: {str(e)}")
                    time.sleep(random.randint(3, 7))

                if company_requests_sent >= max_recruiters_per_company or total_requests_sent >= daily_limit:
                    break

                if not go_to_next_page(driver):
                    break
                page_number += 1

            # Mark this job as Done after outreach attempts if recruiter target reached
            if company_requests_sent >= max_recruiters_per_company:
                try:
                    update_status_by_id(job_id, 'Done')
                    logger.info(f"Updated company '{company}' status in tracker to 'Done'.")
                except Exception as e:
                    logger.warning(f"Failed to record status update: {e}")
            else:
                logger.info(f"Finished processing '{company}' but target count {max_recruiters_per_company} not reached ({company_requests_sent} sent). Keeping status.")

            time.sleep(5)

        logger.info("\n" + "=" * 60)
        logger.info("All recruiter outreach jobs processed!")
        logger.info("=" * 60)
        if sys.stdin.isatty():
            input("\nPress Enter to close the browser...")

    except Exception:
        logger.exception("Fatal error in recruiter outreach connector script")
        if sys.stdin.isatty():
            input("\nFatal error occurred. Press Enter to exit...")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    run_recruiter_connector()
