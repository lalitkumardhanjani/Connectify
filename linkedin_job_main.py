import time
import re
import os
import json
from datetime import datetime
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from linkedin_job_config import SEARCH_KEYWORDS_LIST, SEARCH_URLS
from linkedin_job_driver import (
    get_driver, wait_for_page, wait_for_search_results,
    wait_until_logged_in, inject_runtime_overlay, remove_runtime_overlay
)
from linkedin_job_helpers import decode_apply_redirect, normalize_external_url, extract_job_id
from linkedin_job_io import clean_json_outputs, load_saved_jobs, seen_external_urls

OUTPUT_FILE = "linkedin_jobs.json"

def is_already_saved(url):
    """Check if job URL already exists in Excel tracking list."""
    try:
        if not url:
            return False
        norm = normalize_external_url(decode_apply_redirect(url))
        _, existing = load_saved_jobs()
        return norm in existing
    except Exception:
        return False

def is_job_already_processed_json(company, position):
    """Check if job signature (company|position) already exists in JSON file."""
    try:
        if not os.path.exists(OUTPUT_FILE):
            return False
        with open(OUTPUT_FILE, 'r', encoding="utf-8") as f:
            existing_jobs = json.load(f)
        
        job_signature = f"{company.lower().strip()}|{position.lower().strip()}"
        for job in existing_jobs:
            existing_sig = f"{job.get('company', '').lower().strip()}|{job.get('position', '').lower().strip()}"
            if existing_sig == job_signature:
                return True
        return False
    except Exception as e:
        print(f"Error checking duplicates in JSON: {str(e)}")
        return False

def save_job_json(company, url, position):
    """Save the external job opportunity details to JSON output file."""
    jobs = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                jobs = json.load(f)
        except Exception:
            jobs = []
            
    existing_urls = [j.get("url") for j in jobs if j.get("url")]
    if url not in existing_urls:
        jobs.append({
            "type": "external_apply",
            "url": url,
            "company": company,
            "position": position,
            "saved_at": datetime.now().isoformat(),
            "status": "Pending"
        })
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=4)
        print(f"  [SAVED JSON] saved to {OUTPUT_FILE}: {url}")
    else:
        print("  [INFO] Job already exists in JSON. Skipping JSON save.")

def is_title_matching_keywords(title, keyword_list):
    """Check if the job title matches any keyword from the configured keyword list."""
    title_lower = title.lower()
    for kw in keyword_list:
        if kw.lower() in title_lower:
            return True
    return False

def load_processed_signatures_from_json():
    """Load all processed job signatures (company|position) from JSON to populate session tracking."""
    sigs = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                jobs = json.load(f)
            for j in jobs:
                comp = j.get("company", "").lower().strip()
                pos = j.get("position", "").lower().strip()
                if comp and pos:
                    sigs.add(f"{comp}|{pos}")
        except Exception as e:
            print(f"Error loading signatures: {e}")
    return sigs

def get_left_pane_container(driver):
    """Find and return the left list pane container element on LinkedIn."""
    for css in ['.jobs-search-results-list', '.scaffold-layout__list', 'div[class*="jobs-search-results-list"]']:
        try:
            el = driver.find_element(By.CSS_SELECTOR, css)
            if el.is_displayed():
                return el
        except Exception:
            pass
    return None

def get_job_cards(driver):
    """Scroll the left list pane and return all found job cards."""
    print("Loading job cards...")
    
    left_pane = get_left_pane_container(driver)

    previous_count = 0
    for _ in range(15):
        try:
            if left_pane:
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", left_pane)
            else:
                driver.execute_script("window.scrollBy(0, 1200);")
        except Exception:
            pass
        time.sleep(2)

        left_pane = get_left_pane_container(driver)
        if left_pane:
            cards = left_pane.find_elements(
                By.CSS_SELECTOR,
                'div[role="button"][componentkey*="job-card-component-ref"], div.job-card-container, li.jobs-search-results__list-item, div.job-card-list__item, div.jobs-search-results__list-item, .base-card'
            )
        else:
            cards = driver.find_elements(
                By.CSS_SELECTOR,
                'div[role="button"][componentkey*="job-card-component-ref"], div.job-card-container, li.jobs-search-results__list-item, div.job-card-list__item, div.jobs-search-results__list-item, .base-card'
            )
            
        # Filter for cards that actually contain a job view link
        valid_cards = []
        for c in cards:
            try:
                if c.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']"):
                    valid_cards.append(c)
            except Exception:
                pass
                
        print(f"Currently visible valid cards: {len(valid_cards)}")
        if len(valid_cards) == previous_count:
            break
        previous_count = len(valid_cards)

    left_pane = get_left_pane_container(driver)
    if left_pane:
        cards = left_pane.find_elements(
            By.CSS_SELECTOR,
            'div[role="button"][componentkey*="job-card-component-ref"], div.job-card-container, li.jobs-search-results__list-item, div.job-card-list__item, div.jobs-search-results__list-item, .base-card'
        )
    else:
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            'div[role="button"][componentkey*="job-card-component-ref"], div.job-card-container, li.jobs-search-results__list-item, div.job-card-list__item, div.jobs-search-results__list-item, .base-card'
        )
        
    valid_cards = []
    for c in cards:
        try:
            if c.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']"):
                valid_cards.append(c)
        except Exception:
            pass
    print(f"Final valid cards found: {len(valid_cards)}")
    return valid_cards


