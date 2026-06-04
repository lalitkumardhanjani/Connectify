from selenium import webdriver 
from selenium.webdriver.common.by import By 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC 
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options 
import time 
import json
import random
import logging
from datetime import datetime
from dotenv import load_dotenv
import os

# ============== CONFIGURATION ==============
load_dotenv()
RESUME_LINK = os.getenv("RESUME_LINK", "https://shorturl.at/Un3vp")

EMAIL = os.getenv("LINKEDIN_EMAIL")
PASSWORD = os.getenv("LINKEDIN_PASSWORD")

if not EMAIL or not PASSWORD:
    raise ValueError("Environment variables for linkdin are not loaded properly")

URL = "https://www.linkedin.com/feed/"
JSON_FILE = "linkedin_jobs.json"        # unified file (was job_data.json)
AUDIT_FILE = "linkedin_jobs_audit.json"
LOG_FILE  = "linkedin_automation_.log"

REVIEW_MODE = os.getenv("REVIEW_MODE", "0") != "0"      # True = pause and confirm before every message | False = fully automatic

# OUTREACH_MODE options:
# "connect_only"  — send requests only to not yet connected people
# "message_only"  — send messages only to already connected people
# "both"          — message connected first, then connect requests to new people (recommended)
OUTREACH_MODE = os.getenv("OUTREACH_MODE", "connect_only")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# ============== HELPER FUNCTIONS ==============

