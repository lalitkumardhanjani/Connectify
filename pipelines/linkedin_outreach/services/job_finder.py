import time
import os
import json
import urllib.parse
from datetime import datetime
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config.user_profiles import get_selected_user_config, get_global_settings
from config.constants import LINKEDIN_CONNECT_KEYWORDS_DEFAULT
from core.integrations.selenium_driver import get_driver, wait_for_page, inject_runtime_overlay, remove_runtime_overlay
from core.utils.url_utils import decode_apply_redirect, normalize_external_url, extract_job_id, is_valid_external_url
from core.storage.database import load_saved_jobs, save_job, init_job_leads_store, seen_external_urls
from core.logging.config import logger
from core.utils.string_utils import parse_preferred_locations


def is_already_saved(url):
    """Check if job URL already exists in Excel tracking list."""
    try:
        if not url:
            return False
        norm = normalize_external_url(decode_apply_redirect(url))
        jobs = load_saved_jobs()
        existing = {normalize_external_url(j.get("CompanyURL") or "") for j in jobs if j.get("CompanyURL")}
        return norm in existing
    except Exception:
        return False

def is_job_already_processed_excel(company, position):
    """Check if job signature (company|position) already exists in Excel tracker."""
    try:
        jobs = load_saved_jobs()
        job_signature = f"{company.lower().strip()}|{position.lower().strip()}"
        for job in jobs:
            existing_sig = f"{job.get('CompanyName', '').lower().strip()}|{job.get('JobTitle', '').lower().strip()}"
            if existing_sig == job_signature:
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking duplicates in Excel: {str(e)}")
        return False

def is_title_matching_keywords(title, keyword_list):
    """Check if the job title matches any keyword from the configured keyword list."""
    title_lower = title.lower()
    for kw in keyword_list:
        if str(kw).lower().strip() in title_lower:
            return True
    return False

def load_processed_signatures_from_excel():
    """Load all processed job signatures (company|position) from Excel to populate session tracking."""
    sigs = set()
    try:
        jobs = load_saved_jobs()
        for j in jobs:
            comp = j.get("CompanyName", "").lower().strip()
            pos = j.get("JobTitle", "").lower().strip()
            if comp and pos:
                sigs.add(f"{comp}|{pos}")
    except Exception as e:
        logger.error(f"Error loading signatures from Excel: {e}")
    return sigs

def get_left_pane_container(driver):
    """Find and return the left list pane container element on LinkedIn using JS overflow detection."""
    try:
        container = driver.execute_script("""
            const selectors = [
                '.jobs-search-results-list',
                '.scaffold-layout__list',
                'div[class*="jobs-search-results-list"]',
                '.jobs-search-results-list__list',
                'ul.jobs-search__results-list'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.scrollHeight > el.clientHeight) {
                    return el;
                }
            }
            const col = document.querySelector('.jobs-search-two-pane__a') || 
                        document.querySelector('.jobs-search') || 
                        document.querySelector('div[class*="jobs-search-two-pane"]') ||
                        document.body;
            const allDivs = col.querySelectorAll('div, ul, section');
            for (const el of allDivs) {
                const style = window.getComputedStyle(el);
                if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                    return el;
                }
            }
            return null;
        """)
        if container:
            return container
    except Exception as e:
        logger.warning(f"Error in JS-based left pane detection: {e}")

    for css in [
        '.jobs-search-results-list',
        '.scaffold-layout__list',
        'div[class*="jobs-search-results-list"]',
        'div.jobs-search-results__list',
        'div[class*="jobs-search-results"]',
        'ul.jobs-search__results-list'
    ]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, css)
            if el.is_displayed():
                return el
        except Exception:
            pass
    return None

def scroll_element_into_view_in_left_pane(driver, element):
    """Scroll the left list pane container to center the element without scrolling the main window."""
    try:
        left_pane = get_left_pane_container(driver)
        if left_pane:
            driver.execute_script("""
                const pane = arguments[0];
                const el = arguments[1];
                const paneRect = pane.getBoundingClientRect();
                const elRect = el.getBoundingClientRect();
                pane.scrollTop += (elRect.top - paneRect.top) - (paneRect.height / 2) + (elRect.height / 2);
            """, left_pane, element)
            return True
    except Exception as e:
        logger.warning(f"Error scrolling element in left pane container: {e}")
    
    # Fallback if container scrolling failed or container not found
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", element)
        return True
    except Exception as e:
        logger.warning(f"Fallback scrollIntoView failed: {e}")
    return False

