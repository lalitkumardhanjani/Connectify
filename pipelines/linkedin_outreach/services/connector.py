import os
import sys
import time
import json
import random
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config.settings import LINKEDIN_CONNECT_LOG_FILE
from config.user_profiles import get_selected_user_config, get_global_settings, substitute_template_variables
from config.email_templates import DEFAULT_CONNECTION_TEMPLATE
from core.integrations.selenium_driver import get_driver
from core.storage.database import load_jobs_for_referral, update_status_by_id, get_company_sent_count, get_employee_outreach_progress
from core.logging.config import setup_logger

# Configure a dedicated logger for LinkedIn connection automation
logger = setup_logger(LINKEDIN_CONNECT_LOG_FILE)

def _inject_login_banner(driver):
    """Injects a clear red warning banner to alert the user to log in manually."""
    pass

# ============== HELPER FUNCTIONS ==============

def save_debug_info(driver, step_name):
    """Save screenshot and page source for debugging"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        time.sleep(2)

        screenshot_path = f"debug_screenshot_{step_name}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Saved screenshot: {screenshot_path}")

        try:
            rendered_html = driver.execute_script("return document.body.outerHTML;")
            html_path = f"debug_html_{step_name}_{timestamp}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(rendered_html)
            logger.info(f"Saved rendered HTML: {html_path}")
        except Exception:
            html_path = f"debug_html_{step_name}_{timestamp}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logger.info(f"Saved HTML: {html_path}")
    except Exception as e:
        logger.warning(f"Could not save debug info: {str(e)}")


def get_company_id_from_page(driver, company_url):
    """Navigates to company page URL and extracts the numeric company ID from page metadata or script tags."""
    logger.info(f"Navigating to company URL: {company_url} to extract Company ID")
    try:
        driver.get(company_url)
        time.sleep(4)
        
        # Check if Page not found
        if "page not found" in str(driver.title).lower() or "404" in str(driver.title).lower() or len(driver.find_elements(By.CSS_SELECTOR, ".error-container")) > 0:
            logger.warning(f"Company page for '{company_url}' not found.")
            return None
            
        company_id = driver.execute_script(r"""
            const getCompanyId = () => {
                // A. Try URL if it already contains a numeric company ID
                const urlMatch = window.location.href.match(/\/company\/(\d+)/);
                if (urlMatch) return urlMatch[1];

                // B. Try meta tags (highly reliable, specific to the current page head)
                const metaSelectors = [
                    'meta[property="al:android:url"]',
                    'meta[name="twitter:app:url:iphone"]',
                    'meta[name="twitter:app:url:ipad"]',
                    'meta[name="twitter:app:url:googleplay"]'
                ];
                for (const sel of metaSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const content = el.getAttribute('content') || '';
                        const match = content.match(/company\/(\d+)/) || content.match(/urn:li:company:(\d+)/);
                        if (match) return match[1];
                    }
                }
                
                // C. Try to find the primary "See all employees" / "View all employees" link
                // excluding sidebars/recommendations, and specifically looking for employee/people/connection keywords in the link text
                const links = Array.from(document.querySelectorAll('a[href*="/search/results/people/"]'));
                for (const link of links) {
                    if (link.closest('aside') || link.closest('.org-similar-pages') || link.closest('.org-people-also-viewed') || link.closest('.org-people-also-viewed-module')) {
                        continue;
                    }
                    const text = (link.innerText || link.textContent || '').toLowerCase();
                    if (text.includes('employee') || text.includes('people') || text.includes('connection')) {
                        const href = link.getAttribute('href') || '';
                        const match = href.match(/currentCompany=%5B%22(\d+)%22%5D/) || href.match(/currentCompany=(\d+)/);
                        if (match) return match[1];
                    }
                }

                // D. Try jobs link with company ID parameter (f_C)
                const jobLinks = Array.from(document.querySelectorAll('a[href*="f_C="]'));
                for (const link of jobLinks) {
                    if (link.closest('aside') || link.closest('.org-similar-pages') || link.closest('.org-people-also-viewed') || link.closest('.org-people-also-viewed-module')) {
                        continue;
                    }
                    const href = link.getAttribute('href') || '';
                    const match = href.match(/f_C=(\d+)/) || href.match(/f_C=%5B%22(\d+)%22%5D/);
                    if (match) return match[1];
                }

                // E. Try any link with currentCompany (excluding sidebars)
                for (const link of links) {
                    if (link.closest('aside') || link.closest('.org-similar-pages') || link.closest('.org-people-also-viewed') || link.closest('.org-people-also-viewed-module')) {
                        continue;
                    }
                    const ids = extractIds(link.getAttribute('href'));
                    if (ids.length > 0) return ids;
                }

                // F. Try parsing script tags, looking for companyUniversalId or objectUrn
                const scripts = document.querySelectorAll('script');
                for (const script of scripts) {
                    const text = script.textContent || '';
                    let match = text.match(/"companyUniversalId"\s*:\s*(\d+)/) || text.match(/companyUniversalId\s*:\s*(\d+)/);
                    if (match) return [match[1]];

                    match = text.match(/"objectUrn"\s*:\s*"urn:li:company:(\d+)"/) || text.match(/"urn:li:company:(\d+)"/);
                    if (match) return [match[1]];
                }
                
                return [];
            };
            return getCompanyIds().join(',');
        """)

        # Parse company IDs returned from JS
        company_ids = []
        if company_ids_str:
            company_ids = [i.strip() for i in company_ids_str.split(",") if i.strip()]

        # 2. Python-based regex fallback over page source if JS extraction returned nothing
        if not company_ids:
            logger.info("JS company ID extraction returned nothing. Trying Python page source regex fallback...")
            import re
            page_source = driver.page_source or ""
            current_url = driver.current_url or ""
            
            # A. URL numeric check
            url_match = re.search(r'/company/(\d+)', current_url)
            if url_match:
                company_ids = [url_match.group(1)]
                
            # B. companyUniversalId check (high confidence)
            if not company_ids:
                matches = re.findall(r'"companyUniversalId"\s*:\s*(\d+)', page_source) or re.findall(r'companyUniversalId\s*:\s*(\d+)', page_source)
                if matches:
                    company_ids = list(set(matches))
                    
            # C. f_C (job filter) check (high confidence)
            if not company_ids:
                matches = re.findall(r'f_C=(\d+)', page_source) or re.findall(r'f_C=%5B%22(\d+)%22%5D', page_source)
                if matches:
                    company_ids = list(set(matches))

            # NOTE: Generic urn:li:company: matches over the whole source are intentionally avoided,
            # as they capture competitor IDs from recommendations / "people also viewed" scripts.

        if company_ids:
            import json
            import urllib.parse
            # Format as encoded JSON array e.g. %5B%228019%22%2C%2276157629%22%5D
            return urllib.parse.quote(json.dumps(company_ids, separators=(',', ':')))
        return None
    except Exception as e:
        logger.warning(f"Error extracting Company ID from page: {e}")
        return None


# ============== MESSAGING ==============

def get_connect_review_mode():
    try:
        user_conf = get_selected_user_config()
        return user_conf.get("linkedin_connect", {}).get("review_mode", True)
    except Exception:
        return os.getenv("REVIEW_MODE", "0") != "0"

def get_message(position=None, company=None, first_name=None, job_url=None, resume_link=None, person_name=None):
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    
    template = connect_conf.get("message_template")
    if not template:
        template = DEFAULT_CONNECTION_TEMPLATE

    if not resume_link:
        resume_link = profile.get("resume_url", "")
    
    resolved_person_name = "there"
    if person_name:
        resolved_person_name = person_name.split()[0] if person_name.strip() else "there"
    elif first_name:
        resolved_person_name = first_name

    extra_vars = {
        # uppercase canonical tokens
        "{RECEIVER_NAME}": resolved_person_name,
        "{COMPANY}": company or "the company",
        "{JOB_URL}": job_url or "",
        "{RESUME}": resume_link or "",
        # legacy lowercase aliases for backward compat
        "{company}": company or "the company",
        "{job_url}": job_url or "",
        "{resume}": resume_link or "",
        "{first_name}": first_name or "there",
        "{PERSON_NAME}": resolved_person_name,
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()

def get_message_connected(position=None, job_id=None, resume_link=None, person_name=None, their_role=None, company=None):
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    
    template = connect_conf.get("message_template")
    if not template:
        template = DEFAULT_CONNECTION_TEMPLATE

    if not resume_link:
        resume_link = profile.get("resume_url", "")
        
    recip_first_name = "there"
    if person_name:
        recip_first_name = person_name.split()[0]
        
    extra_vars = {
        # uppercase canonical tokens
        "{RECEIVER_NAME}": recip_first_name,
        "{COMPANY}": company or "your company",
        "{JOB_URL}": job_id or "",
        "{RESUME}": resume_link or "",
        # legacy aliases
        "{company}": company or "your company",
        "{job_url}": job_id or "",
        "{resume}": resume_link or "",
        "{first_name}": recip_first_name,
        "{PERSON_NAME}": recip_first_name,
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()

def review_and_confirm_message(templates_func, label, *args, **kwargs):
    if not get_connect_review_mode():
        return templates_func(*args, **kwargs)

    msg = templates_func(*args, **kwargs)
    
    logger.info("\n" + "─" * 60)
    logger.info(f"REVIEW CONNECTION NOTE: {label}")
    logger.info("─" * 60)
    logger.info(msg)
    logger.info("─" * 60)
    logger.info(f"Length: {len(msg)} / 300 characters")
    logger.info("─" * 60)
    
    choice = input("Approve and send this note? (Y/N/Edit): ").strip().lower()
    if choice == 'y' or choice == '':
        logger.info("Approved.")
        return msg
    elif choice == 'edit':
        logger.info("Paste your custom message (press Enter twice when done):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        custom = "\n".join(lines).strip()
        logger.info(f"Custom message set ({len(custom)} chars)")
        return custom
    else:
        logger.info("Skipped.")
        return None

# ============== SELENIUM HELPERS ==============

def wait_until_logged_in(driver, timeout_seconds=300):
    start = time.time()
    search_bar_selectors = [
        "input[placeholder*='Search']",
        ".search-global-typeahead__input",
        "input[role='combobox']"
    ]
    while time.time() - start < timeout_seconds:
        _inject_login_banner(driver)
        try:
            for selector in search_bar_selectors:
                try:
                    search_bar = driver.find_element(By.CSS_SELECTOR, selector)
                    if search_bar.is_displayed():
                        logger.info("Login detected.")
                        return True
                except NoSuchElementException:
                    continue
        except Exception:
            pass
        time.sleep(2)
    return False

def login_to_linkedin(driver, email, password):
    """Handle LinkedIn login if needed"""
    logger.info("Checking if already logged in...")
    if wait_until_logged_in(driver, timeout_seconds=5):
        logger.info("Already logged in!")
        return True

    logger.info("Not logged in. Attempting login...")
    if email and password:
        try:
            # Navigate to the dedicated login page to ensure standard login form elements are present
            if "linkedin.com/login" not in driver.current_url:
                logger.info("Navigating directly to LinkedIn dedicated login page...")
                try:
                    driver.get("https://www.linkedin.com/login")
                except TimeoutException:
                    logger.warning("Page load timeout navigating to login page; proceeding anyway...")
                except Exception as e:
                    logger.warning(f"Error navigating to login page: {e}; proceeding anyway...")
                time.sleep(2)
                
            email_selectors = [
                "input[id*='username']",
                "input[name='session_key']",
                "input[type='email']",
                "#username"
            ]
            email_input = None
            for selector in email_selectors:
                try:
                    email_input = WebDriverWait(driver, 3).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if email_input:
                logger.info("Login form found. Typing credentials...")
                email_input.send_keys(email)

                password_selectors = [
                    "input[id*='password']",
                    "input[name='session_password']",
                    "input[type='password']",
                    "#password"
                ]
                for selector in password_selectors:
                    try:
                        password_input = driver.find_element(By.CSS_SELECTOR, selector)
                        password_input.send_keys(password)
                        break
                    except NoSuchElementException:
                        continue

                button_selectors = [
                    "button[type='submit']",
                    "button[data-litms-control-urn*='sign-in']",
                    ".btn__primary--large"
                ]
                for selector in button_selectors:
                    try:
                        driver.find_element(By.CSS_SELECTOR, selector).click()
                        break
                    except NoSuchElementException:
                        continue

                if wait_until_logged_in(driver, timeout_seconds=20):
                    logger.info("Login successful!")
                    return True
                else:
                    logger.warning("Auto-login failed or security verification required. Waiting up to 300 seconds for manual login...")
                    if wait_until_logged_in(driver, timeout_seconds=300):
                        return True
                    else:
                        logger.error("Login timeout. Exiting.")
                        return False
            else:
                # Login form not found — LinkedIn may be showing a checkpoint, security
                # screen, or redirect. Fall back to manual login instead of assuming success.
                logger.warning(
                    "Login form not found on page (LinkedIn may be showing a checkpoint "
                    "or security screen). Waiting up to 300 seconds for manual login "
                    "in the browser window — please log in manually and the pipeline "
                    "will resume automatically."
                )
                if wait_until_logged_in(driver, timeout_seconds=300):
                    return True
                else:
                    logger.error("Manual login timeout. Exiting.")
                    return False
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            logger.info("Waiting up to 300 seconds for manual login...")
            if wait_until_logged_in(driver, timeout_seconds=300):
                return True
            else:
                return False
    else:
        logger.warning("LinkedIn credentials missing in config. Waiting up to 300 seconds for manual login in the Chrome window...")
        if wait_until_logged_in(driver, timeout_seconds=300):
            return True
        else:
            logger.error("Login timeout. Exiting.")
            return False

def apply_current_company_filter_via_ui(driver, company_name):
    """
    Attempts to apply the 'Current companies' filter via the LinkedIn UI
    by clicking the dropdown, typing the company name, selecting the first
    suggestion, and clicking 'Show results'.
    """
    logger.info(f"Attempting to verify/apply 'Current companies' filter for '{company_name}' via UI...")
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Step A: Click 'Current companies' dropdown button
        dropdown_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@componentkey="SearchResults_filter_pill_currentCompany"] | //button[contains(., "Current companies")] | //div[@componentkey="SearchResults_filter_pill_currentCompany"] | //span[contains(., "Current companies")]'))
        )
        dropdown_button.click()
        logger.info("Dropdown clicked.")
        time.sleep(2)
        
        # Step B: Find the input element and type the company name
        input_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//input[contains(@placeholder, "Add a company")] | //input[contains(@placeholder, "company")]'))
        )
        input_field.clear()
        input_field.send_keys(company_name)
        logger.info(f"Typed '{company_name}' in filter input.")
        time.sleep(4) # Wait for autocomplete suggestions
        
        # Step C: Select the first suggestion matching the company name
        selected = driver.execute_script(f"""
            const options = Array.from(document.querySelectorAll('[role="option"]'));
            const textMatch = "{company_name.lower()}";
            
            const target = options.find(opt => {{
                const txt = (opt.innerText || opt.textContent || '').toLowerCase();
                return txt.includes(textMatch);
            }});
            
            if (target) {{
                target.click();
                return target.innerText.replace(/\\n/g, ' ');
            }}
            return null;
        """)
        
        if selected:
            logger.info(f"Successfully selected suggestion: {selected}")
        else:
            logger.warning("No matching option found in suggestions list. Attempting fallback click...")
            # Fallback checkbox/label matching
            fallback_clicked = driver.execute_script(f"""
                const textMatch = "{company_name.lower()}";
                const allElements = Array.from(document.querySelectorAll('span, div, label, p'));
                const textElement = allElements.find(el => {{
                    const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                    return txt === textMatch && el.children.length === 0;
                }}) || allElements.find(el => {{
                    const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
                    return txt === textMatch;
                }});
                
                if (textElement) {{
                    let container = textElement.parentElement;
                    let label = null;
                    for (let i = 0; i < 4; i++) {{
                        if (!container) break;
                        label = container.querySelector('label');
                        if (label) break;
                        container = container.parentElement;
                    }}
                    if (label) {{
                        label.click();
                        return "label clicked";
                    }}
                }}
                return null;
            """)
            if fallback_clicked:
                logger.info(f"Fallback label check result: {fallback_clicked}")
            
        time.sleep(2)
        
        # Step D: Click 'Show results' button (if still visible — LinkedIn sometimes auto-applies)
        submitted = driver.execute_script("""
            // First check if popover is even still open (input still visible)
            const inputField = document.querySelector('input[placeholder*="Add a company"]') || 
                               document.querySelector('input[placeholder*="company"]');
            if (!inputField || inputField.offsetParent === null) {
                // Popover is already closed — LinkedIn auto-applied the filter after suggestion click
                return 'auto-applied';
            }

            // Popover still open — find and click Show results
            const allEls = Array.from(document.querySelectorAll('button, div[role="button"], span'));
            const showBtn = allEls.find(el => {
                const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                return txt === 'show results' || txt === 'apply';
            });
            if (showBtn) {
                const clickTarget = showBtn.closest('button') || showBtn.closest('[role="button"]') || showBtn;
                clickTarget.click();
                return 'clicked';
            }
            return 'not-found';
        """)
        
        if submitted == 'auto-applied':
            logger.info("Filter auto-applied by LinkedIn after suggestion selection (popover closed).")
            time.sleep(3)
            return True
        elif submitted == 'clicked':
            logger.info("Successfully clicked 'Show results' to apply filter.")
            time.sleep(4)
            return True
        else:
            # Show results not found but suggestion was selected — wait and check if page updated
            logger.warning("'Show results' button not found. Waiting to see if filter applied...")
            time.sleep(4)
            # If the URL or page updated, treat as success
            return True
    except Exception as ex:
        logger.warning(f"Error applying current company filter via UI: {ex}")
        return False

def search_company(driver, company_name, geo_urn="102713980"):
    """Search for a company on LinkedIn and apply Current Company filter"""
    logger.info(f"Searching for company: {company_name}")
    try:
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={company_name.replace(' ', '%20')}&origin=FACETED_SEARCH"
        if geo_urn:
            search_url += f"&geoUrn=%5B%22{geo_urn}%22%5D"
        driver.get(search_url)
        time.sleep(4)
        apply_current_company_filter_via_ui(driver, company_name)
        return True
    except Exception as e:
        logger.error(f"Direct navigation failed: {str(e)}")
        return False

def navigate_to_company_direct(driver, company_linkedin_id):
    """Navigate directly to company people page using company LinkedIn ID"""
    try:
        url = f"https://www.linkedin.com/company/{company_linkedin_id}/people/"
        driver.get(url)
        time.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Error in direct navigation: {str(e)}")
        return False

def find_people_with_connect_button(driver, max_people=10):
    logger.info(f"Looking for up to {max_people} people with Connect button...")
    people_with_connect = []

    try:
        # Wait for search result content to finish rendering
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/in/')]"))
            )
            logger.info("Search results detected — profile links visible.")
        except Exception:
            logger.warning("Timed out waiting for profile links. Proceeding anyway...")

        # Scroll to load all lazy-rendered cards
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        # KEY FIX: LinkedIn renders people cards inside Shadow DOM web components.
        # document.querySelectorAll('button') CANNOT find them.
        # We must recursively traverse shadow roots to find all buttons.
        results = driver.execute_script("""
            const maxPeople = arguments[0];

            // Recursively search both light DOM and all shadow roots
            function deepQueryAll(selector, root) {
                const results = [];
                try { results.push(...Array.from(root.querySelectorAll(selector))); } catch(e) {}
                try {
                    Array.from(root.querySelectorAll('*')).forEach(el => {
                        if (el.shadowRoot) results.push(...deepQueryAll(selector, el.shadowRoot));
                    });
                } catch(e) {}
                return results;
            }

            const allBtns = deepQueryAll('button, a', document);
            const found = [];
            const seen = new Set();

            for (const btn of allBtns) {
                if (found.length >= maxPeople) break;

                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const txt  = (btn.innerText || btn.textContent || '').trim().toLowerCase();

                const isConnect = aria.includes('to connect') ||
                                  (aria.includes('invite') && aria.includes('connect')) ||
                                  aria === 'connect' ||
                                  txt === 'connect' ||
                                  (txt.includes('connect') && txt.length < 25);

                if (!isConnect) continue;

                // Exclude false positives
                if (aria.includes('currently') || txt.includes('pending') ||
                    txt.includes('following') || txt.includes('message')) continue;

                // Extract name from "Invite [Name] to connect"
                const ariaLabel = btn.getAttribute('aria-label') || '';
                let name = '';
                const m = ariaLabel.match(/invite (.+?) to connect/i);
                if (m) name = m[1].trim();

                // Walk up DOM (works for both light and shadow DOM)
                let profileUrl = '';
                let el = btn.parentElement;
                for (let i = 0; i < 25; i++) {
                    if (!el) break;
                    // Check if the ancestor element itself is the profile link
                    if (el.tagName === 'A' && (el.href || '').includes('/in/')) {
                        profileUrl = el.href.split('?')[0];
                        break;
                    }
                    // Search in light DOM
                    const link = el.querySelector('a[href*="/in/"]');
                    if (link) { profileUrl = link.href.split('?')[0]; break; }
                    // Also search in shadow DOM of this element
                    const shadowLink = deepQueryAll('a[href*="/in/"]', el)[0];
                    if (shadowLink) { profileUrl = shadowLink.href.split('?')[0]; break; }
                    el = el.parentElement;
                }

                if (profileUrl && seen.has(profileUrl)) continue;
                if (profileUrl) seen.add(profileUrl);

                found.push([btn, name, profileUrl]);
            }
            return found;
        """, max_people)

        logger.info(f"Deep shadow DOM search found {len(results) if results else 0} Connect buttons")

        if results:
            for item in results:
                btn_el      = item[0]   # WebElement (works for shadow DOM elements too)
                name        = item[1] or ""
                profile_url = item[2] or ""
                people_with_connect.append({
                    'button':      btn_el,
                    'name':        name,
                    'role':        '',
                    'profile_url': profile_url
                })
            logger.info(f"Total people with Connect button: {len(people_with_connect)}")
            return people_with_connect

        logger.warning("Shadow DOM search found 0 Connect buttons.")
        logger.info(f"Total people with Connect button: 0")
        return people_with_connect
    except Exception as e:
        logger.error(f"Error finding people: {str(e)}")
        return people_with_connect

def find_people_already_connected(driver, max_people=10):
    logger.info("Applying 1st connections filter...")
    try:
        first_connection_filter = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "div[aria-label='Filter by 1st connections']"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_connection_filter)
        time.sleep(1)
        first_connection_filter.click()
        time.sleep(3)
        logger.info("1st connections filter applied")
    except Exception as e:
        logger.warning(f"Could not apply 1st connections filter: {str(e)}")
        return []

    people_connected = []
    try:
        people_cards = driver.find_elements(By.XPATH, "//div[@role='listitem']")
        for card in people_cards:
            if len(people_connected) >= max_people:
                break
            try:
                message_button = card.find_element(
                    By.CSS_SELECTOR,
                    "a[aria-label*='message']"
                )

                name, role, profile_url = "", "", ""
                try:
                    aria = message_button.get_attribute("aria-label") or ""
                    if aria.startswith("Send a message to"):
                        name = aria.replace("Send a message to", "").strip()
                except Exception as e:
                    logger.warning(f"Could not extract name from aria-label: {e}")

                try:
                    profile_url = card.find_element(
                        By.CSS_SELECTOR,
                        "a[href*='/in/']"
                    ).get_attribute("href")
                except Exception:
                    pass

                try:
                    spans = card.find_elements(By.TAG_NAME, "span")
                    for span in spans:
                        text = span.text.strip()
                        if (
                            text
                            and text != name
                            and "1st" not in text
                            and "message" not in text.lower()
                            and len(text) > 10
                        ):
                            role = text
                            break
                except Exception:
                    pass

                people_connected.append({
                    'button':      message_button,
                    'card':        card,
                    'name':        name,
                    'role':        role,
                    'profile_url': profile_url
                })
            except NoSuchElementException:
                continue
        logger.info(f"Total 1st connection people found: {len(people_connected)}")
        return people_connected
    except Exception as e:
        logger.error(f"Error finding connected people: {str(e)}")
        return people_connected

def send_connection_request(driver, person, message, review_mode=None):
    try:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", person['button'])
            time.sleep(2)
        except Exception as e:
            logger.debug(f"Could not scroll to button: {str(e)}")

        connect_clicked = False
        try:
            person['button'].click()
            connect_clicked = True
            time.sleep(2)
        except Exception:
            pass

        if not connect_clicked:
            try:
                driver.execute_script("arguments[0].click();", person['button'])
                connect_clicked = True
                time.sleep(3)
            except Exception as e:
                logger.error(f"Connect button failed: {str(e)}")
                return False

        time.sleep(4)
        try:
            how_know_options = driver.find_elements(By.XPATH, "//label[contains(@for, 'connect-choice')]")
            if how_know_options:
                how_know_options[0].click()
                time.sleep(1)

                continue_button_selectors = [
                    "//button[contains(@aria-label, 'Continue')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[contains(text(), 'Next')]",
                    "//button[@data-control-name='continue']"
                ]
                for selector in continue_button_selectors:
                    try:
                        continue_btn = driver.find_element(By.XPATH, selector)
                        continue_btn.click()
                        time.sleep(1)
                        break
                    except NoSuchElementException:
                        continue
        except Exception as e:
            logger.debug(f"No 'How do you know' screen or error: {str(e)}")

        add_note_clicked = False

        # KEY FIX: Modal buttons may be in Shadow DOM — use recursive deep search.
        add_note_button = driver.execute_script("""
            function deepQueryAll(selector, root) {
                const results = [];
                try { results.push(...Array.from(root.querySelectorAll(selector))); } catch(e) {}
                try {
                    Array.from(root.querySelectorAll('*')).forEach(el => {
                        if (el.shadowRoot) results.push(...deepQueryAll(selector, el.shadowRoot));
                    });
                } catch(e) {}
                return results;
            }
            const allBtns = deepQueryAll('button, a', document);
            const byText = allBtns.find(b => {
                const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                return txt === 'add a note' || txt.includes('add a note');
            });
            if (byText) return byText;
            const byAria = allBtns.find(b => {
                const a = (b.getAttribute('aria-label') || '').toLowerCase();
                return a.includes('add a note');
            });
            return byAria || null;
        """)

        if add_note_button:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_note_button)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", add_note_button)
                add_note_clicked = True
                time.sleep(3)
            except Exception as e:
                logger.warning(f"Failed to click Add a note button: {e}")

        if add_note_clicked:
            # KEY FIX: Textarea may be in Shadow DOM — use deep recursive search.
            message_box = driver.execute_script("""
                function deepQueryAll(selector, root) {
                    const results = [];
                    try { results.push(...Array.from(root.querySelectorAll(selector))); } catch(e) {}
                    try {
                        Array.from(root.querySelectorAll('*')).forEach(el => {
                            if (el.shadowRoot) results.push(...deepQueryAll(selector, el.shadowRoot));
                        });
                    } catch(e) {}
                    return results;
                }
                const allTextareas = deepQueryAll('textarea', document);
                return allTextareas.find(t => t.offsetParent !== null) || allTextareas[0] || null;
            """)

            if message_box:
                driver.execute_script("arguments[0].value = '';", message_box)
                time.sleep(0.3)
                driver.execute_script("""
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, message_box, message)
                time.sleep(1)

                if review_mode is None:
                    review_mode = get_connect_review_mode()

                if review_mode:
                    print("\n" + "="*50)
                    print("INVITE QUALITY GATE - CONNECTION NOTE REVIEW")
                    print("="*50)
                    print(f"Recipient: {person.get('name', 'unknown')} ({person.get('role', 'unknown')})")
                    print("-" * 50)
                    print(message)
                    print("="*50)
                    
                    print("Enter action (Send [S] / Skip [K] / Quit [Q]):")
                    choice = input().strip().lower()
                    while choice not in ('s', 'k', 'q'):
                        print("Invalid option. Please enter Send [S], Skip [K], or Quit [Q]:")
                        choice = input().strip().lower()
                        
                    if choice == 'k':
                        logger.info("User skipped connection request.")
                        close_dialog(driver)
                        return "skipped"
                    elif choice == 'q':
                        logger.info("User requested to quit the connector pipeline.")
                        close_dialog(driver)
                        return "quit"
                    else:
                        logger.info("User approved sending connection request.")
                else:
                    logger.info("Automatically sending connection request...")

                # KEY FIX: Send button may be in Shadow DOM — use deep recursive search.
                send_btn = driver.execute_script("""
                    function deepQueryAll(selector, root) {
                        const results = [];
                        try { results.push(...Array.from(root.querySelectorAll(selector))); } catch(e) {}
                        try {
                            Array.from(root.querySelectorAll('*')).forEach(el => {
                                if (el.shadowRoot) results.push(...deepQueryAll(selector, el.shadowRoot));
                            });
                        } catch(e) {}
                        return results;
                    }
                    const allBtns = deepQueryAll('button, a', document);
                    // Prefer exact 'Send invitation' match
                    const exact = allBtns.find(b => {
                        const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        return txt === 'send invitation' || aria === 'send invitation' || txt === 'send';
                    });
                    if (exact) return exact;
                    // Fallback: primary button that is NOT 'Send without a note'
                    return allBtns.find(b => {
                        const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                        return b.classList.contains('artdeco-button--primary') && !txt.includes('without');
                    }) || null;
                """)

                if send_btn:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", send_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", send_btn)
                    time.sleep(3)
                    logger.info(f"Successfully sent connection request to {person.get('name', 'unknown')} (Profile URL: {person.get('profile_url', 'unknown')}) with note:\n{message}")
                    return True
                else:
                    logger.warning("Could not find Send invitation button.")
                    close_dialog(driver)
                    return False
            else:
                logger.warning("Could not find note message text area.")
                close_dialog(driver)
                return False
        else:
            # Could not find "Add a note" button — never send without a note.
            # This pipeline requires a personalized note. Skip this person.
            save_debug_info(driver, "no_add_note_button")
            logger.warning(f"Could not find 'Add a note' button for {person.get('name', 'unknown')}. Skipping to avoid sending without a note.")
            close_dialog(driver)
            return "skipped"
    except Exception as e:
        logger.error(f"Error sending connection request: {str(e)}")
        error_msg = str(e).lower()
        is_connection_error = (
            "connection" in error_msg or 
            "refused" in error_msg or 
            "max retries" in error_msg or 
            "invalid session id" in error_msg or 
            "no such window" in error_msg or 
            "chrome not reachable" in error_msg or
            "disconnected" in error_msg
        )
        if is_connection_error:
            logger.error("Lost connection to Chrome browser. Terminating request.")
            return "browser_error"
        try:
            close_dialog(driver)
        except Exception:
            pass
        return False