def save_debug_info(driver, step_name):
    """Save screenshot and page source for debugging"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        time.sleep(2)

        screenshot_path = f"debug_screenshot_{step_name}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logging.info(f"Saved screenshot: {screenshot_path}")

        try:
            rendered_html = driver.execute_script("return document.body.outerHTML;")
            html_path = f"debug_html_{step_name}_{timestamp}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(rendered_html)
            logging.info(f"Saved rendered HTML: {html_path}")
        except:
            html_path = f"debug_html_{step_name}_{timestamp}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logging.info(f"Saved HTML: {html_path}")

    except Exception as e:
        logging.warning(f"Could not save debug info: {str(e)}")


def load_job_data(filename):
    """Load jobs from unified JSON file - supports multiple formats"""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        
        jobs = []
        for job in data:
            # Check if it has the full format with company, position, etc.
            if "position" in job and "company" in job:
                # Full format - only include "Will Apply" status
                if job.get("status") == "Will Apply":
                    jobs.append(job)
            # Otherwise, it's the simplified format with company and url
            elif "company" in job and "url" in job:
                # Convert simplified format to full format
                jobs.append({
                    "company": job["company"],
                    "position": "Target Position",
                    "job_id": job.get("url", ""),
                    "max_apply": job.get("max_apply", 5),
                    "linkedin_id": "",
                    "url": job["url"],
                    "status": job.get("status", "")
                })
        
        return jobs
    except FileNotFoundError:
        logging.error(f"JSON file '{filename}' not found!")
        return []
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'!")
        return []

def save_json_file(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved JSON file: {filename}")
    except Exception as e:
        logging.error(f"Failed to save JSON file {filename}: {str(e)}")


def append_audit_entry(entry):
    audit_data = []
    try:
        if os.path.exists(AUDIT_FILE):
            with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                audit_data = json.load(f)
    except Exception:
        logging.warning(f"Could not read audit file {AUDIT_FILE}, creating fresh audit file")

    audit_data.append(entry)
    save_json_file(AUDIT_FILE, audit_data)


def remove_job_from_json(job):
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read {JSON_FILE} for removal: {str(e)}")
        return False

    def matches(entry):
        company_match = entry.get('company') == job.get('company')
        job_url = job.get('ShortenURL') or job.get('CompanyURL') or job.get('url', '')
        entry_url = entry.get('url', '')
        return company_match and entry_url == job_url

    filtered = [entry for entry in data if not matches(entry)]

    if len(filtered) == len(data):
        logging.warning(f"Could not find job to remove from {JSON_FILE}: {job.get('company')}")
        return False

    save_json_file(JSON_FILE, filtered)
    return True


def pause_on_error(msg="An error occurred"):
    logging.exception(msg)

    print("\n" + "=" * 80)
    print(msg)
    print("Browser remains open for debugging.")
    print("Press Enter to continue...")
    print("=" * 80)

    input()

# ============== MESSAGING ==============

MESSAGE_TEMPLATES = [
    "Hi, my sister is applying for the DBA position at {company}. Would you kindly refer her?\nJob: {job_url}\nResume: {resume}\nThank you for your support.",
]
 
LONG_TEMPLATES = [
    "Hi, my sister is applying for the DBA position at {company}. Would you kindly refer her?\nJob: {job_url}\nResume: {resume}\nThank you for your support.",
]

GREETINGS = ["Hi", "Hey", "Hello"]

def _build_job_part(job_id):
    if not job_id:
        return ""
    if job_id.startswith("http"):
        return job_id
    return f"#{job_id}"


def get_connect_review_mode():
    try:
        from user_config_manager import get_selected_user_config
        user_conf = get_selected_user_config()
        return user_conf.get("linkedin_connect", {}).get("review_mode", True)
    except Exception:
        return os.getenv("REVIEW_MODE", "0") != "0"

def get_message(
    position=None,
    company=None,
    first_name=None,
    job_url=None,
    resume_link=None,
    max_length=300
):
    try:
        from user_config_manager import get_selected_user_config, substitute_template_variables
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    
    template = connect_conf.get("message_template")
    if not template:
        from user_config_manager import DEFAULT_CONNECTION_TEMPLATE
        template = DEFAULT_CONNECTION_TEMPLATE

    if not resume_link:
        resume_link = profile.get("resume_url", "")
    
    extra_vars = {
        "{company}": company or "the company",
        "{job_url}": job_url or "",
        "{resume}": resume_link or "",
        "{first_name}": first_name or "there",
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()

def get_message_connected(
    position=None,
    job_id=None,
    resume_link=None,
    person_name=None,
    their_role=None,
    company=None,
):
    try:
        from user_config_manager import get_selected_user_config, substitute_template_variables
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    
    template = connect_conf.get("message_template")
    if not template:
        from user_config_manager import DEFAULT_CONNECTION_TEMPLATE
        template = DEFAULT_CONNECTION_TEMPLATE

    if not resume_link:
        resume_link = profile.get("resume_url", "")
        
    recip_first_name = "there"
    if person_name:
        recip_first_name = person_name.split()[0]
        
    extra_vars = {
        "{company}": company or "your company",
        "{job_url}": job_id or "",
        "{resume}": resume_link or "",
        "{first_name}": recip_first_name,
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()

def review_and_confirm_message(templates_func, label, *args, **kwargs):
    """
    Show all possible messages, let user pick or approve.
    Returns final message string or None to skip.
    Only runs when REVIEW_MODE = True.
    """
    if not get_connect_review_mode():
        return templates_func(*args, **kwargs)

    msg = templates_func(*args, **kwargs)
    
    logging.info("\n" + "─" * 60)
    logging.info(f"REVIEW CONNECTION NOTE: {label}")
    logging.info("─" * 60)
    logging.info(msg)
    logging.info("─" * 60)
    logging.info(f"Length: {len(msg)} / 300 characters")
    logging.info("─" * 60)
    
    choice = input("Approve and send this note? (Y/N/Edit): ").strip().lower()
    if choice == 'y' or choice == '':
        logging.info("Approved.")
        return msg
    elif choice == 'edit':
        logging.info("Paste your custom message (press Enter twice when done):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        custom = "\n".join(lines).strip()
        logging.info(f"Custom message set ({len(custom)} chars)")
        return custom
    else:
        logging.info("Skipped.")
        return None


# ============== SELENIUM HELPERS ==============

def safe_click(driver, by, selector, wait_time=10, description="element"):
    """Safely click an element with error handling"""
    try:
        wait = WebDriverWait(driver, wait_time)
        element = wait.until(EC.element_to_be_clickable((by, selector)))
        element.click()
        logging.info(f"Successfully clicked {description}")
        return True
    except (TimeoutException, NoSuchElementException) as e:
        logging.warning(f"Could not click {description}: {str(e)}")
        return False


def safe_send_keys(driver, by, selector, text, wait_time=10, description="input"):
    """Safely send keys to an element with error handling"""
    try:
        wait = WebDriverWait(driver, wait_time)
        element = wait.until(EC.visibility_of_element_located((by, selector)))
        element.clear()
        element.send_keys(text)
        logging.info(f"Successfully entered text in {description}")
        return element
    except (TimeoutException, NoSuchElementException) as e:
        logging.warning(f"Could not send keys to {description}: {str(e)}")
        return None


def login_to_linkedin_2(driver, email, password):
    """Handle LinkedIn login if needed - OPTIMIZED VERSION"""
    logging.info("Checking if already logged in...")

    try:
        search_bar_selectors = [
            "input[placeholder*='Search']",
            ".search-global-typeahead__input",
            "input[role='combobox']"
        ]

        for selector in search_bar_selectors:
            try:
                search_bar = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if search_bar:
                    logging.info("Already logged in! (Search bar found)")
                    return
            except TimeoutException:
                continue

        logging.info("Not logged in. Attempting login...")

    except Exception as e:
        logging.warning(f"Error checking for search bar: {str(e)}")

    try:
        email_selectors = [
            "input[id*='username']",
            "input[name='session_key']",
            "input[type='email']",
            "#username"
        ]

        email_input = None
        for selector in email_selectors:
            try:
                wait = WebDriverWait(driver, 3)
                email_input = wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                break
            except TimeoutException:
                continue

        if email_input:
            logging.info("Login required. Attempting to log in...")
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

            time.sleep(5)
            logging.info("Login successful!")
        else:
            logging.info("No login form found - assuming already logged in")

    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        logging.info("Continuing anyway - might already be logged in")


def login_to_linkedin(driver, email, password):
    """Handle LinkedIn login if needed"""
    logging.info("Checking if login is required...")
    time.sleep(3)

    try:
        email_selectors = [
            "input[id*='username']",
            "input[name='session_key']",
            "input[type='email']",
            "#username"
        ]

        email_input = None
        for selector in email_selectors:
            try:
                wait = WebDriverWait(driver, 3)
                email_input = wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                break
            except TimeoutException:
                continue

        if email_input:
            logging.info("Login required. Attempting to log in...")
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

            time.sleep(3)
            logging.debug("Login successful!")
        else:
            logging.debug("Already logged in!")

    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        logging.info("Continuing anyway - might already be logged in")


def search_company(driver, company_name):
    """Search for a company on LinkedIn"""
    logging.info(f"Searching for company: {company_name}")

    try:
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={company_name.replace(' ', '%20')}&origin=FACETED_SEARCH"
        driver.get(search_url)
        logging.debug(f"Navigated directly to search results URL")
        time.sleep(4)
        return True
    except Exception as e:
        logging.error(f"Direct navigation failed: {str(e)}")
        return False


def navigate_to_company_people(driver, company_name):
    """Navigate to the People section of a company page"""
    logging.info(f"Navigating to {company_name} People section...")

    try:
        time.sleep(3)

        try:
            companies_button = driver.find_element(
                By.XPATH,
                "//button[contains(text(), 'Companies') or contains(@aria-label, 'Companies')]"
            )
            companies_button.click()
            logging.debug("Clicked Companies filter")
            time.sleep(7)
        except NoSuchElementException:
            logging.warning("Could not find Companies filter button")

        company_link_selectors = [
            "a.app-aware-link[href*='/company/']",
            ".entity-result__title-text a",
            "a[data-control-name='search_srp_result']"
        ]

        for selector in company_link_selectors:
            try:
                company_link = driver.find_element(By.CSS_SELECTOR, selector)
                company_link.click()
                logging.debug(f"Clicked on company profile")
                time.sleep(3)
                break
            except NoSuchElementException:
                continue

        people_tab_selectors = [
            "a[href*='/people/']",
            "//a[contains(text(), 'People')]",
            "a.org-page-navigation__item-anchor[href*='people']"
        ]

        for selector in people_tab_selectors:
            try:
                if selector.startswith("//"):
                    people_tab = driver.find_element(By.XPATH, selector)
                else:
                    people_tab = driver.find_element(By.CSS_SELECTOR, selector)
                people_tab.click()
                logging.debug("Navigated to People section")
                time.sleep(7)
                return True
            except NoSuchElementException:
                continue

        logging.error("Could not find People tab")
        return False

    except Exception as e:
        logging.error(f"Error navigating to company people: {str(e)}")
        return False


def navigate_to_company_direct(driver, company_linkedin_id):
    """Navigate directly to company people page using company LinkedIn ID"""
    try:
        url = f"https://www.linkedin.com/company/{company_linkedin_id}/people/"
        driver.get(url)
        logging.debug(f"Navigated directly to {company_linkedin_id} people page")
        time.sleep(3)
        return True
    except Exception as e:
        logging.error(f"Error in direct navigation: {str(e)}")
        return False


# ============== PEOPLE FINDERS ==============

def find_people_with_connect_button(driver, max_people=10):
    """Find people with Connect button"""

    logging.info(f"Looking for up to {max_people} people with Connect button...")

    people_with_connect = []

    try:
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

        people_cards = driver.find_elements(By.XPATH, "//div[@role='listitem']")
        logging.debug(f"Found {len(people_cards)} people cards")

        for card in people_cards:

            if len(people_with_connect) >= max_people:
                break

            try:
                connect_button = card.find_element(
                    By.CSS_SELECTOR,
                    "a[aria-label*='to connect']"
                )

                name = ""
                name_selectors = [
                    ".entity-result__title-text span[aria-hidden='true']",
                    ".entity-result__title-text a",
                    ".entity-result__title-text",
                    "span.entity-result__title-line",
                    "a[href*='/in/']"
                ]
                for selector in name_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, selector)
                        val = el.text.strip()
                        if val:
                            if "•" in val:
                                val = val.split("•")[0].strip()
                            if "\n" in val:
                                val = val.split("\n")[0].strip()
                            name = val
                            break
                    except:
                        continue

                role = ""
                role_selectors = [
                    ".entity-result__primary-subtitle",
                    ".entity-result__badge-container + div",
                    "div[class*='subtitle']"
                ]
                for selector in role_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, selector)
                        val = el.text.strip()
                        if val:
                            role = val
                            break
                    except:
                        continue

                people_with_connect.append({
                    'button': connect_button,
                    'card':   card,
                    'name':   name,
                    'role':   role,
                })

            except NoSuchElementException:
                continue

        logging.info(f"Total people with Connect button: {len(people_with_connect)}")
        return people_with_connect

    except Exception as e:
        logging.error(f"Error finding people: {str(e)}")
        return people_with_connect


def find_people_already_connected(driver, max_people=10):
    """Filter by 1st connections then find Message buttons"""

    logging.info("Applying 1st connections filter...")

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
        logging.info("1st connections filter applied")

    except Exception as e:
        logging.warning(f"Could not apply 1st connections filter: {str(e)}")
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

                # Name from message button aria-label
                try:
                    aria = message_button.get_attribute("aria-label") or ""

                    if aria.startswith("Send a message to"):
                        name = aria.replace("Send a message to", "").strip()

                except Exception as e:
                    logging.warning(f"Could not extract name from aria-label: {e}")

                # Profile URL
                try:
                    profile_url = card.find_element(
                        By.CSS_SELECTOR,
                        "a[href*='/in/']"
                    ).get_attribute("href")
                except:
                    pass

                # Fallback role extraction
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

                except:
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

        logging.info(f"Total 1st connection people found: {len(people_connected)}")
        return people_connected

    except Exception as e:
        logging.error(f"Error finding connected people: {str(e)}")
        return people_connected


# ============== SENDERS ==============

def verify_connection_sent(driver, person):
    """Verify that connection request was sent by checking if button changed to Pending"""
    try:
        time.sleep(1)
        button_element = person['button']

        button_text = None
        try:
            button_text = button_element.text.strip().lower()
        except:
            try:
                button_text = driver.execute_script(
                    "return arguments[0].textContent;", button_element
                ).strip().lower()
            except:
                pass

        if button_text:
            if 'pending' in button_text:
                logging.info("✓ Verified: Button changed to 'Pending' - request sent successfully")
                return True
            elif 'connect' in button_text:
                logging.debug("⚠ Button still shows 'Connect' - request may not have sent")
                return False
            else:
                logging.info(f"Button text: '{button_text}' - assuming sent")
                return True
        else:
            try:
                pending_found = driver.execute_script("""
                    const host = document.querySelector('#interop-outlet');
                    if (!host || !host.shadowRoot) return false;
                    const buttons = host.shadowRoot.querySelectorAll('button');
                    for (let btn of buttons) {
                        if (btn.textContent.toLowerCase().includes('pending')) return true;
                    }
                    return false;
                """)
                if pending_found:
                    logging.info("✓ Verified: 'Pending' found in shadow DOM")
                    return True
            except:
                pass

            logging.debug("Could not verify button state - assuming sent")
            return True

    except Exception as e:
        logging.debug(f"Could not verify connection sent: {str(e)}")
        return True


def send_connection_request(driver, person, message):
    """Send connection request with a message"""
    try:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", person['button']
            )
            time.sleep(2)
        except Exception as e:
            logging.debug(f"Could not scroll to button: {str(e)}")

        connect_clicked = False

        try:
            person['button'].click()
            logging.debug("Clicked Connect button (regular click)")
            connect_clicked = True
            time.sleep(2)
        except Exception as e:
            logging.debug(f"Regular click failed: {str(e)}")

        if not connect_clicked:
            try:
                driver.execute_script("arguments[0].click();", person['button'])
                logging.debug("Clicked Connect button (JavaScript click)")
                connect_clicked = True
                time.sleep(3)
            except Exception as e:
                logging.error(f"JavaScript click also failed: {str(e)}")
                logging.error("Connect button failed; proceeding without debug info")
                return False

        if not connect_clicked:
            logging.error("Failed to click Connect button")
            logging.error("Connect button not clicked; proceeding without debug info")
            return False

        logging.debug("Waiting for modal dialog to fully render...")
        time.sleep(4)

        try:
            how_know_options = driver.find_elements(
                By.XPATH, "//label[contains(@for, 'connect-choice')]"
            )
            if how_know_options:
                logging.debug("Found 'How do you know' screen, selecting first option")
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
                        logging.debug("Clicked Continue button")
                        time.sleep(1)
                        break
                    except NoSuchElementException:
                        continue
        except Exception as e:
            logging.debug(f"No 'How do you know' screen or error: {str(e)}")

        add_note_clicked = False

        add_note_css_selectors = [
            "button[aria-label='Add a note']",
            "button.artdeco-button--primary",
            "button.ml1.artdeco-button--primary"
        ]

        for selector in add_note_css_selectors:
            try:
                add_note_button = driver.execute_script("""
                    const host = document.querySelector('#interop-outlet');
                    if (!host) return null;
                    const root = host.shadowRoot;
                    if (!root) return null;
                    return root.querySelector(arguments[0]);
                """, selector)

                if not add_note_button:
                    continue

                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", add_note_button
                )
                time.sleep(1)
                driver.execute_script("arguments[0].click();", add_note_button)
                logging.debug("Clicked 'Add a note' button via Shadow DOM JavaScript")
                add_note_clicked = True
                time.sleep(3)
                break

            except Exception as e:
                logging.warning(f"Error with selector {selector}: {str(e)}")
                continue

        if add_note_clicked:
            message_box_selectors = [
                "textarea[name='message']",
                "textarea#custom-message",
                "textarea.ember-text-area",
                "textarea[placeholder*='note']"
            ]

            message_box = None

            for selector in message_box_selectors:
                try:
                    message_box = driver.execute_script("""
                        const host = document.querySelector('#interop-outlet');
                        if (!host) return null;
                        const root = host.shadowRoot;
                        if (!root) return null;
                        return root.querySelector(arguments[0]);
                    """, selector)
                    if message_box:
                        break
                except Exception as e:
                    logging.warning(f"Message box selector failed: {str(e)}")

            if message_box:
                driver.execute_script("arguments[0].value = '';", message_box)
                time.sleep(0.3)
                driver.execute_script("""
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, message_box, message)
                logging.debug(f"Added message to connection request")
                time.sleep(1)

                send_button_selectors = [
                    "button[aria-label='Send invitation']",
                    "button.artdeco-button--primary",
                    "button.ml1.artdeco-button--primary",
                ]

                send_clicked = False

                for selector in send_button_selectors:
                    try:
                        send_button = driver.execute_script("""
                            const host = document.querySelector('#interop-outlet');
                            if (!host) return null;
                            const root = host.shadowRoot;
                            if (!root) return null;
                            return root.querySelector(arguments[0]);
                        """, selector)

                        if not send_button:
                            continue

                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", send_button
                        )
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", send_button)

                        logging.info("✓ Clicked Send button - assuming request sent successfully")
                        send_clicked = True
                        time.sleep(3)
                        return True

                    except Exception as e:
                        logging.debug(f"Send selector failed: {str(e)}")
                        continue

                if not send_clicked:
                    logging.warning("Could not find or click Send button")
                    close_dialog(driver)
                    return False

            else:
                logging.warning("Could not find message box")
                close_dialog(driver)
                return False

        else:
            logging.info(f"No 'Add a note' option found, trying to send without message")
            save_debug_info(driver, "no_add_note_button")

            send_button_selectors = [
                "button.artdeco-button--primary[aria-label*='Send']",
                "button.ml1.artdeco-button--primary",
                "button[aria-label*='Send without']",
                "button.artdeco-button--primary"
            ]

            for selector in send_button_selectors:
                try:
                    send_button = driver.execute_script("""
                        const host = document.querySelector('#interop-outlet');
                        if (!host) return null;
                        const root = host.shadowRoot;
                        if (!root) return null;
                        return root.querySelector(arguments[0]);
                    """, selector)

                    if not send_button:
                        continue

                    driver.execute_script("arguments[0].click();", send_button)

                    try:
                        send_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", send_button)

                    time.sleep(2)
                    return True

                except TimeoutException:
                    continue
                except Exception as e:
                    logging.debug(f"Error: {str(e)}")
                    continue

            logging.debug(f"Could not send connection request")
            close_dialog(driver)
            return False

    except Exception as e:
        logging.debug(f"Error sending connection request: {str(e)}")
        close_dialog(driver)
        return False

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import pyperclip
import time
import logging


