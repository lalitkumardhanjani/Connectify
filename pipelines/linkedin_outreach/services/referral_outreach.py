import os
import sys
import time
import random
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

from config.settings import LINKEDIN_CONNECT_LOG_FILE
from config.user_profiles import get_selected_user_config, get_global_settings, substitute_template_variables, get_resume_file_path
from core.integrations.selenium_driver import get_driver
from core.storage.database import (
    load_jobs_for_referral,
    add_or_update_referral,
    is_profile_already_contacted,
    load_all_referrals
)
from core.logging.config import setup_logger

# Reuse helpers from the main connector module
from pipelines.linkedin_outreach.services.connector import (
    login_to_linkedin,
    review_and_confirm_message
)

logger = setup_logger(LINKEDIN_CONNECT_LOG_FILE)

def get_referral_message(company=None, target_role=None, person_name=None, employee_designation=None, job_url=None):
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}

    profile = user_conf.get("profile", {})
    connect_conf = user_conf.get("linkedin_connect", {})
    referral_conf = user_conf.get("referral_outreach", {})
    
    template = referral_conf.get("message_template")
    if not template:
        template = connect_conf.get("message_template")
    if not template:
        template = "Hi {PERSON_NAME}, I noticed we are connected and saw you work as {employee_designation} at {company}. I'm interested in the {target_role} role there. I'd love to get your guidance or a referral if possible! My resume: {resume}"

    resume_link = profile.get("resume_url", "")
    candidate_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or "Candidate"
    
    resolved_person_name = "there"
    if person_name:
        resolved_person_name = person_name.split()[0] if person_name.strip() else "there"

    extra_vars = {
        "{company}": company or "the company",
        "{resume}": resume_link or "",
        "{first_name}": resolved_person_name,
        "{PERSON_NAME}": resolved_person_name,
        "{target_role}": target_role or "relevant role",
        "{employee_designation}": employee_designation or "employee",
        "{candidate_name}": candidate_name,
        "{job_url}": job_url or ""
    }
    
    msg = substitute_template_variables(template, profile, extra_vars)
    return msg.strip()


def find_company_employees_search_url(driver, company_name):
    """Navigates to company page and finds the search URL for its employees."""
    slug = company_name.lower().replace(" ", "-").replace(".", "").replace(",", "")
    url = f"https://www.linkedin.com/company/{slug}/"
    logger.info(f"Navigating directly to company: {url}")
    try:
        driver.get(url)
        time.sleep(4)
    except Exception as e:
        logger.warning(f"Direct navigation failed: {e}")

    # Fallback search if page not found
    if "Page not found" in driver.title or "404" in driver.title or len(driver.find_elements(By.CSS_SELECTOR, ".error-container")) > 0:
        logger.warning(f"Company page for '{slug}' not found. Searching on LinkedIn...")
        search_url = f"https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(' ', '%20')}"
        try:
            driver.get(search_url)
            time.sleep(4)
            first_result = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".entity-result__title-text a"))
            )
            company_url = first_result.get_attribute("href")
            logger.info(f"Found company page via search: {company_url}")
            driver.get(company_url)
            time.sleep(4)
        except Exception as e:
            logger.error(f"Failed to find company page: {e}")
            return None

    # Try extracting the search link from the company page
    search_url = None
    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        try:
            href = link.get_attribute("href") or ""
            if "/search/results/people/" in href:
                search_url = href
                if "network" in href or "Network" in href:
                    break
        except Exception:
            continue

    if search_url:
        logger.info(f"Discovered employees search URL: {search_url}")
        if "network" not in search_url.lower() and "facetnetwork" not in search_url.lower():
            if "?" in search_url:
                search_url += "&network=%5B%22F%22%5D"
            else:
                search_url += "?network=%5B%22F%22%5D"
        return search_url

    # Second fallback: navigate to people tab directly
    people_url = driver.current_url.rstrip("/") + "/people/"
    logger.info(f"Navigating directly to people tab: {people_url}")
    try:
        driver.get(people_url)
        time.sleep(4)
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                href = link.get_attribute("href") or ""
                if "/search/results/people/" in href:
                    search_url = href
                    if "network" in href or "Network" in href:
                        break
            except Exception:
                continue
    except Exception:
        pass

    if search_url:
        if "network" not in search_url.lower() and "facetnetwork" not in search_url.lower():
            search_url += "&network=%5B%22F%22%5D"
        return search_url

    return None