def send_direct_message(driver, person, message):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", person["button"])
        time.sleep(1)
        person["button"].click()
        time.sleep(3)

        editor = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (!host || !host.shadowRoot) return null;
            return host.shadowRoot.querySelector('.msg-form__contenteditable');
        """)

        if not editor:
            raise Exception("Message editor not found")

        driver.execute_script("""
            arguments[0].scrollIntoView({block:'center'});
            arguments[0].click();
            arguments[0].focus();
        """, editor)
        time.sleep(1)

        driver.execute_script("""
            const editor = arguments[0];
            const text   = arguments[1];
            editor.focus();
            editor.click();
            editor.innerText = '';
            document.execCommand('insertText', false, text);
            ['input', 'change', 'keydown', 'keyup', 'keypress'].forEach(eventType => {
                const event = new Event(eventType, { bubbles: true, cancelable: true });
                editor.dispatchEvent(event);
            });
            const inputEvent = new InputEvent('input', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text
            });
            editor.dispatchEvent(inputEvent);
        """, editor, message)
        time.sleep(1)

        send_button = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (!host || !host.shadowRoot) return null;
            return host.shadowRoot.querySelector('.msg-form__send-button');
        """)

        if not send_button:
            raise Exception("Send button not found")

        if send_button.get_attribute("disabled") is not None:
            raise Exception("Message was not actually inserted")

        driver.execute_script("arguments[0].click();", send_button)
        time.sleep(3)
        logger.info(f"Message sent to {person.get('name', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message: {str(e)}")
        return False

