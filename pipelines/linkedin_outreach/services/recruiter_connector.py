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
from core.storage.database import (
    load_jobs_for_referral,
    update_status_by_id,
    is_profile_already_contacted,
    load_all_referrals,
    add_or_update_referral,
    get_recruiter_outreach_progress
)
from core.logging.config import setup_logger

# Reuse Selenium action helper functions from the main connector module
from pipelines.linkedin_outreach.services.connector import (
    login_to_linkedin,
    find_people_with_connect_button,
    send_connection_request,
    go_to_next_page
)

logger = setup_logger(LINKEDIN_CONNECT_LOG_FILE)

def get_recruiter_message(company=None, first_name=None, resume_link=None, person_name=None):
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
    
    resolved_person_name = "there"
    if person_name:
        resolved_person_name = person_name.split()[0] if person_name.strip() else "there"
    elif first_name:
        resolved_person_name = first_name

    extra_vars = {
        "{company}": company or "the company",
        "{resume}": resume_link or "",
        "{first_name}": first_name or "there",
        "{PERSON_NAME}": resolved_person_name,
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()


def get_recruiter_direct_message(company=None, first_name=None, resume_link=None, person_name=None):
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    recruiter_conf = user_conf.get("recruiter_outreach", {})
    
    template = recruiter_conf.get("direct_message_template")
    if not template:
        template = "Hi {first_name}, hope you are doing well. I noticed you handle Talent Acquisition at {company}. I wanted to share my profile for DBA roles. My resume: {resume}. Let me know if you have any open roles!"

    if not resume_link:
        resume_link = profile.get("resume_url", "")
    
    resolved_person_name = "there"
    if person_name:
        resolved_person_name = person_name.split()[0] if person_name.strip() else "there"
    elif first_name:
        resolved_person_name = first_name

    extra_vars = {
        "{company}": company or "the company",
        "{resume}": resume_link or "",
        "{first_name}": first_name or "there",
        "{PERSON_NAME}": resolved_person_name,
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()


def run_recruiter_discovery():
    """Phase 1: Discover connected 1st-degree recruiters at target companies."""
    logger.info("=" * 60)
    logger.info("Phase 1: Discovering Connected Recruiters...")
    logger.info("=" * 60)
    
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    recruiter_conf = user_conf.get("recruiter_outreach", {})
    max_recruits = int(recruiter_conf.get("target_count") or 2)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    
    job_data = load_jobs_for_referral(status_filter='Asked for Referral')
    if not job_data:
        logger.info("No jobs with status 'Asked for Referral' found. Nothing to discover.")
        return
 
    try:
        driver = get_driver()
    except Exception as e:
        logger.error(f"Error starting Chrome: {e}")
        sys.exit(1)

    try:
        driver.get("https://www.linkedin.com/feed/")
        if not login_to_linkedin(driver, email, password):
            logger.error("Failed to login to LinkedIn. Exiting...")
            sys.exit(1)

        from pipelines.linkedin_outreach.services.referral_outreach import scrape_connections_from_search

        for job in job_data:
            company = job.get('CompanyName') or ''
            job_id = job.get('JobID') or ''
            
            # Update current Job Lead status to In Progress
            try:
                update_status_by_id(job_id, 'In Progress')
            except Exception as e:
                logger.warning(f"Failed to update Job status to In Progress: {e}")

            # Check company target recruiters progress (total active/pending recruiter outreach count)
            total_progress = get_recruiter_outreach_progress(company)
            if total_progress >= max_recruits:
                logger.info(f"Target recruiter count of {max_recruits} already reached/discovered for {company} (progress: {total_progress}). Skipping discovery.")
                try:
                    update_status_by_id(job_id, 'Done')
                except Exception as e:
                    logger.warning(f"Failed to update Job status to Done: {e}")
                continue

            remaining_cap = max_recruits - total_progress
            logger.info(f"\nProcessing company for recruiter discovery: {company} (JobID {job_id}). Remaining target capacity: {remaining_cap}")
            
            search_query = f"{company} Talent Acquisition"
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={search_query.replace(' ', '%20')}&network=%5B%22F%22%5D"
            
            logger.info(f"Navigating to search URL: {search_url}")
            driver.get(search_url)
            time.sleep(4)
            
            connections = scrape_connections_from_search(driver, max_people=remaining_cap)
            if not connections:
                logger.info(f"No 1st-degree recruiters found at {company}.")
                continue
                
            discovered_count = 0
            for conn in connections:
                profile_url = conn['profile_url']
                
                # Check eligibility
                if is_profile_already_contacted(profile_url):
                    logger.info(f"Recruiter connection {conn['name']} already contacted or skipped. Skipping.")
                    continue
                    
                referral_data = {
                    'JobID': job_id,
                    'CompanyName': company,
                    'Referral_Person_Name': conn['name'],
                    'Referral_Person_Email': '',
                    'Referral_Person_Profile_URL': profile_url,
                    'Referral_Person_Designation': conn['designation'],
                    'Referral_Source': 'Existing Recruiter',
                    'Referral_Status': 'Pending'
                }
                
                add_or_update_referral(referral_data)
                discovered_count += 1
                logger.info(f"Discovered Recruiter: {conn['name']} ({conn['designation']}) - Pending outreach")
                
            logger.info(f"Found and stored {discovered_count} new 1st-degree recruiter contacts for {company}.")
            time.sleep(2)
            
    except Exception as e:
        logger.error(f"Fatal error in recruiter discovery: {e}")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()


def run_recruiter_messaging():
    """Phase 2: Message pending recruiter connections and verify delivery."""
    logger.info("=" * 60)
    logger.info("Phase 2: Sending Recruiter Messages...")
    logger.info("=" * 60)
    
    user_conf = get_selected_user_config()
    profile = user_conf.get("profile", {})
    global_conf = get_global_settings()
    recruiter_conf = user_conf.get("recruiter_outreach", {})
    review_mode = recruiter_conf.get("review_mode", True)
    interval = int(recruiter_conf.get("interval") or 5)
    max_recruits = int(recruiter_conf.get("target_count") or 2)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    
    all_referrals = load_all_referrals()
    pending = [
        r for r in all_referrals
        if str(r.get('Referral_Status')).strip().lower() == 'pending'
        and str(r.get('Referral_Source') or '').strip().startswith('Recruiter')
    ]
    
    if not pending:
        logger.info("No pending recruiter connections found for outreach.")
        return
        
    logger.info(f"Found {len(pending)} pending recruiter connection messages to process.")
    
    try:
        driver = get_driver()
    except Exception as e:
        logger.error(f"Error starting Chrome: {e}")
        sys.exit(1)

    sent_count = 0
    try:
        driver.get("https://www.linkedin.com/feed/")
        if not login_to_linkedin(driver, email, password):
            logger.error("Failed to login to LinkedIn. Exiting...")
            sys.exit(1)

        from pipelines.linkedin_outreach.services.referral_outreach import (
            open_messaging_from_profile,
            insert_message_draft,
            upload_resume_attachment,
            prompt_referral_action,
            click_send_message,
            verify_delivery,
            close_chat_window
        )

        # Close any chat overlays restored by LinkedIn session state on start
        logger.info("Performing initial post-login chat window cleanup...")
        close_chat_window(driver)

        for idx, ref in enumerate(pending):
            ref_id = ref.get('ReferralID')
            job_id = str(ref.get('JobID'))
            company = ref.get('CompanyName')
            name = ref.get('Referral_Person_Name')
            profile_url = ref.get('Referral_Person_Profile_URL')
            designation = ref.get('Referral_Person_Designation')
            
            # Check company target recruiters progress
            total_progress = get_recruiter_outreach_progress(company)
            if total_progress >= max_recruits:
                logger.info(f"Target recruiter count of {max_recruits} already reached for {company} (progress: {total_progress}). Skipping messaging.")
                continue

            logger.info("\n" + "=" * 60)
            logger.info(f"Processing recruiter message to {name} ({company})")
            logger.info("=" * 60)
            
            # Final eligibility check
            if is_profile_already_contacted(profile_url):
                logger.info(f"Eligibility Check: profile {profile_url} already messaged. Skipping.")
                ref['Referral_Status'] = 'Skipped'
                add_or_update_referral(ref)
                continue
                
            # Close any leftover chat windows first to avoid pasting into previous chats
            close_chat_window(driver)
            
            driver.get(profile_url)
            time.sleep(4)
            
            if not open_messaging_from_profile(driver, name=name):
                logger.warning(f"Could not open messaging for {name}. Message button not found or hidden.")
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Message button not found on profile'
                add_or_update_referral(ref)
                continue
                
            first_name = name.split()[0] if name else "there"
            message_text = get_recruiter_direct_message(
                company=company,
                first_name=first_name,
                person_name=name,
            )
            
            if len(message_text) > 1000:
                logger.warning("Message exceeds 1000 characters. Truncating.")
                message_text = message_text[:997] + "..."
                
            inserted = insert_message_draft(driver, message_text)
            if not inserted:
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Failed to insert text into chat box'
                add_or_update_referral(ref)
                close_chat_window(driver)
                continue
                
            # Attempt to upload local resume PDF as attachment
            upload_resume_attachment(driver, profile)
                
            # Invite Quality Gate (Prompt action after the text draft is ready in browser)
            action = prompt_referral_action(name, review_mode=review_mode)
            
            if action == "skip":
                logger.info(f"Skipped recruiter outreach to {name} by user.")
                ref['Referral_Status'] = 'Skipped'
                add_or_update_referral(ref)
                close_chat_window(driver)
                continue
            elif action == "quit":
                logger.info("Quitting recruiter outreach pipeline as requested.")
                try:
                    update_status_by_id(job_id, 'Cancelled')
                except Exception as e:
                    logger.warning(f"Failed to update Job status to Cancelled: {e}")
                close_chat_window(driver)
                sys.exit(2)
                
            sent = click_send_message(driver)
            if sent:
                # Delivery Verification
                verified = verify_delivery(driver, message_text)
                if verified:
                    ref['Referral_Status'] = 'Sent'
                    ref['Sent_Time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ref['Error_Reason'] = ''
                    sent_count += 1
                else:
                    ref['Referral_Status'] = 'Failed'
                    ref['Error_Reason'] = 'Message clicked but did not appear in chat history'
            else:
                ref['Referral_Status'] = 'Failed'
                ref['Error_Reason'] = 'Failed to click send button'
                
            add_or_update_referral(ref)
            close_chat_window(driver)
            
            logger.info(f"Recruiter messages sent: {sent_count}")
            if idx < len(pending) - 1:
                logger.info(f"Waiting for {interval} seconds before next outreach...")
                time.sleep(interval)

    except Exception as e:
        logger.error(f"Fatal error in recruiter outreach messaging: {e}")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()


def run_recruiter_connector():
    logger.info("=" * 60)
    logger.info("LinkedIn Recruiter Outreach Automation Starting...")
    
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    
    recruiter_conf = user_conf.get("recruiter_outreach", {})
    review_mode = recruiter_conf.get("review_mode", True)
    interval = int(recruiter_conf.get("interval") or 120)
    target_count = int(recruiter_conf.get("target_count") or 2)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    resume_link = user_conf.get("profile", {}).get("resume_url", "")
    
    logger.info(f"REVIEW_MODE  : {review_mode}")
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
            company = job.get('CompanyName') or ''
            job_id = job.get('JobID') or ''

            # Check company target recruiters progress
            total_progress = get_recruiter_outreach_progress(company)
            if total_progress >= target_count:
                logger.info(f"Company '{company}' has already reached its target recruiter count of {target_count} (progress: {total_progress}). Skipping.")
                try:
                    update_status_by_id(job_id, 'Done')
                except Exception as e:
                    logger.warning(f"Failed to update Job status to Done: {e}")
                continue

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
            max_recruiters_per_company = target_count - total_progress

            while company_requests_sent < max_recruiters_per_company:
                logger.info(f"\nProcessing search page {page_number} for recruiters")
                remaining_limit = max_recruiters_per_company - company_requests_sent
                
                people = find_people_with_connect_button(driver, max_people=remaining_limit)

                if not people:
                    logger.warning("No connectable recruiter profiles found on this page")
                    if not go_to_next_page(driver):
                        logger.warning("No more pages available")
                        break
                    page_number += 1
                    continue

                for person in people:
                    if company_requests_sent >= max_recruiters_per_company:
                        break
                    try:
                        raw_name = person.get('name') or ''
                        first_name = raw_name.split()[0] if raw_name else "there"
                        message = get_recruiter_message(
                            company=company,
                            first_name=first_name,
                            resume_link=resume_link,
                            person_name=raw_name,
                        )
                        if len(message) > 300:
                            message = message[:297] + "..."

                        sent = send_connection_request(driver, person, message, review_mode=review_mode)
                        
                        status_val = 'Sent'
                        error_reason = ''
                        if sent == "skipped":
                            logger.info(f"Skipping recruiter connect request to {person.get('name', 'unknown')}")
                            status_val = 'Skipped'
                        elif sent == "quit":
                            logger.info("Quitting recruiter outreach loop as requested by user.")
                            try:
                                update_status_by_id(job_id, 'Cancelled')
                            except Exception as e:
                                logger.warning(f"Failed to update Job status to Cancelled: {e}")
                            sys.exit(2)
                        elif sent:
                            company_requests_sent += 1
                            total_requests_sent += 1
                            logger.info(f"Recruiter connect requests sent: {company_requests_sent}/{max_recruiters_per_company} for {company}")
                            logger.info(f"Total connect requests sent in this run: {total_requests_sent}")
                            status_val = 'Sent'
                        else:
                            status_val = 'Failed'
                            error_reason = 'Connection invitation note could not be sent to recruiter'

                        if sent != "quit":
                            try:
                                referral_data = {
                                    'JobID': job_id,
                                    'CompanyName': company,
                                    'Referral_Person_Name': person.get('name', 'unknown'),
                                    'Referral_Person_Email': '',
                                    'Referral_Person_Profile_URL': person.get('profile_url', ''),
                                    'Referral_Person_Designation': person.get('role', 'Recruiter'),
                                    'Referral_Source': 'Sent Recruiter Connection',
                                    'Referral_Status': status_val,
                                    'Sent_Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status_val == 'Sent' else '',
                                    'Error_Reason': error_reason
                                }
                                add_or_update_referral(referral_data)
                            except Exception as ex:
                                logger.warning(f"Failed to save recruiter connection request referral details to Excel: {ex}")

                        if sent == "skipped":
                            continue
                    except Exception as e:
                        logger.warning(f"Failed sending recruiter connect request: {str(e)}")
                    time.sleep(random.randint(3, 7))

                if company_requests_sent >= max_recruiters_per_company:
                    break

                if not go_to_next_page(driver):
                    break
                page_number += 1

            # Mark this job as Done after outreach attempts if recruiter target reached
            # Calculate total recruiter outreach progress
            total_recruits_progress = get_recruiter_outreach_progress(company)
            if total_recruits_progress >= target_count:
                try:
                    update_status_by_id(job_id, 'Done')
                    logger.info(f"Updated company '{company}' status in tracker to 'Done'.")
                except Exception as e:
                    logger.warning(f"Failed to record status update: {e}")
            else:
                try:
                    update_status_by_id(job_id, 'Completed – Target Not Met')
                    logger.info(f"Finished recruiter processing for '{company}' but target count {target_count} not reached (current progress: {total_recruits_progress}). Updated status to 'Completed – Target Not Met'.")
                except Exception as e:
                    logger.warning(f"Failed to record status update: {e}")

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