def scrape_connections_from_search(driver, max_people=5):
    """Scrapes connection details from the search results page."""
    people_connected = []
    try:
        for _ in range(2):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

        people_cards = driver.find_elements(By.XPATH, "//div[@role='listitem']")
        for card in people_cards:
            if len(people_connected) >= max_people:
                break
            try:
                profile_url = ""
                try:
                    profile_link = card.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                    profile_url = profile_link.get_attribute("href")
                    if "?" in profile_url:
                        profile_url = profile_url.split("?")[0]
                except Exception:
                    continue

                if not profile_url:
                    continue

                name = ""
                name_selectors = [
                    ".entity-result__title-text span[aria-hidden='true']",
                    ".entity-result__title-text a",
                    ".entity-result__title-text",
                    "span.entity-result__title-line",
                    "a[href*='/in/']"
                ]
                for sel in name_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, sel)
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

                # Fallback 1: Use the profile link's own text
                if not name:
                    try:
                        val = profile_link.text.strip()
                        if val:
                            if "\n" in val:
                                val = val.split("\n")[0].strip()
                            if "•" in val:
                                val = val.split("•")[0].strip()
                            name = val
                    except Exception:
                        pass

                # Fallback 2: Parse from profile URL slug
                if not name:
                    try:
                        slug = profile_url.rstrip("/").split("/in/")[-1].split("?")[0]
                        parts = slug.split("-")
                        if parts and parts[-1].isdigit() and len(parts[-1]) >= 4:
                            parts = parts[:-1]
                        name = " ".join(parts).title()
                    except Exception:
                        name = "LinkedIn Member"

                role = ""
                role_selectors = [
                    ".entity-result__primary-subtitle",
                    ".entity-result__badge-container + div",
                    "div[class*='subtitle']",
                    ".entity-result__summary"
                ]
                for sel in role_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, sel)
                        val = el.text.strip()
                        if val:
                            role = val
                            break
                    except Exception:
                        continue

                if not role:
                    role = "Employee"

                people_connected.append({
                    'name': name,
                    'designation': role,
                    'profile_url': profile_url
                })
            except Exception as e:
                logger.warning(f"Error parsing connection card: {e}")
        return people_connected
    except Exception as e:
        logger.error(f"Error during card scraping: {e}")
        return []