def go_to_next_jobs_page(driver):
    """Click the pagination next page control button."""
    try:
        print("Trying to move to next jobs page...")
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                'button.artdeco-pagination__button--next, button[aria-label="Next"], button[data-testid="pagination-controls-next-button-visible"], button[data-testid="pagination-controls-next-button"]'
            ))
        )
        disabled = driver.execute_script("""
            return arguments[0].disabled ||
                   arguments[0].getAttribute('disabled') !== null ||
                   arguments[0].getAttribute('aria-disabled') === 'true';
        """, next_button)

        if disabled:
            print("Next page button disabled")
            return False

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
        time.sleep(1)

        driver.execute_script("arguments[0].click();", next_button)
        print("Moved to next jobs page")
        time.sleep(6)
        return True
    except Exception as e:
        print(f"Could not move to next page: {str(e)}")
        return False

def run_automation(target_url=None):
    clean_json_outputs()
    driver = get_driver()

    try:
        driver.get("https://www.linkedin.com/login")

        if not wait_until_logged_in(driver, timeout_seconds=5):
            from linkedin_job_config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD
            try:
                driver.find_element(By.ID, "username").send_keys(LINKEDIN_EMAIL or "")
                driver.find_element(By.ID, "password").send_keys(LINKEDIN_PASSWORD or "")
                driver.find_element(By.XPATH, "//button[@type='submit']").click()
                if not wait_until_logged_in(driver, timeout_seconds=30):
                    print("Manual login required – complete in the browser.")
            except Exception as e:
                print(f"Auto-login failed: {e}")

        inject_runtime_overlay(driver)

        # Store the main window handle
        main_handle = driver.current_window_handle
        print(f"Main window handle: {main_handle}")

        # Load existing tracker urls
        _, existing_urls = load_saved_jobs()
        seen_external_urls.update(existing_urls)
        print(f"Loaded {len(existing_urls)} existing jobs from Excel tracker.\n")

        # Load time limit per keyword
        from user_config_manager import get_global_settings
        global_conf = get_global_settings()
        try:
            max_duration = int(global_conf.get("max_run_duration_seconds", 120))
        except ValueError:
            max_duration = 120

        print(f"Time limit per keyword: {max_duration} seconds")
        total_saved = 0
        session_lost = False
        processed_signatures = load_processed_signatures_from_json()
        processed_job_ids = set()

        for kw_i, (keyword, search_url) in enumerate(
            zip(SEARCH_KEYWORDS_LIST, SEARCH_URLS), start=1
        ):
            if session_lost:
                break

            print(f"\n{'='*60}")
            print(f"[KEYWORD {kw_i}/{len(SEARCH_KEYWORDS_LIST)}] {keyword}")
            print(f"{'='*60}")

            try:
                driver.get(search_url)
                print("Loading search results...")
                wait_for_page(8)
                wait_for_search_results(driver, timeout=20)
                wait_for_page(2)
                # Handle optional search results layout verification / optional filters
                wait_for_page(2)

                page_no = 1
                keyword_start_time = time.time()

                while True:
                    elapsed = time.time() - keyword_start_time
                    if elapsed >= max_duration:
                        print(f"Time limit reached for keyword '{keyword}' ({int(elapsed)}s >= {max_duration}s). Moving to next keyword.")
                        break

                    print(f"\n[PAGE {page_no}] Keyword: '{keyword}' (Elapsed: {int(elapsed)}s)")

                    job_cards = get_job_cards(driver)
                    if not job_cards:
                        print("No jobs found on current page.")
                        break

                    print(f"Found {len(job_cards)} jobs on page {page_no}")

                    for index in range(len(job_cards)):
                        # Check time limit inside loop
                        elapsed = time.time() - keyword_start_time
                        if elapsed >= max_duration:
                            print(f"Time limit reached during card processing ({int(elapsed)}s >= {max_duration}s).")
                            break

                        sig = ""
                        job_id = ""
                        try:
                            # Refresh elements to avoid StaleElementReferenceException
                            left_pane = get_left_pane_container(driver)
                            if left_pane:
                                job_cards = left_pane.find_elements(
                                    By.CSS_SELECTOR,
                                    'div[role="button"][componentkey*="job-card-component-ref"], div.job-card-container, li.jobs-search-results__list-item, div.job-card-list__item, div.jobs-search-results__list-item, .base-card'
                                )
                            else:
                                job_cards = driver.find_elements(
                                    By.CSS_SELECTOR,
                                    'div[role="button"][componentkey*="job-card-component-ref"], div.job-card-container, li.jobs-search-results__list-item, div.job-card-list__item, div.jobs-search-results__list-item, .base-card'
                                )
                            valid_cards = []
                            for c in job_cards:
                                try:
                                    if c.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']"):
                                        valid_cards.append(c)
                                except Exception:
                                    pass

                            if index >= len(valid_cards):
                                break

                            card = valid_cards[index]

                            # Scroll card into viewport
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                            time.sleep(2)

                            # Extract position/job title
                            position = ""
                            try:
                                title_el = card.find_element(By.CSS_SELECTOR, 'p span[aria-hidden="true"]')
                                position = title_el.text.strip()
                            except Exception:
                                try:
                                    title_el = card.find_element(By.CSS_SELECTOR, 'a[href*="/jobs/view/"]')
                                    position = title_el.text.strip()
                                except Exception:
                                    pass

                            position = position.replace("(Verified job)", "").strip()

                            # Extract Company Name
                            company = ""
                            try:
                                company_el = card.find_element(By.XPATH, './/div[@data-display-contents="true"]/following-sibling::div[1]//p')
                                company = company_el.text.strip()
                            except Exception:
                                try:
                                    company_el = card.find_element(
                                        By.CSS_SELECTOR,
                                        'a[href*="/company/"], .job-card-container__company-name, .job-card-list__company-name, .base-search-card__subtitle, .artdeco-entity-lockup__subtitle'
                                    )
                                    company = company_el.text.strip()
                                except Exception:
                                    pass

                            if company:
                                company = company.split('\n')[0].strip()
                            if not company:
                                company = "Unknown Company"

                            # Extract Job ID and Card URL
                            card_url = ""
                            try:
                                card_a = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
                                card_url = card_a.get_attribute("href")
                                job_id = extract_job_id(card_url)
                            except Exception:
                                pass

                            sig = f"{company.lower().strip()}|{position.lower().strip()}"

                            print(f"\n  --- Job {index + 1}/{len(valid_cards)} (Page {page_no}) ---")
                            print(f"  Title  : {position}")
                            print(f"  Company: {company}")
                            if job_id:
                                print(f"  Job ID : {job_id}")

                            # Check duplicates/processed state early
                            if job_id and job_id in processed_job_ids:
                                print(f"  [SKIP] Job ID {job_id} already processed in this run.")
                                continue
                            if sig in processed_signatures:
                                print("  [SKIP] Job already processed (session signature check).")
                                if job_id:
                                    processed_job_ids.add(job_id)
                                continue
                            if is_job_already_processed_json(company, position):
                                print("  [SKIP] Job already processed (JSON signature check).")
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                                continue

                            # Click job card to load right details pane
                            driver.execute_script("arguments[0].click();", card)
                            time.sleep(3)

                            # Find right details pane to wait for buttons
                            right_pane = None
                            for css in ['.jobs-search__job-details', '.jobs-details', '#job-details', '.scaffold-layout__detail']:
                                try:
                                    el = driver.find_element(By.CSS_SELECTOR, css)
                                    if el.is_displayed():
                                        right_pane = el
                                        break
                                except Exception:
                                    continue

                            target_container = right_pane if right_pane else driver

                            # Wait until Apply / Easy Apply buttons are loaded
                            try:
                                WebDriverWait(driver, 15).until(
                                    EC.presence_of_element_located((
                                        By.CSS_SELECTOR,
                                        """
                                        a[aria-label*='Easy Apply'],
                                        button[aria-label*='Easy Apply'],
                                        a[aria-label*='Apply on company website'],
                                        button[aria-label*='Apply on company website'],
                                        a[href*='linkedin.com/safety/go'],
                                        button.jobs-apply-button,
                                        a.jobs-apply-button
                                        """
                                    ))
                                )
                            except Exception:
                                print("  Apply section load timeout.")

                            time.sleep(2)

                            # Find all candidate Apply/Easy Apply buttons inside the container
                            apply_buttons = []
                            candidate_selectors = [
                                "a[aria-label*='Easy Apply']",
                                "button[aria-label*='Easy Apply']",
                                "a[aria-label*='Apply on company website']",
                                "button[aria-label*='Apply on company website']",
                                "a[href*='linkedin.com/safety/go']",
                                "button.jobs-apply-button",
                                "a.jobs-apply-button",
                                ".jobs-apply-button"
                            ]
                            for selector in candidate_selectors:
                                try:
                                    els = target_container.find_elements(By.CSS_SELECTOR, selector)
                                    for el in els:
                                        if el.is_displayed() and el not in apply_buttons:
                                            apply_buttons.append(el)
                                except Exception:
                                    continue

                            is_easy_apply = False
                            external_apply_btn = None
                            for btn in apply_buttons:
                                try:
                                    text = (btn.text or btn.get_attribute("aria-label") or "").lower()
                                    if "easy apply" in text:
                                        is_easy_apply = True
                                        break
                                    elif "apply" in text:
                                        external_apply_btn = btn
                                except Exception:
                                    continue

                            if is_easy_apply:
                                print("  [SKIP] Easy Apply job. Skipping completely.")
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                                continue

                            if not external_apply_btn:
                                print("  [SKIP] No regular Apply button found.")
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                                continue

                            original_tab = driver.current_window_handle
                            pre_click_handles = driver.window_handles

                            # Click external Apply button directly in browser to trigger new tab
                            print("  Clicking the external Apply button...")
                            driver.execute_script("arguments[0].click();", external_apply_btn)

                            # Wait up to 10 seconds for a new tab to open
                            new_handle = None
                            for _ in range(20):
                                time.sleep(0.5)
                                current_handles = driver.window_handles
                                for h in current_handles:
                                    if h not in pre_click_handles:
                                        new_handle = h
                                        break
                                if new_handle:
                                    break

                            if not new_handle:
                                print("  [WARNING] Clicked Apply but no new tab opened.")
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                                continue

                            # Switch to external tab
                            driver.switch_to.window(new_handle)
                            time.sleep(5)  # Wait for redirects to settle

                            external_url = driver.current_url
                            print(f"  Settled External URL: {external_url}")

                            # Check duplicate in Excel
                            if is_already_saved(external_url):
                                print("  [SKIP] Job already saved in Excel tracker.")
                                driver.close()
                                driver.switch_to.window(original_tab)
                                time.sleep(2)
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                                continue

                            # Check if job title matches any keyword from our configured list
                            if is_title_matching_keywords(position, SEARCH_KEYWORDS_LIST):
                                # Store to JSON
                                save_job_json(company, external_url, position)
                                # Store to Excel to update Pipeline database records
                                try:
                                    from linkedin_job_io import save_job as excel_save_job
                                    if excel_save_job({
                                        "url": external_url,
                                        "company": company,
                                        "search_keyword": keyword
                                    }):
                                        total_saved += 1
                                        print("  [SUCCESS] Job stored in Excel tracker.")
                                except Exception as e:
                                    print(f"  [ERROR] Excel save error: {e}")
                            else:
                                print(f"  [SKIP] Title '{position}' does not match configured SEARCH_KEYWORDS_LIST.")

                            # Close external tab and switch back to search page
                            driver.close()
                            driver.switch_to.window(original_tab)
                            time.sleep(2)

                            # Mark as processed in session
                            processed_signatures.add(sig)
                            if job_id:
                                processed_job_ids.add(job_id)

                        except Exception as e:
                            print(f"  Error processing job {index + 1}: {str(e)}")
                            # Recovery: close any extra handles and switch back to main
                            try:
                                handles = driver.window_handles
                                if len(handles) > 1:
                                    for h in handles:
                                        if h != main_handle:
                                            driver.switch_to.window(h)
                                            driver.close()
                                driver.switch_to.window(main_handle)
                            except Exception:
                                pass
                            # Ensure we mark it processed to avoid looping
                            try:
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                            except Exception:
                                pass
                            continue

                    # Navigate to next page
                    moved = go_to_next_jobs_page(driver)
                    if not moved:
                        print("No more pages available.")
                        break
                    page_no += 1

            except (InvalidSessionIdException, WebDriverException) as e:
                print(f"Session lost: {e}")
                session_lost = True
                break

        print(f"\n{'='*60}")
        print(f"[COMPLETE] Total jobs saved: {total_saved}")
        print(f"{'='*60}")

    finally:
        try:
            remove_runtime_overlay(driver)
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    run_automation()