def get_job_cards(driver):
    """Scroll the left list pane gradually to load all job cards and return them."""
    logger.info("Loading job cards by scrolling left pane gradually...")
    left_pane = get_left_pane_container(driver)
    
    # Progressive gradual scroll to trigger lazy loading of all cards
    try:
        pane = left_pane
        if not pane:
            for selector in [
                '.jobs-search-results-list',
                '.scaffold-layout__list',
                'div[class*="jobs-search-results-list"]',
                'div.jobs-search-results__list',
                'div[class*="jobs-search-results"]'
            ]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed():
                        pane = el
                        break
                except Exception:
                    pass

        if pane:
            logger.info("Starting progressive scroll on left pane...")
            current_scroll = 0
            no_change_count = 0
            
            for _ in range(40): # safety limit to prevent infinite loops
                # Get current scroll height
                scroll_height = driver.execute_script("return arguments[0].scrollHeight", pane)
                
                # Increment scroll position by a smaller step to ensure all intermediate cards load
                current_scroll += 300
                if current_scroll > scroll_height:
                    current_scroll = scroll_height
                    
                driver.execute_script("arguments[0].scrollTop = arguments[1]", pane, current_scroll)
                time.sleep(0.2)
                
                # Check if we reached the bottom of current scrollable area
                if current_scroll >= scroll_height:
                    # Wait to see if more jobs load and scroll_height increases
                    time.sleep(1.2)
                    new_scroll_height = driver.execute_script("return arguments[0].scrollHeight", pane)
                    if new_scroll_height == scroll_height:
                        no_change_count += 1
                        if no_change_count >= 3:  # Only stop if height doesn't change after 3 consecutive attempts
                            logger.info("Reached absolute bottom of job list.")
                            break
                    else:
                        no_change_count = 0 # reset because height increased
        else:
            logger.warning("Could not find scrollable pane for job cards, using window scroll fallback.")
            for offset in range(0, 4000, 350):
                driver.execute_script("window.scrollTo(0, arguments[0]);", offset)
                time.sleep(0.2)
    except Exception as e:
        logger.warning(f"Error during gradual scroll: {e}")

    time.sleep(1.0)
    
    card_selectors = (
        'li.jobs-search-results__list-item, '
        '.job-card-container, '
        'div.job-card-list__item, '
        'div[role="button"][componentkey*="job-card-component-ref"], '
        'div.jobs-search-results__list-item, '
        '.base-card'
    )
    
    left_pane = get_left_pane_container(driver)
    if left_pane:
        cards = left_pane.find_elements(By.CSS_SELECTOR, card_selectors)
    else:
        cards = driver.find_elements(By.CSS_SELECTOR, card_selectors)
        
    valid_cards = []
    seen_job_ids = set()
    for c in cards:
        try:
            links = c.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            if links:
                href = links[0].get_attribute("href")
                job_id = extract_job_id(href)
                if job_id:
                    if job_id not in seen_job_ids:
                        seen_job_ids.add(job_id)
                        valid_cards.append(c)
        except Exception:
            pass
            
    logger.info(f"Final valid cards found: {len(valid_cards)}")
    return valid_cards