def open_messaging_from_profile(driver, name=None):
    """Finds and clicks the Message button on the connection's profile page, or focuses if already open."""
    if name:
        logger.info(f"Checking if chat window for '{name}' is already open...")
        try:
            status = driver.execute_script("""
                const nameToFind = arguments[0].toLowerCase();
                const nameParts = nameToFind.split(/\\s+/).filter(Boolean);
                
                const findAndExpand = (root) => {
                    if (!root) return null;
                    const headers = root.querySelectorAll('.msg-overlay-bubble-header, [class*="bubble-header"]');
                    for (const header of headers) {
                        const text = (header.innerText || '').toLowerCase();
                        const matches = nameParts.every(part => text.includes(part)) || text.includes(nameToFind);
                        if (matches) {
                            const bubble = header.closest('.msg-overlay-conversation-bubble, [class*="conversation-bubble"]');
                            if (bubble) {
                                const isMinimized = bubble.classList.contains('msg-overlay-board--minimized') || 
                                                   bubble.getAttribute('aria-expanded') === 'false' ||
                                                   bubble.clientHeight < 100;
                                if (isMinimized) {
                                    header.click();
                                    header.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                                    return "expanded_now";
                                } else {
                                    return "already_expanded";
                                }
                            } else {
                                if (header.clientHeight > 0) {
                                    return "already_expanded";
                                }
                            }
                        }
                    }
                    return null;
                };
                
                let res = findAndExpand(document);
                if (res) return res;
                
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    res = findAndExpand(host.shadowRoot);
                    if (res) return res;
                }
                return "not_found";
            """, name)
            
            if status == "already_expanded":
                logger.info(f"Chat window for {name} is already open and expanded. Skipping click.")
                return True
            elif status == "expanded_now":
                logger.info(f"Found minimized chat window for {name} and expanded it.")
                time.sleep(2)
                return True
            else:
                logger.info(f"No active chat window found for {name}. Will search for Message button.")
        except Exception as e:
            logger.warning(f"Error checking if chat window was already open: {e}")
            
    logger.info("Searching for Message button on profile page...")
    
    # Wait for the main content block to be present
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//main"))
        )
    except Exception:
        logger.warning("Timed out waiting for main content tag")
        time.sleep(3)
    
    message_selectors = [
        # Scoped to the top-card section inside main content
        "//main//section[contains(@class, 'top-card') or contains(@class, 'profile-card')]//button[contains(., 'Message') or contains(@aria-label, 'Message')]",
        "//main//section[contains(@class, 'top-card') or contains(@class, 'profile-card')]//a[contains(., 'Message') or contains(@aria-label, 'Message') or contains(@href, 'messaging/thread')]",
        
        # Scoped to the first section of main (which is always the top card)
        "//main//section[1]//button[contains(., 'Message') or contains(@aria-label, 'Message')]",
        "//main//section[1]//a[contains(., 'Message') or contains(@aria-label, 'Message') or contains(@href, 'messaging/thread')]",
        
        # Scoped generally to main tag (excludes sidebars/messaging drawers)
        "//main//button[contains(@aria-label, 'Message') or contains(@aria-label, 'message')]",
        "//main//button[contains(., 'Message') or contains(., 'message')]",
        "//main//a[contains(@href, '/messaging/thread/') or contains(@href, 'messaging/thread')]",
        "//main//a[contains(@aria-label, 'Message') or contains(@aria-label, 'message')]",
        "//main//a[contains(., 'Message') or contains(., 'message')]",
        
        # Original general fallbacks
        "button.pvs-profile-actions__action[aria-label*='Message']",
        "//button[contains(@class, 'pvs-profile-actions__action')][span[text()='Message']]",
        "//button[contains(., 'Message') and not(contains(@aria-label, 'Premium'))]"
    ]
    
    # Try finding and clicking
    for sel in message_selectors:
        try:
            if sel.startswith("//"):
                btn = driver.find_element(By.XPATH, sel)
            else:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                
            if btn:
                logger.info(f"Found Message button candidate with selector: {sel}")
                
                # Scroll into view
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(1)
                
                # Try standard click
                try:
                    btn.click()
                    logger.info("Clicked Message button successfully via standard click.")
                    time.sleep(3)
                    return True
                except Exception as click_err:
                    logger.info(f"Standard click failed: {click_err}. Trying JS click...")
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Clicked Message button successfully via JS click.")
                    time.sleep(3)
                    return True
        except Exception:
            continue
            
    # If we get here, no selectors worked. Log details to debug
    logger.warning("Message button not found. Dumping button and link elements to help debug...")
    try:
        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"Total buttons found on page: {len(all_buttons)}")
        for b in all_buttons:
            try:
                text = (b.text or "").strip()
                aria = (b.get_attribute("aria-label") or "").strip()
                classes = (b.get_attribute("class") or "").strip()
                if text or aria:
                    logger.info(f"  [BUTTON] Text: '{text}' | Aria-label: '{aria}' | Class: '{classes}'")
            except Exception:
                pass
                
        all_links = driver.find_elements(By.TAG_NAME, "a")
        logger.info(f"Total links found on page: {len(all_links)}")
        for l in all_links:
            try:
                text = (l.text or "").strip()
                aria = (l.get_attribute("aria-label") or "").strip()
                href = (l.get_attribute("href") or "").strip()
                classes = (l.get_attribute("class") or "").strip()
                if "message" in text.lower() or "message" in aria.lower() or "messaging" in href.lower() or "thread" in href.lower():
                    logger.info(f"  [LINK] Text: '{text}' | Aria-label: '{aria}' | Href: '{href}' | Class: '{classes}'")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to dump debug elements: {e}")
        
    return False