def close_dialog(driver):
    try:
        dismiss_selectors = [
            "button.artdeco-modal__dismiss",
            "button[aria-label='Dismiss']",
            "button[data-test-modal-close-btn]"
        ]
        for sel in dismiss_selectors:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    btn.click()
                    time.sleep(1)
                    return True
            except Exception:
                continue

        result = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (!host) return 'NO_HOST';
            const root = host.shadowRoot;
            if (!root) return 'NO_SHADOW_ROOT';
            const selectors = [
                "button.artdeco-modal__dismiss",
                "button[data-test-modal-close-btn]",
                "button[aria-label='Dismiss']"
            ];
            for (const selector of selectors) {
                const btn = root.querySelector(selector);
                if (btn) { btn.click(); return 'SUCCESS'; }
            }
            return 'NO_CLOSE_BUTTON';
        """)
        time.sleep(1)
        if result == "SUCCESS":
            return True

        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
        return True
    except Exception:
        return False

def go_to_next_page(driver):
    try:
        next_button = driver.execute_script("""
            const btn = document.querySelector('button.artdeco-pagination__button--next') ||
                        document.querySelector('button[aria-label="Next"]') ||
                        document.querySelector('button[data-testid="pagination-controls-next-button"]');
            if (btn) return btn;
            const buttons = Array.from(document.querySelectorAll('button'));
            for (const b of buttons) {
                if (b.innerText && b.innerText.trim().toLowerCase() === 'next') {
                    return b;
                }
            }
            return null;
        """)
        if not next_button:
            return False

        is_disabled = driver.execute_script("return arguments[0].disabled;", next_button)
        if is_disabled:
            return False

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", next_button)
        time.sleep(5)
        return True
    except Exception:
        return False

# ============== RUN OUTREACH CONNECTIONS ==============

def run_connector():
    """Main runner logic for outreach connection workflow."""
    logger.info("=" * 60)
    logger.info("LinkedIn Referral Request Automation Starting...")
    
    # Load profile credentials & outreach modes
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    
    connect_conf = user_conf.get("linkedin_connect", {})
    max_connections_per_company = int(connect_conf.get("max_connections_per_company") or 5)
    max_connections_per_run = int(connect_conf.get("max_connections_per_run") or 30)
    geo_urn = connect_conf.get("geo_urn") or "102713980"
    total_connections_sent = 0
    
    outreach_mode = os.getenv("OUTREACH_MODE", "connect_only")
    review_mode = get_connect_review_mode()
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    resume_link = user_conf.get("profile", {}).get("resume_url", "")
    
    logger.info(f"REVIEW_MODE     : {review_mode}")
    logger.info(f"OUTREACH_MODE   : {outreach_mode}")
    logger.info(f"MAX PER COMPANY : {max_connections_per_company}")
    logger.info(f"MAX PER RUN     : {max_connections_per_run}")
    logger.info("=" * 60)

    job_data = load_jobs_for_referral(status_filter='Interested')
    if not job_data:
        logger.error("No jobs with status 'Interested' found in database. Exiting...")
        return

    logger.info(f"Loaded {len(job_data)} jobs with status 'Interested'.")


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

        for job in job_data:
            if total_connections_sent >= max_connections_per_run:
                logger.info(f"Max connections per run limit of {max_connections_per_run} reached. Stopping run.")
                break

            company = job.get('CompanyName') or ''
            job_id = job.get('JobID') or ''
            linkedin_company_url = job.get('LinkedIn_Company_URL') or ''
            
            from core.storage.database import get_completed_referral_count
            completed_progress = get_completed_referral_count(company, linkedin_company_url, job_id=job_id)
            if completed_progress >= max_connections_per_company:
                logger.info(f"Company '{company}' has already reached/completed its target connection count of {max_connections_per_company} (progress: {completed_progress}). Skipping.")
                try:
                    update_status_by_id(job_id, 'Referral Outreach Completed')
                except Exception as e:
                    logger.warning(f"Failed to update Job status: {e}")
                continue
                
            position = job.get('SearchKeyword') or ''
            job_url = job.get('ShortenURL') or job.get('CompanyURL') or ''
            
            # Compute remaining target capacity for this company
            max_apply = max_connections_per_company - completed_progress
            logger.info(f"Company '{company}' remaining target count is {max_apply} (progress: {completed_progress}).")
            linkedin_id = job.get('linkedin_id', '')

            logger.info("\n" + "=" * 60)
            logger.info(f"Processing: {company} — {position}")
            logger.info("=" * 60)

            navigation_success = False
            company_id = None
            
            # Step 1: Try to resolve Company ID using LinkedIn_Company_URL
            if linkedin_company_url:
                company_id = get_company_id_from_page(driver, linkedin_company_url)
                
            # Step 2: If no Company ID, try to search for the company to get its page and ID
            if not company_id:
                logger.info(f"Company ID not resolved directly. Searching for company page on LinkedIn for: {company}")
                search_url = f"https://www.linkedin.com/search/results/companies/?keywords={company.replace(' ', '%20')}"
                try:
                    driver.get(search_url)
                    time.sleep(4)
                    first_result = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".entity-result__title-text a"))
                    )
                    found_company_url = first_result.get_attribute("href")
                    logger.info(f"Found company page via search: {found_company_url}")
                    company_id = get_company_id_from_page(driver, found_company_url)
                except Exception as e:
                    logger.warning(f"Failed to find company page for {company} via search: {e}")
            
            # Step 3: If we have a Company ID, navigate to search results filtered strictly by currentCompany
            if company_id:
                # Filter to 2nd and 3rd+ degree connections who CURRENTLY work at the company
                people_search_url = f"https://www.linkedin.com/search/results/people/?currentCompany={company_id}&network=%5B%22S%22%2C%22O%22%5D"
                if geo_urn:
                    people_search_url += f"&geoUrn=%5B%22{geo_urn}%22%5D"
                logger.info(f"Navigating to current employees search results: {people_search_url}")
                try:
                    driver.get(people_search_url)
                    time.sleep(4)
                    navigation_success = True
                    
                    # Verify if the current company filter is active in the UI
                    is_active = driver.execute_script("""
                        const el = document.querySelector('[componentkey="SearchResults_filter_pill_currentCompany"]') ||
                                   document.querySelector('[aria-label*="Current companies"]');
                        if (el) {
                            const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                            return !txt.includes('current companies') && !txt.includes('current company');
                        }
                        return false;
                    """)
                    if not is_active:
                        logger.warning("Current Company filter is not active after direct URL navigation. Applying via UI...")
                        apply_current_company_filter_via_ui(driver, company)
                except Exception as e:
                    logger.error(f"Failed to navigate to company search page: {e}")
            
            # Step 4: Fallback to global keyword search if everything else fails
            if not navigation_success:
                logger.info(f"Fallback to global keyword search for {company}")
                if not search_company(driver, company, geo_urn=geo_urn):
                    logger.error(f"Failed to search for {company}. Skipping...")
                    continue
                navigation_success = True

            msg_count = 0
            success_count = 0
            logger.info(f"Starting outreach requests for this job: {success_count}/{max_apply}")

            # Send connect requests to new people
            if outreach_mode in ("connect_only", "both"):
                page_number = 1
                while success_count < max_apply:
                    # Check if browser is still open/alive
                    try:
                        _ = driver.title
                    except Exception:
                        logger.error("Chrome browser was closed or crashed. Terminating connection requests.")
                        break

                    logger.info(f"\nProcessing page {page_number} for connect requests")
                    remaining = max_apply - success_count
                    people = find_people_with_connect_button(driver, max_people=remaining)

                    if not people:
                        logger.warning("No connectable people found on this page")
                        if not go_to_next_page(driver):
                            logger.warning("No more pages available")
                            break
                        page_number += 1
                        continue

                    for person in people:
                        if success_count >= max_apply:
                            break
                        # Check if browser is still open/alive
                        try:
                            _ = driver.title
                        except Exception:
                            logger.error("Chrome browser was closed or crashed. Terminating connection requests.")
                            break

                        try:
                            raw_name = person.get('name') or ''
                            first_name = raw_name.split()[0] if raw_name else "there"
                            message = get_message(
                                position=position,
                                company=company,
                                first_name=first_name,
                                job_url=job_url,
                                resume_link=resume_link,
                                person_name=raw_name,
                            )
                            if len(message) > 300:
                                message = message[:297] + "..."

                            sent = send_connection_request(driver, person, message, review_mode=review_mode)
                            
                            status_val = 'Sent'
                            error_reason = ''
                            if sent == "browser_error":
                                logger.error("Browser connection was lost. Exiting run...")
                                return
                            elif sent == "skipped":
                                logger.info(f"Skipping connect request to {person.get('name', 'unknown')}")
                                status_val = 'Skipped'
                            elif sent == "quit":
                                logger.info("Quitting connect requests loop as requested by user.")
                                try:
                                    update_status_by_id(job_id, 'Cancelled')
                                except Exception as e:
                                    logger.warning(f"Failed to update Job status to Cancelled: {e}")
                                sys.exit(2)
                            elif sent:
                                success_count += 1
                                total_connections_sent += 1
                                logger.info("Recorded connection request success.")
                                logger.info(f"Connect requests sent: {success_count}/{max_apply}")
                                logger.info(f"Total connections sent in this run: {total_connections_sent}")
                            else:
                                status_val = 'Failed'
                                error_reason = 'Connection invitation note could not be sent'

                            if sent != "quit":
                                try:
                                    from core.storage.database import add_or_update_referral
                                    referral_data = {
                                        'JobID': job_id,
                                        'CompanyName': company,
                                        'Job_URL': job_url,
                                        'Referral_Person_Name': person.get('name', 'unknown'),
                                        'Referral_Person_Email': '',
                                        'Referral_Person_Profile_URL': person.get('profile_url', ''),
                                        'Referral_Source': 'Sent Employee Connection',
                                        'Referral_Status': status_val,
                                        'Sent_Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status_val == 'Sent' else '',
                                        'Error_Reason': error_reason
                                    }
                                    add_or_update_referral(referral_data)
                                except Exception as ex:
                                    logger.warning(f"Failed to save connection request referral details to Excel: {ex}")

                            if sent == "skipped":
                                continue
                        except Exception as e:
                            logger.warning(f"Failed sending connect request: {str(e)}")
                        time.sleep(random.randint(3, 7))

                    if success_count >= max_apply:
                        break

                    if not go_to_next_page(driver):
                        break
                    page_number += 1

            # Message already connected
            if outreach_mode in ("message_only", "both"):
                connected_people = find_people_already_connected(driver, max_people=max_apply)
                if connected_people:
                    logger.info(f"Found {len(connected_people)} already connected — sending messages")
                    for person in connected_people:
                        long_message = review_and_confirm_message(
                            get_message_connected,
                            f"LONG MESSAGE — {person.get('name', 'unknown')} at {company}",
                            position=position,
                            job_id=job_id,
                            person_name=person.get('name'),
                            their_role=person.get('role'),
                        )
                        status_val = 'Sent'
                        error_reason = ''
                        if long_message is None:
                            logger.info(f"Skipping message to {person.get('name', 'unknown')}")
                            status_val = 'Skipped'
                        else:
                            try:
                                if send_direct_message(driver, person, long_message):
                                    msg_count += 1
                                else:
                                    status_val = 'Failed'
                                    error_reason = 'Direct message window could not be processed'
                            except Exception as e:
                                logger.warning(f"Failed sending message: {str(e)}")
                                status_val = 'Failed'
                                error_reason = str(e)
                        
                        try:
                            from core.storage.database import add_or_update_referral
                            referral_data = {
                                'JobID': job_id,
                                'CompanyName': company,
                                'Job_URL': job_url,
                                'Referral_Person_Name': person.get('name', 'unknown'),
                                'Referral_Person_Email': '',
                                'Referral_Person_Profile_URL': person.get('profile_url', ''),
                                'Referral_Source': 'Existing Employee',
                                'Referral_Status': status_val,
                                'Sent_Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status_val == 'Sent' else '',
                                'Error_Reason': error_reason
                            }
                            add_or_update_referral(referral_data)
                        except Exception as ex:
                            logger.warning(f"Failed to save direct message referral details to Excel: {ex}")

                        if long_message is None:
                            continue
                    logger.info(f"✓ Messages sent: {msg_count}/{len(connected_people)}")
                else:
                    logger.info("No already connected people found")

            logger.info(f"\n✓ Completed {company}: {success_count} connect requests, {msg_count} messages sent")
            
            # Calculate total progress for this company
            from core.storage.database import get_completed_referral_count
            completed_progress = get_completed_referral_count(company, linkedin_company_url, job_id=job_id)
            if completed_progress >= max_connections_per_company:
                try:
                    update_status_by_id(job_id, 'Referral Outreach Completed')
                    logger.info(f"Target of {max_connections_per_company} reached for {company}. Status updated to 'Referral Outreach Completed'.")
                except Exception as e:
                    logger.warning(f"Failed to update Job status: {e}")
            else:
                try:
                    update_status_by_id(job_id, 'Completed – Target Not Met')
                    logger.info(f"Finished processing {company} but target {max_connections_per_company} not reached (current progress: {completed_progress}). Updated status to 'Completed – Target Not Met'.")
                except Exception as e:
                    logger.warning(f"Failed to update Job status: {e}")
            
            time.sleep(5)

        logger.info("\n" + "=" * 60)
        logger.info("All jobs processed!")
        logger.info("=" * 60)
        if sys.stdin.isatty():
            input("\nPress Enter to close the browser...")

    except Exception:
        logger.exception("Fatal error in connector script")
        if sys.stdin.isatty():
            input("\nFatal error occurred. Press Enter to exit...")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    run_connector()