def go_to_next_jobs_page(driver):
    """Click the pagination next page control button and validate success."""
    import urllib.parse
    
    # 1. Scroll the left list pane to the bottom multiple times to force pagination controls to render
    logger.info("Scrolling left list pane to load pagination...")
    for _ in range(3):
        left_pane = get_left_pane_container(driver)
        try:
            if left_pane:
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", left_pane)
            else:
                driver.execute_script("""
                    const panel = document.querySelector('.jobs-search-results-list') || 
                                  document.querySelector('.scaffold-layout__list') ||
                                  document.querySelector('div[class*="jobs-search-results-list"]');
                    if (panel) {
                        panel.scrollTop = panel.scrollHeight;
                    }
                """)
        except Exception:
            pass
        time.sleep(1)

    # Helper to get active page number
    def get_page_num():
        try:
            val = driver.execute_script("""
                const activeBtn = document.querySelector('li.artdeco-pagination__indicator.selected button, li.artdeco-pagination__indicator--selected button, button[aria-current="true"], .artdeco-pagination__button--selected');
                return activeBtn ? activeBtn.innerText.trim() : null;
            """)
            if val and val.isdigit():
                return int(val)
        except Exception:
            pass
        try:
            current_url = driver.current_url
            if 'start=' in current_url:
                parsed = urllib.parse.urlparse(current_url)
                params = urllib.parse.parse_qs(parsed.query)
                start_val = params.get('start', ['0'])[0]
                return int(start_val) // 25 + 1
        except Exception:
            pass
        return None

    # Helper to get top job IDs to check if list content updated
    def get_job_sigs():
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            signatures = []
            for c in cards[:5]:
                try:
                    href = c.get_attribute("href")
                    job_id = extract_job_id(href)
                    if job_id:
                        signatures.append(job_id)
                except Exception:
                    pass
            return signatures
        except Exception:
            return []

    # Get state before navigation
    initial_page = get_page_num()
    initial_sigs = get_job_sigs()
    logger.info(f"Current page number detected before pagination click: {initial_page}")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Trying to find Next Page button (Attempt {attempt}/{max_retries})...")
            
            # Find Next Page button using multiple potential selectors
            next_button_selectors = [
                "button[aria-label='View next page']",
                "button.jobs-search-pagination__button--next",
                "button[aria-label='Next page']",
                'button.artdeco-pagination__button--next',
                'button[aria-label="Next"]',
                'button[data-testid="pagination-controls-next-button-visible"]',
                'button[data-testid="pagination-controls-next-button"]',
                'li.artdeco-pagination__indicator--next button'
            ]
            
            next_button = None
            for selector in next_button_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        next_button = btn
                        break
                except Exception:
                    continue

            if not next_button:
                # Try finding by XPATH text
                try:
                    next_button = driver.find_element(By.XPATH, "//button[contains(span/text(), 'Next') or contains(text(), 'Next')]")
                except Exception:
                    pass

            if not next_button:
                logger.info("Next page button does not exist in DOM. Assuming end of results.")
                return False

            # Check if disabled
            disabled = driver.execute_script("""
                return arguments[0].disabled ||
                       arguments[0].getAttribute('disabled') !== null ||
                       arguments[0].getAttribute('aria-disabled') === 'true' ||
                       arguments[0].classList.contains('artdeco-button--disabled');
            """, next_button)

            if disabled:
                logger.info("Next page button exists but is disabled. End of results reached.")
                return False

            # Scroll button into center without scrolling window/details panel
            scroll_element_into_view_in_left_pane(driver, next_button)
            time.sleep(1)

            # Click
            logger.info("Clicking the Next Page button...")
            try:
                next_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", next_button)

            # Wait for navigation to complete (verify page number changed or jobs changed)
            success = False
            for _ in range(16): # wait up to 8 seconds
                time.sleep(0.5)
                current_page = get_page_num()
                current_sigs = get_job_sigs()
                
                page_changed = (current_page is not None and initial_page is not None and current_page != initial_page)
                jobs_changed = (current_sigs and initial_sigs and current_sigs != initial_sigs)
                
                # If either indicator is met, navigation succeeded
                if page_changed or jobs_changed:
                    logger.info(f"Successfully navigated to next page. New Page: {current_page}")
                    success = True
                    break

            if success:
                # Wait for page content to settle
                time.sleep(3)
                return True
            else:
                logger.warning(f"Click action succeeded but page validation failed (page/jobs did not change). Retrying...")
                
        except Exception as e:
            logger.warning(f"Error during pagination attempt {attempt}: {str(e)}")
            time.sleep(2)

    logger.error("Failed to navigate to next page after max retries. Stopping pagination.")
    return False