def send_direct_message(driver, person, message):
    """Send message to already connected person"""

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            person["button"]
        )

        time.sleep(1)

        person["button"].click()

        time.sleep(3)

        editor = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');

            if (!host || !host.shadowRoot)
                return null;

            return host.shadowRoot.querySelector(
                '.msg-form__contenteditable'
            );
        """)

        if not editor:
            raise Exception("Message editor not found")

        driver.execute_script("""
            arguments[0].scrollIntoView({block:'center'});
            arguments[0].click();
            arguments[0].focus();
        """, editor)
        time.sleep(1)

        # inject text directly via JS — same approach as send_connection_request
        driver.execute_script("""
            const editor = arguments[0];
            const text   = arguments[1];

            editor.focus();
            editor.click();

            // clear existing content
            editor.innerText = '';

            // insert text
            document.execCommand('insertText', false, text);

            // fire full event chain LinkedIn React listens to
            ['input', 'change', 'keydown', 'keyup', 'keypress'].forEach(eventType => {
                const event = new Event(eventType, { bubbles: true, cancelable: true });
                editor.dispatchEvent(event);
            });

            // also fire InputEvent specifically — React 16+ listens to this
            const inputEvent = new InputEvent('input', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text
            });
            editor.dispatchEvent(inputEvent);

        """, editor, message)
        time.sleep(1)
        
        editor_text = driver.execute_script("return arguments[0].innerText;", editor)
        editor_html = driver.execute_script("return arguments[0].innerHTML;", editor)
        logging.info(f"Editor innerText: {repr(editor_text)}")
        logging.info(f"Editor innerHTML: {repr(editor_html)}")


        editor_text = driver.execute_script("""
            return arguments[0].innerText;
        """, editor)

        print("EDITOR TEXT:")
        print(repr(editor_text))

        send_button = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');

            if (!host || !host.shadowRoot)
                return null;

            return host.shadowRoot.querySelector(
                '.msg-form__send-button'
            );
        """)

        if not send_button:
            raise Exception("Send button not found")

        print(
            "SEND ENABLED:",
            send_button.get_attribute("disabled") is None
        )

        if send_button.get_attribute("disabled") is not None:
            raise Exception("Message was not actually inserted")

        driver.execute_script(
            "arguments[0].click();",
            send_button
        )

        time.sleep(3)

        logging.info(
            f"Message sent to {person.get('name', 'unknown')}"
        )

        return True

    except Exception as e:
        logging.error(
            f"Failed to send message: {str(e)}"
        )
        return False

