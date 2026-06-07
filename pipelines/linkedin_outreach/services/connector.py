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
        "{company}": company or "your company",
        "{job_url}": job_id or "",
        "{resume}": resume_link or "",
        "{first_name}": recip_first_name,
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
                logger.info("No login form found - assuming already logged in")
                return True
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

def search_company(driver, company_name):
    """Search for a company on LinkedIn"""
    logger.info(f"Searching for company: {company_name}")
    try:
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={company_name.replace(' ', '%20')}&origin=FACETED_SEARCH"
        driver.get(search_url)
        time.sleep(4)
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
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

        people_cards = driver.find_elements(By.XPATH, "//div[@role='listitem']")
        for card in people_cards:
            if len(people_with_connect) >= max_people:
                break
            try:
                connect_button = None
                buttons = card.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    try:
                        aria = btn.get_attribute("aria-label") or ""
                        text = btn.text or ""
                        if "to connect" in aria.lower() or "connect" in aria.lower() or text.strip().lower() == "connect":
                            connect_button = btn
                            break
                    except Exception:
                        continue
                
                if not connect_button:
                    try:
                        connect_button = card.find_element(By.XPATH, ".//*[contains(@aria-label, 'to connect') or contains(@aria-label, 'Connect')]")
                    except Exception:
                        pass
                
                if not connect_button:
                    continue

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
                    except Exception:
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
                    except Exception:
                        continue

                profile_url = ""
                try:
                    profile_link = card.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                    profile_url = profile_link.get_attribute("href")
                    if "?" in profile_url:
                        profile_url = profile_url.split("?")[0]
                except Exception:
                    pass

                people_with_connect.append({
                    'button': connect_button,
                    'card':   card,
                    'name':   name,
                    'role':   role,
                    'profile_url': profile_url
                })
            except NoSuchElementException:
                continue
        logger.info(f"Total people with Connect button: {len(people_with_connect)}")
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
        add_note_css_selectors = [
            "button[aria-label='Add a note']",
            "button.artdeco-button--primary",
            "button.ml1.artdeco-button--primary"
        ]

        add_note_button = None
        for selector in add_note_css_selectors:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    add_note_button = btn
                    break
            except Exception:
                pass
            try:
                btn = driver.execute_script("""
                    const host = document.querySelector('#interop-outlet');
                    if (!host || !host.shadowRoot) return null;
                    return host.shadowRoot.querySelector(arguments[0]);
                """, selector)
                if btn:
                    add_note_button = btn
                    break
            except Exception:
                pass

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
            message_box_selectors = [
                "textarea[name='message']",
                "textarea#custom-message",
                "textarea.ember-text-area",
                "textarea[placeholder*='note']"
            ]
            message_box = None
            for selector in message_box_selectors:
                try:
                    box = driver.find_element(By.CSS_SELECTOR, selector)
                    if box.is_displayed():
                        message_box = box
                        break
                except Exception:
                    pass
                try:
                    box = driver.execute_script("""
                        const host = document.querySelector('#interop-outlet');
                        if (!host || !host.shadowRoot) return null;
                        return host.shadowRoot.querySelector(arguments[0]);
                    """, selector)
                    if box:
                        message_box = box
                        break
                except Exception:
                    pass

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

                send_button_selectors = [
                    "button[aria-label='Send invitation']",
                    "button.artdeco-button--primary",
                    "button.ml1.artdeco-button--primary",
                ]

                send_btn = None
                for selector in send_button_selectors:
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, selector)
                        if btn.is_displayed():
                            send_btn = btn
                            break
                    except Exception:
                        pass
                    try:
                        btn = driver.execute_script("""
                            const host = document.querySelector('#interop-outlet');
                            if (!host || !host.shadowRoot) return null;
                            return host.shadowRoot.querySelector(arguments[0]);
                        """, selector)
                        if btn:
                            send_btn = btn
                            break
                    except Exception:
                        pass

                if send_btn:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", send_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", send_btn)
                    time.sleep(3)
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
            save_debug_info(driver, "no_add_note_button")
            if review_mode is None:
                review_mode = get_connect_review_mode()
            if review_mode:
                print("\n" + "="*50)
                print("INVITE QUALITY GATE - CONNECT WITHOUT NOTE REVIEW")
                print("="*50)
                print(f"Recipient: {person.get('name', 'unknown')} ({person.get('role', 'unknown')})")
                print("="*50)
                print("Enter action (Send [S] / Skip [K] / Quit [Q]):")
                choice = input().strip().lower()
                while choice not in ('s', 'k', 'q'):
                    print("Invalid option. Please enter Send [S], Skip [K], or Quit [Q]:")
                    choice = input().strip().lower()
                if choice == 'k':
                    close_dialog(driver)
                    return "skipped"
                elif choice == 'q':
                    close_dialog(driver)
                    return "quit"

            send_button_selectors = [
                "button.artdeco-button--primary[aria-label*='Send']",
                "button.ml1.artdeco-button--primary",
                "button[aria-label*='Send without']",
                "button.artdeco-button--primary"
            ]

            send_btn = None
            for selector in send_button_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        send_btn = btn
                        break
                except Exception:
                    pass
                try:
                    btn = driver.execute_script("""
                        const host = document.querySelector('#interop-outlet');
                        if (!host || !host.shadowRoot) return null;
                        return host.shadowRoot.querySelector(arguments[0]);
                    """, selector)
                    if btn:
                        send_btn = btn
                        break
                except Exception:
                    pass

            if send_btn:
                driver.execute_script("arguments[0].click();", send_btn)
                time.sleep(2)
                return True
            close_dialog(driver)
            return False
    except Exception as e:
        logger.error(f"Error sending connection request: {str(e)}")
        close_dialog(driver)
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
    max_connections = int(connect_conf.get("max_connections_per_run") or 5)
    total_connections_sent = 0
    
    outreach_mode = os.getenv("OUTREACH_MODE", "connect_only")
    review_mode = get_connect_review_mode()
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    resume_link = user_conf.get("profile", {}).get("resume_url", "")
    
    logger.info(f"REVIEW_MODE  : {review_mode}")
    logger.info(f"OUTREACH_MODE: {outreach_mode}")
    logger.info(f"MAX_LIMIT    : {max_connections}")
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
            if total_connections_sent >= max_connections:
                logger.info(f"Global run limit of {max_connections} connection requests reached. Stopping pipeline.")
                break

            company = job.get('CompanyName') or ''
            
            # Check company target connections progress
            total_progress = get_employee_outreach_progress(company)
            if total_progress >= max_connections:
                logger.info(f"Company '{company}' has already reached its target connection count of {max_connections} (progress: {total_progress}). Skipping.")
                continue
                
            position = job.get('SearchKeyword') or ''
            job_id = job.get('JobID') or ''
            job_url = job.get('ShortenURL') or job.get('CompanyURL') or ''
            
            # Compute remaining target capacity for this company
            max_apply = max_connections - total_progress
            logger.info(f"Company '{company}' remaining target count is {max_apply} (progress: {total_progress}).")
            linkedin_id = job.get('linkedin_id', '')

            logger.info("\n" + "=" * 60)
            logger.info(f"Processing: {company} — {position}")
            logger.info("=" * 60)

            navigation_success = False
            if linkedin_id:
                logger.info(f"Using direct navigation with linkedin_id: {linkedin_id}")
                navigation_success = navigate_to_company_direct(driver, linkedin_id)

            if not navigation_success:
                logger.info(f"Using search method for {company}")
                if not search_company(driver, company):
                    logger.error(f"Failed to search for {company}. Skipping...")
                    continue
                navigation_success = True

            msg_count = 0
            success_count = 0
            logger.info(f"Starting outreach requests for this job: {success_count}/{max_apply}")

            # Send connect requests to new people
            if outreach_mode in ("connect_only", "both"):
                page_number = 1
                while success_count < max_apply and total_connections_sent < max_connections:
                    logger.info(f"\nProcessing page {page_number} for connect requests")
                    remaining = min(max_apply - success_count, max_connections - total_connections_sent)
                    people = find_people_with_connect_button(driver, max_people=remaining)

                    if not people:
                        logger.warning("No connectable people found on this page")
                        if not go_to_next_page(driver):
                            logger.warning("No more pages available")
                            break
                        page_number += 1
                        continue

                    for person in people:
                        if success_count >= max_apply or total_connections_sent >= max_connections:
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
                            if sent == "skipped":
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
                                logger.info(f"Total connections sent in this run: {total_connections_sent}/{max_connections}")
                            else:
                                status_val = 'Failed'
                                error_reason = 'Connection invitation note could not be sent'

                            if sent != "quit":
                                try:
                                    from core.storage.database import add_or_update_referral
                                    referral_data = {
                                        'JobID': job_id,
                                        'CompanyName': company,
                                        'Referral_Person_Name': person.get('name', 'unknown'),
                                        'Referral_Person_Email': '',
                                        'Referral_Person_Profile_URL': person.get('profile_url', ''),
                                        'Referral_Person_Designation': person.get('role', ''),
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

                    if success_count >= max_apply or total_connections_sent >= max_connections:
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
                                'Referral_Person_Name': person.get('name', 'unknown'),
                                'Referral_Person_Email': '',
                                'Referral_Person_Profile_URL': person.get('profile_url', ''),
                                'Referral_Person_Designation': person.get('role', ''),
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
            total_progress = get_employee_outreach_progress(company)
            if total_progress >= max_connections:
                try:
                    update_status_by_id(job_id, 'Asked for Referral')
                    logger.info(f"Target of {max_connections} reached for {company}. Status updated to 'Asked for Referral'.")
                except Exception as e:
                    logger.warning(f"Failed to update Job status: {e}")
            else:
                try:
                    update_status_by_id(job_id, 'Completed – Target Not Met')
                    logger.info(f"Finished processing {company} but target {max_connections} not reached (current progress: {total_progress}). Updated status to 'Completed – Target Not Met'.")
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