def wait_for_search_results(driver, timeout=30):
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script(
            "return !!d.querySelector('a[href*=\"/jobs/view/\"]') || "
            "!!d.querySelector('ul.jobs-search__results-list li') || "
            "!!d.querySelector('div.jobs-search-results__list-item') || "
            "!!d.querySelector('div.job-card-container') || "
            "!!d.querySelector('div.job-card-list__item') || "
            "!!d.querySelector('.base-card')"
        ))
        return True
    except Exception:
        return False

def build_search_url(keyword, search_location, search_time_range):
    quoted = urllib.parse.quote_plus(keyword)
    if search_location.lower() == "remote":
        return (
            f"https://www.linkedin.com/jobs/search/?keywords={quoted}"
            f"&f_WT=2&f_TPR={search_time_range}"
            f"&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
        )
    elif not search_location:
        return (
            f"https://www.linkedin.com/jobs/search/?keywords={quoted}"
            f"&f_TPR={search_time_range}"
            f"&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
        )
    else:
        quoted_loc = urllib.parse.quote_plus(search_location)
        return (
            f"https://www.linkedin.com/jobs/search/?keywords={quoted}"
            f"&location={quoted_loc}&f_TPR={search_time_range}"
            f"&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
        )

def wait_until_logged_in(driver, timeout_seconds=300):
    logger.info("\nLogin required.")
    logger.info("In the opened Chrome window, sign in to LinkedIn using email/password.")
    logger.info("Avoid 'Continue with Google' here; Google often blocks sign-in in automated browsers.")

    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            logged_in = driver.execute_script(
                "return !!document.querySelector("
                "  'input[placeholder*=\"Search\"],"
                "   input[role=\"combobox\"],"
                "   .search-global-typeahead__input'"
                ");"
            )
            if logged_in:
                logger.info("Login detected.")
                return True
        except Exception:
            pass
        time.sleep(2)
    return False