def close_dialog(driver):
    """Close LinkedIn modal dialog"""
    try:
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

        logging.debug(f"Close dialog result: {result}")
        time.sleep(1)
        return result == "SUCCESS"

    except Exception as e:
        logging.debug(f"Could not close dialog: {str(e)}")
        return False


def go_to_next_page(driver):
    """Go to next LinkedIn people search page"""
    try:
        logging.debug("Trying to navigate to next page...")

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
            logging.warning("Next page button not found")
            return False

        is_disabled = driver.execute_script("return arguments[0].disabled;", next_button)

        if is_disabled:
            logging.info("Next page button disabled")
            return False

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", next_button)
        logging.info("Moved to next page")
        time.sleep(5)
        return True

    except Exception as e:
        logging.warning(f"Could not move to next page: {str(e)}")
        return False


# ============== MAIN SCRIPT ==============

def main():
    logging.info("=" * 60)
    logging.info("LinkedIn Referral Request Automation Starting...")
    logging.info(f"REVIEW_MODE  : {REVIEW_MODE}")
    logging.info(f"OUTREACH_MODE: {OUTREACH_MODE}")
    logging.info("=" * 60)

    from excel_adapter import get_jobs_for_referral

    job_data = get_jobs_for_referral()

    if not job_data:
        logging.error("No referral jobs found! Exiting...")
        return

    logging.info(f"Loaded {len(job_data)} jobs with status 'Asked for referral'.")

    # Chrome setup matching other scripts (using linkedin_job_driver.py)
    from linkedin_job_driver import get_driver
    try:
        driver = get_driver()
    except Exception as e:
        logging.error(f"Error starting Chrome: {e}")
        return

    try:
        driver.get(URL)
        login_to_linkedin_2(driver, EMAIL, PASSWORD)

        for job in job_data:
            # Extract fields using Excel column names
            company     = job.get('CompanyName') or ''
            position    = job.get('SearchKeyword') or ''
            job_id      = job.get('JobID') or ''
            job_url     = job.get('ShortenURL') or job.get('CompanyURL') or ''
            max_apply   = job.get('max_apply') or 5  # default to 5 requests per job
            linkedin_id = job.get('linkedin_id', '')

            logging.info("\n" + "=" * 60)
            logging.info(f"Processing: {company} — {position}")
            logging.info(f"OUTREACH_MODE: {OUTREACH_MODE}  |  REVIEW_MODE: {REVIEW_MODE}")
            logging.info("=" * 60)

            # ── Navigate to company people page ──
            navigation_success = False

            if linkedin_id:
                logging.info(f"Using direct navigation with linkedin_id: {linkedin_id}")
                navigation_success = navigate_to_company_direct(driver, linkedin_id)

            if not navigation_success:
                logging.info(f"Using search method for {company}")
                if not search_company(driver, company):
                    logging.error(f"Failed to search for {company}. Skipping...")
                    continue
                navigation_success = True

            if not navigation_success:
                logging.error(f"Failed to navigate to {company} people page. Skipping...")
                continue

            msg_count     = 0
            existing_referrals = job.get('ReferralPerson')
            if existing_referrals:
                success_count = len([n for n in str(existing_referrals).split(',') if n.strip()])
            else:
                success_count = 0
            logging.info(f"Existing referrals already sent for this job: {success_count}/{max_apply}")

            # ── Step 2: Connect requests to new people (1st filter naturally OFF) ──
            if OUTREACH_MODE in ("connect_only", "both"):

                page_number = 1

                while success_count < max_apply:

                    logging.info(f"\nProcessing page {page_number} for connect requests")
                    remaining = max_apply - success_count

                    people = find_people_with_connect_button(driver, max_people=remaining)

                    if not people:
                        logging.warning("No connectable people found on this page")
                        if not go_to_next_page(driver):
                            logging.warning("No more pages available")
                            break
                        page_number += 1
                        continue

                    for person in people:
                        if success_count >= max_apply:
                            break
                        try:
                            first_name = person['name'].split()[0] if person['name'] else "there"
                            message = get_message(
                                position=position,
                                company=company,
                                first_name=first_name,
                                job_url=job_url,
                                resume_link=RESUME_LINK,
                            )
                            
                            if send_connection_request(driver, person, message):
                                success_count += 1
                                # Record referral person and update job status
                                try:
                                    job_id_val = job.get('JobID') or job_id
                                    person_name = person.get('name') or 'Unknown'
                                    # Append the referral person's name
                                    from excel_adapter import add_referral_person
                                    add_referral_person(job_id_val, person_name)
                                    # Update the status: 'Done' if we reached 5, else keep 'Ask for referral'
                                    from data_store import update_status_by_id
                                    if success_count >= max_apply:
                                        update_status_by_id(job_id_val, 'Done')
                                    else:
                                        update_status_by_id(job_id_val, 'Ask for referral')
                                except Exception as e:
                                    logging.warning(f"Failed to record referral info: {e}")
                                logging.info(f"Connect requests sent: {success_count}/{max_apply}")
                        except Exception as e:
                            logging.warning(f"Failed sending connect request: {str(e)}")
                        time.sleep(random.randint(3, 7))

                    if success_count >= max_apply:
                        break

                    if not go_to_next_page(driver):
                        break
                    page_number += 1

                if success_count >= max_apply and success_count > 0:
                    removed = remove_job_from_json(job)
                    audit_entry = {
                        "company": company,
                        "position": position,
                        "job_id": job_id,
                        "job_url": job_id,
                        "max_apply": max_apply,
                        "success_count": success_count,
                        "removed_at": datetime.now().isoformat(),
                        "removed": removed,
                    }
                    append_audit_entry(audit_entry)
                    logging.info(f"Removed completed job from {JSON_FILE}: {company}")

            # ── Step 1: Message already connected (1st filter ON) ──
            if OUTREACH_MODE in ("message_only", "both"):

                connected_people = find_people_already_connected(driver, max_people=max_apply)

                if connected_people:
                    logging.info(f"Found {len(connected_people)} already connected — sending messages")

                    for person in connected_people:
                        long_message = review_and_confirm_message(
                            get_message_connected,
                            f"LONG MESSAGE — {person.get('name', 'unknown')} at {company}",
                            position=position,
                            job_id=job_id,
                            person_name=person.get('name'),
                            their_role=person.get('role'),
                        )
                        if long_message is None:
                            logging.info(f"Skipping message to {person.get('name', 'unknown')}")
                            continue
                        try:
                            if send_direct_message(driver, person, long_message):
                                msg_count += 1
                        except Exception as e:
                            logging.warning(f"Failed sending message: {str(e)}")
                        time.sleep(random.randint(3, 7))

                    logging.info(f"✓ Messages sent: {msg_count}/{len(connected_people)}")
                else:
                    logging.info("No already connected people found")


            logging.info(
                f"\n✓ Completed {company}: {success_count} connect requests, {msg_count} messages sent"
            )
            time.sleep(5)

        logging.info("\n" + "=" * 60)
        logging.info("All jobs processed!")
        logging.info(f"Log saved to: {LOG_FILE}")
        logging.info("Browser will remain open. Close manually when done.")
        logging.info("=" * 60)

        input("\nPress Enter to close the browser...")

    except Exception:
        logging.exception("Fatal error")

        input(
            "\nFatal error occurred. "
            "Browser is still open for debugging.\n"
            "Press Enter to exit..."
        )

    finally:
        logging.info("Script finished. Browser remains open.")


if __name__ == "__main__":
    main()