def insert_message_draft(driver, message):
    """Inserts the message into the overlay chat box and simulates space/backspace to validate draft."""
    try:
        editor = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                if (ed) return ed;
            }
            return document.querySelector('.msg-form__contenteditable');
        """)
        
        if not editor:
            logger.error("Message editor contenteditable not found")
            return False
            
        # Focus and click the editor to prepare it
        driver.execute_script("""
            const editor = arguments[0];
            editor.focus();
            editor.click();
        """, editor)
        time.sleep(0.5)
        
        # Clear existing text and paste the new message using execCommand
        driver.execute_script("""
            const editor = arguments[0];
            const text = arguments[1];
            
            // Clear existing text by selecting all (prevents breaking Draft.js DOM nodes)
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
            
            // Dispatch standard input change events
            ['input', 'change', 'keydown', 'keyup', 'keypress'].forEach(eventType => {
                const event = new Event(eventType, { bubbles: true, cancelable: true });
                editor.dispatchEvent(event);
            });
            
            // Dispatch explicit InputEvent
            const inputEvent = new InputEvent('input', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: text
            });
            editor.dispatchEvent(inputEvent);
        """, editor, message)
        time.sleep(1)
        
        # Simulating space and backspace natively via Selenium keys to update Draft.js state
        try:
            editor.send_keys(" ")
            time.sleep(0.5)
            editor.send_keys(Keys.BACKSPACE)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to send native space/backspace: {e}")
            
        editor_text = driver.execute_script("return arguments[0].innerText || arguments[0].textContent;", editor)
        logger.info(f"Draft text in editor is now: '{editor_text[:60].strip()}...'")
        return True
    except Exception as e:
        logger.error(f"Failed to insert message draft: {e}")
        return False


def click_send_message(driver):
    """Finds, enables, and clicks the send button."""
    try:
        editor = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                if (ed) return ed;
            }
            return document.querySelector('.msg-form__contenteditable');
        """)
        
        send_button = driver.execute_script("""
            const editor = arguments[0];
            let btn = null;
            if (editor) {
                const form = editor.closest('form') || editor.closest('.msg-convo-wrapper') || editor.closest('.msg-form__container');
                if (form) {
                    btn = form.querySelector('.msg-form__send-button');
                }
            }
            if (!btn) {
                const host = document.querySelector('#interop-outlet');
                if (host && host.shadowRoot) {
                    btn = host.shadowRoot.querySelector('.msg-form__send-button');
                }
            }
            if (!btn) {
                btn = document.querySelector('.msg-form__send-button');
            }
            if (btn) {
                btn.removeAttribute('disabled');
                btn.disabled = false;
            }
            return btn;
        """, editor)
        
        if not send_button:
            logger.error("Send button not found")
            return False
            
        logger.info("Clicking the Send button...")
        try:
            if send_button.is_displayed() and send_button.is_enabled():
                send_button.click()
                logger.info("Clicked Send button via native Selenium click.")
                time.sleep(3)
                return True
        except Exception as sel_err:
            logger.debug(f"Native Selenium click failed: {sel_err}. Trying JavaScript click...")
            
        driver.execute_script("arguments[0].click();", send_button)
        logger.info("Clicked Send button via JavaScript click.")
        time.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Failed to click send button: {e}")
        return False


def upload_resume_attachment(driver, profile):
    """Locates the file input element in the chat overlay and uploads the local resume PDF."""
    try:
        resume_path = get_resume_file_path(profile)
        if not resume_path or not os.path.exists(resume_path):
            logger.warning(f"Local resume file not found at path: {resume_path}. Skipping file upload.")
            return False
            
        logger.info(f"Attempting to upload local resume: {resume_path}")
        
        # Locate the file input element inside the active chat form
        file_input = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            let form = null;
            if (host && host.shadowRoot) {
                const ed = host.shadowRoot.querySelector('.msg-form__contenteditable');
                if (ed) form = ed.closest('form');
            }
            if (!form) {
                const ed = document.querySelector('.msg-form__contenteditable');
                if (ed) form = ed.closest('form') || ed.closest('.msg-convo-wrapper') || ed.closest('.msg-form__container');
            }
            if (form) {
                return form.querySelector('input[type="file"]');
            }
            return document.querySelector('.msg-form__footer input[type="file"]') || document.querySelector('input[type="file"].msg-form__attachment-input') || document.querySelector('input[type="file"]');
        """)
        
        if not file_input:
            logger.warning("LinkedIn chat file input element not found.")
            return False
            
        # Send the absolute path of the resume file to the file input
        file_input.send_keys(resume_path)
        logger.info("Resume file path sent to LinkedIn chat file input.")
        time.sleep(3) # Wait for upload to complete
        return True
    except Exception as e:
        logger.warning(f"Error uploading resume attachment: {e}")
        return False


def verify_delivery(driver, sent_text):
    """Verifies that the message appears in the chat thread history."""
    try:
        bubbles = driver.execute_script("""
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                return Array.from(host.shadowRoot.querySelectorAll('.msg-s-event-listitem__body, .msg-thread__message-text')).map(el => el.innerText);
            }
            return Array.from(document.querySelectorAll('.msg-s-event-listitem__body, .msg-thread__message-text')).map(el => el.innerText);
        """)
        if not bubbles:
            logger.warning("No message bubbles found to verify.")
            return False
            
        last_messages = bubbles[-3:]
        short_sent = sent_text[:50].strip().lower()
        for msg in last_messages:
            if msg and short_sent in msg.lower():
                logger.info("Delivery verified! Sent message matches chat history.")
                return True
        logger.warning(f"No message matching draft found. Scraped bubbles: {bubbles}")
        return False
    except Exception as e:
        logger.warning(f"Error verifying delivery: {e}")
        return False


def close_chat_window(driver):
    """Closes the overlay chat window."""
    try:
        # Find and click all possible close buttons for chat overlay windows using robust recursive logic and MouseEvent dispatching
        clicked = driver.execute_script("""
            let count = 0;
            const clickElement = (btn) => {
                if (!btn) return;
                try {
                    btn.click();
                } catch(e) {}
                try {
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                } catch(e) {}
                count++;
            };
            
            const closeAllInRoot = (root) => {
                if (!root) return;
                const headers = root.querySelectorAll('.msg-overlay-bubble-header, header, [class*="bubble-header"]');
                headers.forEach(header => {
                    const buttons = header.querySelectorAll('button');
                    buttons.forEach(btn => {
                        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const btnClass = (btn.className || '').toLowerCase();
                        const innerText = (btn.innerText || '').toLowerCase();
                        const id = (btn.id || '').toLowerCase();
                        
                        let shouldClick = ariaLabel.includes('close') || ariaLabel.includes('dismiss') || ariaLabel.includes('cancel') ||
                                          btnClass.includes('close') || btnClass.includes('dismiss') || btnClass.includes('cancel') ||
                                          id.includes('close') || id.includes('dismiss') || id.includes('cancel') ||
                                          innerText.includes('close') || ariaLabel.includes('conversation');
                                          
                        if (!shouldClick) {
                            const svg = btn.querySelector('svg');
                            if (svg) {
                                const svgClass = (svg.getAttribute('class') || '').toLowerCase();
                                const svgType = (svg.getAttribute('type') || '').toLowerCase();
                                const svgData = (svg.getAttribute('data-type') || '').toLowerCase();
                                const svgTestIcon = (svg.getAttribute('data-test-icon') || '').toLowerCase();
                                
                                let useClose = false;
                                const useEl = svg.querySelector('use');
                                if (useEl) {
                                    const useHref = (useEl.getAttribute('href') || useEl.getAttribute('xlink:href') || '').toLowerCase();
                                    if (useHref.includes('close') || useHref.includes('cancel') || useHref.includes('dismiss')) {
                                        useClose = true;
                                    }
                                }
                                
                                if (svgClass.includes('close') || svgType.includes('close') || svgData.includes('close') || svgTestIcon.includes('close') || useClose ||
                                    svgClass.includes('cancel') || svgType.includes('cancel') || svgTestIcon.includes('cancel') ||
                                    svgClass.includes('x') || svgType.includes('x') || svgTestIcon.includes('x') ||
                                    svgClass.includes('dismiss') || svgType.includes('dismiss') || svgTestIcon.includes('dismiss')) {
                                    shouldClick = true;
                                }
                            }
                        }
                        
                        if (shouldClick) {
                            clickElement(btn);
                        }
                    });
                });
            };
            
            // 1. Close in main document
            closeAllInRoot(document);
            
            // 2. Close in shadow DOM
            const host = document.querySelector('#interop-outlet');
            if (host && host.shadowRoot) {
                closeAllInRoot(host.shadowRoot);
            }
            return count;
        """)
        time.sleep(1)
        if clicked and clicked > 0:
            logger.info(f"Closed {clicked} chat window overlay(s).")
            return True
        else:
            # Fallback: click direct close elements
            clicked_fallback = driver.execute_script("""
                const els = document.querySelectorAll('.msg-overlay-bubble-header__control--close, button[aria-label*="Close conversation"], [data-control-name="close_comparison"]');
                els.forEach(el => {
                    try { el.click(); } catch(e) {}
                    try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); } catch(e) {}
                });
                return els.length;
            """)
            if clicked_fallback > 0:
                logger.info(f"Closed {clicked_fallback} chat window overlays using fallback.")
                return True
    except Exception as e:
        logger.warning(f"Could not close chat window: {e}")
    return False


def run_phase_one_discovery():
    """Phase 1: Discover connected 1st-degree employees at target companies."""
    logger.info("=" * 60)
    logger.info("Phase 1: Discovering Connected Employees...")
    logger.info("=" * 60)
    
    user_conf = get_selected_user_config()
    global_conf = get_global_settings()
    connect_conf = user_conf.get("linkedin_connect", {})
    max_referrals = int(connect_conf.get("max_connections_per_run") or 5)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    
    job_data = load_jobs_for_referral(status_filter='Interested')
    if not job_data:
        logger.info("No jobs with status 'Interested' found. Nothing to discover.")
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

        for job in job_data:
            company = job.get('CompanyName') or ''
            job_id = job.get('JobID') or ''
            
            logger.info(f"\nProcessing company: {company} (JobID {job_id})")
            search_url = find_company_employees_search_url(driver, company)
            if not search_url:
                logger.warning(f"Could not find employees search link for: {company}")
                continue
                
            driver.get(search_url)
            time.sleep(4)
            
            connections = scrape_connections_from_search(driver, max_people=max_referrals)
            if not connections:
                logger.info(f"No 1st-degree connections found at {company}.")
                continue
                
            discovered_count = 0
            for conn in connections:
                profile_url = conn['profile_url']
                
                # Check eligibility
                if is_profile_already_contacted(profile_url):
                    logger.info(f"Connection {conn['name']} already messaged or skipped. Skipping.")
                    continue
                    
                referral_data = {
                    'JobID': job_id,
                    'CompanyName': company,
                    'Referral_Person_Name': conn['name'],
                    'Referral_Person_Email': '',
                    'Referral_Person_Profile_URL': profile_url,
                    'Referral_Person_Designation': conn['designation'],
                    'Referral_Source': 'Existing Connection',
                    'Referral_Status': 'Pending'
                }
                
                add_or_update_referral(referral_data)
                discovered_count += 1
                logger.info(f"Discovered: {conn['name']} ({conn['designation']}) - Pending outreach")
                
            logger.info(f"Found and stored {discovered_count} new 1st-degree connection contacts for {company}.")
            time.sleep(2)
            
    except Exception as e:
        logger.error(f"Fatal error in connection discovery: {e}")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()


def prompt_referral_action(recipient_name, review_mode=True):
    if not review_mode:
        return "send"

    print("\n" + "="*50)
    print("INVITE QUALITY GATE - REFERRAL MESSAGE REVIEW")
    print("="*50)
    print(f"Recipient: {recipient_name}")
    print("-" * 50)
    print("Please review the message draft in the LinkedIn chat window.")
    print("="*50)
    print("Send [S] / Skip [K] / Quit [Q]")
    
    choice = input().strip().lower()
    while choice not in ('s', 'k', 'q'):
        print("Invalid option. Please enter Send [S], Skip [K], or Quit [Q]:")
        choice = input().strip().lower()
        
    if choice == 'k':
        return "skip"
    elif choice == 'q':
        return "quit"
    else:
        return "send"


def run_phase_two_messaging():
    """Phase 2-5: Message pending connections and verify delivery."""
    logger.info("=" * 60)
    logger.info("Phase 2-5: Sending Referral Messages...")
    logger.info("=" * 60)
    
    user_conf = get_selected_user_config()
    profile = user_conf.get("profile", {})
    global_conf = get_global_settings()
    connect_conf = user_conf.get("linkedin_connect", {})
    review_mode = connect_conf.get("review_mode", True)
    interval = int(connect_conf.get("interval") or 5)
    max_referrals = int(connect_conf.get("max_connections_per_run") or 5)
    
    email = global_conf.get("linkedin_email")
    password = global_conf.get("linkedin_password")
    
    all_referrals = load_all_referrals()
    pending = [
        r for r in all_referrals
        if str(r.get('Referral_Status')).strip().lower() == 'pending'
        and not str(r.get('Referral_Source') or '').strip().startswith('Recruiter')
    ]
    
    if not pending:
        logger.info("No pending connections found for outreach.")
        return
        
    logger.info(f"Found {len(pending)} pending connection messages to process.")
    
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

        # Close any chat overlays restored by LinkedIn session state on start
        logger.info("Performing initial post-login chat window cleanup...")
        close_chat_window(driver)

        # Load job metadata to resolve job titles and URLs
        job_data = load_jobs_for_referral(status_filter='Interested')
        job_titles = {str(j.get('JobID')): (j.get('JobTitle') or j.get('SearchKeyword')) for j in job_data}
        job_urls = {str(j.get('JobID')): (j.get('ShortenURL') or j.get('CompanyURL') or '') for j in job_data}

        for idx, ref in enumerate(pending):
            if sent_count >= max_referrals:
                logger.info(f"Max referrals limit of {max_referrals} reached. Stopping.")
                break
                
            ref_id = ref.get('ReferralID')
            job_id = str(ref.get('JobID'))
            company = ref.get('CompanyName')
            name = ref.get('Referral_Person_Name')
            profile_url = ref.get('Referral_Person_Profile_URL')
            designation = ref.get('Referral_Person_Designation')
            target_role = job_titles.get(job_id) or "DBA"
            job_url = job_urls.get(job_id) or ""
            
            logger.info("\n" + "=" * 60)
            logger.info(f"Processing referral message to {name} ({company})")
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
                
            message_text = get_referral_message(
                company=company,
                target_role=target_role,
                person_name=name,
                employee_designation=designation,
                job_url=job_url
            )
            
            if len(message_text) > 500:
                logger.warning("Message exceeds 500 characters. Truncating.")
                message_text = message_text[:497] + "..."
                
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
                logger.info(f"Skipped referral outreach to {name} by user.")
                ref['Referral_Status'] = 'Skipped'
                add_or_update_referral(ref)
                close_chat_window(driver)
                continue
            elif action == "quit":
                logger.info("Quitting referral outreach pipeline as requested.")
                close_chat_window(driver)
                break
                
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
            
            logger.info(f"Referrals sent: {sent_count}/{max_referrals}")
            if idx < len(pending) - 1 and sent_count < max_referrals:
                logger.info(f"Waiting for {interval} seconds before next outreach...")
                time.sleep(interval)

    except Exception as e:
        logger.error(f"Fatal error in connection outreach: {e}")
        sys.exit(1)
    finally:
        logger.info("Closing browser...")
        driver.quit()