def run_job_finder(target_url=None):
    """Executes the LinkedIn Job Finder scraper workflow."""
    init_job_leads_store()
    driver = get_driver()

    try:
        driver.get("https://www.linkedin.com/login")

        if not wait_until_logged_in(driver, timeout_seconds=5):
            global_conf = get_global_settings()
            email = global_conf.get("linkedin_email")
            password = global_conf.get("linkedin_password")
            if email and password:
                logger.info("Attempting auto-login...")
                try:
                    driver.find_element(By.ID, "username").send_keys(email)
                    driver.find_element(By.ID, "password").send_keys(password)
                    driver.find_element(By.XPATH, "//button[@type='submit']").click()
                    if wait_until_logged_in(driver, timeout_seconds=20):
                        logger.info("Auto-login successful!")
                    else:
                        logger.warning("Auto-login failed or security verification required. Waiting up to 300 seconds for manual login...")
                        if not wait_until_logged_in(driver, timeout_seconds=300):
                            logger.error("Login timeout. Exiting.")
                            driver.quit()
                            return
                except Exception as e:
                    logger.warning(f"Auto-login failed: {e}. Waiting up to 300 seconds for manual login...")
                    if not wait_until_logged_in(driver, timeout_seconds=300):
                        logger.error("Login timeout. Exiting.")
                        driver.quit()
                        return
            else:
                logger.warning("LinkedIn credentials missing in config. Waiting up to 300 seconds for manual login...")
                if not wait_until_logged_in(driver, timeout_seconds=300):
                    logger.error("Login timeout. Exiting.")
                    driver.quit()
                    return

        inject_runtime_overlay(driver)
        main_handle = driver.current_window_handle

        # Load existing tracker urls
        jobs = load_saved_jobs()
        existing_urls = {normalize_external_url(j.get("CompanyURL") or "") for j in jobs if j.get("CompanyURL")}
        seen_external_urls.update(existing_urls)
        logger.info(f"Loaded {len(existing_urls)} existing jobs from Excel tracker.\n")

        # Load dynamic configurations
        user_conf = get_selected_user_config()
        global_conf = get_global_settings()
        
        search_keywords = user_conf.get("linkedin_connect", {}).get("search_keywords") or user_conf.get("linkedin_connect", {}).get("keywords") or LINKEDIN_CONNECT_KEYWORDS_DEFAULT
        title_keywords = user_conf.get("linkedin_connect", {}).get("title_keywords") or user_conf.get("linkedin_connect", {}).get("keywords") or LINKEDIN_CONNECT_KEYWORDS_DEFAULT
        search_time_range = global_conf.get("search_time_range", "r604800")
        
        # Retrieve preferred locations from profile
        profile = user_conf.get("profile", {})
        pref_location_str = profile.get("preferred_locations", "")
        locations = parse_preferred_locations(pref_location_str)
        
        # Fallback to current location if preferred locations are empty
        if not locations:
            current_loc = profile.get("current_location", "").strip()
            if current_loc:
                locations = parse_preferred_locations(current_loc)
                
        # If still empty, fall back to global search location (only if not India fallback)
        if not locations:
            global_loc = global_conf.get("search_location", "").strip()
            if global_loc and "india" not in global_loc.lower():
                locations = parse_preferred_locations(global_loc)
                
        # If absolutely no locations are configured, search nationwide (represented by "")
        if not locations:
            locations = [""]
        
        search_combinations = []
        for loc in locations:
            for kw in search_keywords:
                url = build_search_url(kw, loc, search_time_range)
                search_combinations.append((kw, loc, url))
        
        connect_conf = user_conf.get("linkedin_connect", {})
        try:
            max_pages = int(connect_conf.get("search_pages") or 2)
        except (ValueError, TypeError):
            max_pages = 2

        logger.info(f"Page search limit per keyword: {max_pages} pages")
        total_saved = 0
        session_lost = False
        processed_signatures = load_processed_signatures_from_excel()
        processed_job_ids = set()

        for comb_i, (keyword, loc, search_url) in enumerate(search_combinations, start=1):
            if session_lost:
                break

            logger.info(f"\n[COMBINATION {comb_i}/{len(search_combinations)}] Keyword: '{keyword}' in '{loc}'")
            try:
                driver.get(search_url)
                logger.info(f"Loading search results for keyword '{keyword}' in '{loc}'...")
                wait_for_page(8)
                wait_for_search_results(driver, timeout=20)
                wait_for_page(2)

                page_no = 1

                while page_no <= max_pages:
                    logger.info(f"\n[PAGE {page_no}/{max_pages}] Keyword: '{keyword}'")

                    job_cards = get_job_cards(driver)
                    if not job_cards:
                        logger.info("No jobs found on current page.")
                        break

                    logger.info(f"Found {len(job_cards)} jobs on page {page_no}")

                    for index in range(len(job_cards)):
                        sig = ""
                        job_id = ""
                        position = ""
                        company = ""
                        card_url = ""
                        try:
                            # 1. Refresh elements to avoid StaleElementReferenceException
                            left_pane = get_left_pane_container(driver)
                            card_selectors = (
                                'li.jobs-search-results__list-item, '
                                '.job-card-container, '
                                'div.job-card-list__item, '
                                'div[role="button"][componentkey*="job-card-component-ref"], '
                                'div.jobs-search-results__list-item, '
                                '.base-card'
                            )
                            if left_pane:
                                job_cards = left_pane.find_elements(By.CSS_SELECTOR, card_selectors)
                            else:
                                job_cards = driver.find_elements(By.CSS_SELECTOR, card_selectors)
                            valid_cards = []
                            seen_job_ids = set()
                            for c in job_cards:
                                try:
                                    links = c.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
                                    if links:
                                        href = links[0].get_attribute("href")
                                        jid = extract_job_id(href)
                                        if jid:
                                            if jid not in seen_job_ids:
                                                seen_job_ids.add(jid)
                                                valid_cards.append(c)
                                except Exception:
                                    pass

                            if index >= len(valid_cards):
                                break

                            card = valid_cards[index]
                            # Scroll using left pane scoped helper to bring card into view
                            scroll_element_into_view_in_left_pane(driver, card)
                            time.sleep(2)

                            # Extract Card URL and Job ID first (from card element)
                            try:
                                card_a = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
                                card_url = card_a.get_attribute("href")
                                job_id = extract_job_id(card_url)
                            except Exception:
                                pass

                            # 2. Click the job title link to open the job details panel
                            job_link = None
                            for selector in ["a.job-card-list__title", "a.job-card-container__link", "a[href*='/jobs/view/']"]:
                                try:
                                    el = card.find_element(By.CSS_SELECTOR, selector)
                                    if el.is_displayed():
                                        job_link = el
                                        break
                                except Exception:
                                    continue
                            if not job_link:
                                job_link = card

                            logger.info(f"\n  --- Opening Job {index + 1}/{len(valid_cards)} (Page {page_no}) ---")
                            driver.execute_script("arguments[0].click();", job_link)

                            # 3. Wait until right details panel loads
                            try:
                                WebDriverWait(driver, 15).until(
                                    EC.presence_of_element_located((
                                        By.CSS_SELECTOR,
                                        """
                                        .jobs-search__job-details--wrapper,
                                        .jobs-search__job-details,
                                        .jobs-details,
                                        #job-details,
                                        .scaffold-layout__detail
                                        """
                                    ))
                                )
                            except Exception:
                                logger.info("  Timed out waiting for right-side job details panel to load.")

                            time.sleep(2)

                            # Find right details pane
                            right_pane = None
                            for css in [
                                '.jobs-search__job-details--wrapper',
                                '.jobs-search__job-details',
                                '.jobs-details',
                                '#job-details',
                                '.scaffold-layout__detail'
                            ]:
                                try:
                                    el = driver.find_element(By.CSS_SELECTOR, css)
                                    if el.is_displayed():
                                        right_pane = el
                                        break
                                except Exception:
                                    continue

                            # Extract metadata (Title, Company Name) trying details pane first
                            if right_pane:
                                try:
                                    title_el = right_pane.find_element(
                                        By.CSS_SELECTOR, 
                                        "h1, h2, .job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title"
                                    )
                                    position = title_el.text.strip()
                                except Exception:
                                    pass

                                try:
                                    company_el = right_pane.find_element(
                                        By.CSS_SELECTOR, 
                                        "a[href*='/company/'], .job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name"
                                    )
                                    company = company_el.text.strip()
                                except Exception:
                                    pass

                            # Fallback to card if details pane extraction was empty/failed
                            if not position:
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

                            if not company:
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

                            if not job_id:
                                try:
                                    job_id = extract_job_id(driver.current_url)
                                except Exception:
                                    pass

                            sig = f"{company.lower().strip()}|{position.lower().strip()}"

                            logger.info(f"  Title  : {position}")
                            logger.info(f"  Company: {company}")
                            if job_id:
                                logger.info(f"  Job ID : {job_id}")

                            # 4. Check whether the job contains a valid Apply button
                            target_container = right_pane if right_pane else driver
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
                                logger.info("  Apply section load timeout.")

                            time.sleep(2)

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

                            # Register processed identifiers
                            processed_signatures.add(sig)
                            if job_id:
                                processed_job_ids.add(job_id)

                            if is_easy_apply:
                                logger.info("  [SKIP] Easy Apply job. Skipping completely.")
                                continue

                            if not external_apply_btn:
                                logger.info("  [SKIP] No regular Apply button found.")
                                continue

                            # Click external Apply button first to get external URL and verify link works
                            original_tab = driver.current_window_handle
                            pre_click_handles = driver.window_handles

                            logger.info("  Clicking the external Apply button for confirmation and URL retrieval...")
                            try:
                                external_apply_btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", external_apply_btn)

                            # Wait for new tab
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
                                logger.info("  No new tab opened immediately. Checking for LinkedIn safety/redirection confirmation modal...")
                                modal_confirm_btn = None
                                
                                # Common selectors for the proceed/confirm elements in LinkedIn's safety warning dialogs
                                for selector in [
                                    "a[href*='linkedin.com/safety/go']",
                                    ".artdeco-modal__confirm-dialog-btn",
                                    ".artdeco-modal button.artdeco-button--primary",
                                    "div[role='dialog'] button.artdeco-button--primary",
                                    "div[role='dialog'] a[href*='safety/go']"
                                ]:
                                    try:
                                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                        for el in elements:
                                            if el.is_displayed():
                                                modal_confirm_btn = el
                                                break
                                    except Exception:
                                        pass
                                    if modal_confirm_btn:
                                        break
                                        
                                if modal_confirm_btn:
                                    logger.info("  Detected redirection confirmation dialog. Clicking proceed button...")
                                    try:
                                        modal_confirm_btn.click()
                                    except Exception:
                                        driver.execute_script("arguments[0].click();", modal_confirm_btn)
                                        
                                    # Wait again for the new tab to open
                                    for _ in range(15):
                                        time.sleep(0.5)
                                        current_handles = driver.window_handles
                                        for h in current_handles:
                                            if h not in pre_click_handles:
                                                new_handle = h
                                                break
                                        if new_handle:
                                            break

                            if not new_handle:
                                logger.warning("  [WARNING] Clicked Apply but no new tab opened.")
                                continue

                            driver.switch_to.window(new_handle)
                            
                            # Wait for the external URL to resolve/settle to a non-empty, non-blank destination
                            settled_url = ""
                            start_wait = time.time()
                            while time.time() - start_wait < 8:  # max 8 seconds timeout
                                try:
                                    curr_url = driver.current_url
                                    if curr_url and curr_url != "about:blank" and "linkedin.com/safety/go" not in curr_url:
                                        settled_url = curr_url
                                        # If it's a known applicant tracking system/job portal, we can stop waiting early
                                        if any(domain in curr_url for domain in ["greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com"]):
                                            break
                                except Exception:
                                    pass
                                time.sleep(0.5)
                            
                            if not settled_url:
                                try:
                                    settled_url = driver.current_url
                                except Exception:
                                    pass
                            
                            external_url = settled_url
                            logger.info(f"  Settled External URL: {external_url}")

                            # Perform filters and validations after clicking and confirming the Apply link
                            is_valid = True

                            if is_job_already_processed_excel(company, position):
                                logger.info("  [SKIP] Job already processed (Excel signature check).")
                                is_valid = False

                            if is_valid and not is_title_matching_keywords(position, title_keywords):
                                logger.info(f"  [SKIP] Title '{position}' does not match configured keyword list.")
                                is_valid = False

                            if is_valid:
                                excluded_kws = [str(kw).lower().strip() for kw in user_conf.get("linkedin_connect", {}).get("excluded_keywords", []) if str(kw).strip()]
                                excluded_hit = next((kw for kw in excluded_kws if kw in position.lower()), None)
                                if excluded_hit:
                                    logger.info(f"  [SKIP] Title '{position}' excluded by exclusion keyword '{excluded_hit}'.")
                                    is_valid = False

                            if is_valid and is_already_saved(external_url):
                                logger.info("  [SKIP] Job already saved in Excel tracker.")
                                is_valid = False

                            # Save to Excel if all validation checks pass
                            if is_valid:
                                try:
                                    if save_job({
                                        "CompanyURL": external_url,
                                        "CompanyName": company,
                                        "JobTitle": position,
                                        "SearchKeyword": keyword
                                    }):
                                        total_saved += 1
                                        logger.info("  [SUCCESS] Job stored in Excel tracker.")
                                except Exception as e:
                                    logger.error(f"  [ERROR] Excel save error: {e}")

                            # Close new tab and return to main LinkedIn search tab
                            driver.close()
                            driver.switch_to.window(original_tab)
                            time.sleep(2)

                        except (InvalidSessionIdException, WebDriverException) as e:
                            logger.error(f"  Critical session error processing job {index + 1}: {str(e)}")
                            session_lost = True
                            raise e
                        except Exception as e:
                            logger.error(f"  Error processing job {index + 1}: {str(e)}")
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
                            try:
                                processed_signatures.add(sig)
                                if job_id:
                                    processed_job_ids.add(job_id)
                            except Exception:
                                pass
                            continue

                    moved = go_to_next_jobs_page(driver)
                    if not moved:
                        logger.info("No more pages available.")
                        break
                    page_no += 1

            except (InvalidSessionIdException, WebDriverException) as e:
                logger.error(f"Session lost: {e}")
                session_lost = True
                break

        logger.info(f"\n[COMPLETE] Total jobs saved: {total_saved}")

    finally:
        try:
            remove_runtime_overlay(driver)
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass
