import os
import time
import platform
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config.user_profiles import get_selected_user_config, get_global_settings, substitute_template_variables, get_resume_file_path
from config.email_templates import DEFAULT_EMAIL_TEMPLATE
from core.logging.config import logger

def generate_email_draft():
    """Generate email subject and body dynamically using the active user configuration and templates."""
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}
        
    profile = user_conf.get("profile", {})
    email_scraper = user_conf.get("email_scraper", {})
    
    # Retrieve template from config
    raw_template = email_scraper.get("email_template")
    if not raw_template:
        raw_template = DEFAULT_EMAIL_TEMPLATE
        
    # Substitute variables
    body = substitute_template_variables(raw_template, profile)
    subject = "Referral Request – DBA Opportunity"
    
    return subject, body


def send_email_smtp(to_email, name, post_url):
    """Sends email via standard SMTP server."""
    subject, body = generate_email_draft()
    
    try:
        user_conf = get_selected_user_config()
        global_conf = get_global_settings()
    except Exception:
        user_conf = {}
        global_conf = {}
        
    email_scraper = user_conf.get("email_scraper", {})
    review_mode = email_scraper.get("review_mode", True)
    
    smtp_email = global_conf.get("smtp_email") or os.getenv("SMTP_EMAIL", "lk356003@gmail.com")
    smtp_password = global_conf.get("smtp_password") or os.getenv("SMTP_PASSWORD")
    smtp_server = global_conf.get("smtp_server") or os.getenv("SMTP_SERVER", "smtp.gmail.com")
    try:
        smtp_port = int(global_conf.get("smtp_port") or os.getenv("SMTP_PORT", 587))
    except ValueError:
        smtp_port = 587
    
    if review_mode:
        print("\n" + "="*50)
        print("REVIEW MODE - NEW EMAIL (SMTP)")
        print("="*50)
        print(f"To: {to_email} ({name})")
        print(f"Post Source: {post_url}")
        print("-" * 50)
        print(f"Subject: {subject}")
        print(body)
        print("="*50)
        
        choice = input("Send this email? (Y/N): ").strip().lower()
        if choice != 'y':
            logger.info(f"User skipped sending email to {to_email}.")
            return False

    if not smtp_email or not smtp_password:
        logger.error("SMTP credentials not configured. Cannot send email.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Successfully sent email to {to_email}.")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_email_via_gmail(driver, to_email, review_mode=None):
    """Send email via Gmail web interface using Selenium."""
    try:
        user_conf = get_selected_user_config()
    except Exception:
        user_conf = {}
        
    profile = user_conf.get("profile", {})
    email_scraper = user_conf.get("email_scraper", {})
    
    if review_mode is None:
        review_mode = email_scraper.get("review_mode", True)
    
    review_mode = bool(review_mode)
    resume_file_path = get_resume_file_path(profile)
    subject, body = generate_email_draft()

    def attach_resume(file_path):
        if not os.path.exists(file_path):
            logger.warning(f"Resume file not found: {file_path}")
            return False

        file_input = None
        try:
            file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
            if file_inputs:
                file_input = file_inputs[0]

            if not file_input:
                attach_selectors = [
                    "//div[@aria-label='Attach files']",
                    "//div[@data-tooltip='Attach files']",
                    "//div[contains(@aria-label, 'Attach files')]",
                    "//span[contains(@data-tooltip, 'Attach files')]",
                ]
                for sel in attach_selectors:
                    try:
                        attach_btn = driver.find_element(By.XPATH, sel)
                        driver.execute_script("arguments[0].click();", attach_btn)
                        time.sleep(1)
                        break
                    except Exception:
                        continue

                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                if file_inputs:
                    file_input = file_inputs[0]

            if not file_input:
                logger.warning("Could not find Gmail attach file input")
                return False

            driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;",
                file_input,
            )
            file_input.send_keys(file_path)

            filename = os.path.basename(file_path)
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{filename}') or contains(@aria-label, '{filename}') or contains(@title, '{filename}')]") ) )
            except TimeoutException:
                logger.warning("Attachment file name did not appear in Gmail UI; proceeding anyway")

            logger.info(f"Attached resume: {filename}")
            return True
        except Exception as e:
            logger.warning(f"Failed to attach resume: {e}")
            return False

    try:
        # Navigate to Gmail if not already there
        if "mail.google.com" not in driver.current_url:
            logger.info("Navigating to Gmail...")
            driver.get("https://mail.google.com/mail/u/0/")
            time.sleep(3)
        
        # Click "Compose" button
        compose_selectors = [
            ".aMvxe",
            "button[aria-label='Compose']",
            "div[gh='cm']",
            "div[role='button'][gh='cm']",
            "//div[text()='Compose' and @role='button']",
            ".rK7tdc",
            ".T-I.T-I-KE.L3"
        ]
        
        compose_btn = None
        for selector in compose_selectors:
            try:
                if selector.startswith("//") or selector.startswith(".//"):
                    compose_btn = driver.find_element(By.XPATH, selector)
                else:
                    compose_btn = driver.find_element(By.CSS_SELECTOR, selector)
                if compose_btn:
                    break
            except Exception:
                continue
        
        if compose_btn:
            try:
                driver.execute_script("arguments[0].click();", compose_btn)
            except Exception:
                try:
                    compose_btn.click()
                except Exception:
                    pass
            time.sleep(1.5)
        else:
            logger.warning("Could not find Gmail compose button")
            return False
        
        time.sleep(0.5)
        select_all_key = Keys.COMMAND if platform.system() == 'Darwin' else Keys.CONTROL

        def _get_field_text(field):
            try:
                value = field.get_attribute('value')
                if value:
                    return value.strip()
            except Exception:
                pass
            try:
                return driver.execute_script("return arguments[0].textContent || arguments[0].innerText || '';", field).strip()
            except Exception:
                return ''

        def _set_field_value(field, value):
            try:
                tag = field.tag_name.lower()
                if tag in ('input', 'textarea'):
                    driver.execute_script(
                        "var field = arguments[0]; field.focus(); field.value = arguments[1]; field.dispatchEvent(new Event('input', { bubbles: true })); field.dispatchEvent(new Event('change', { bubbles: true }));",
                        field,
                        value,
                    )
                else:
                    driver.execute_script(
                        "var field = arguments[0]; field.focus(); field.innerText = arguments[1]; field.textContent = arguments[1]; field.dispatchEvent(new Event('input', { bubbles: true })); field.dispatchEvent(new Event('change', { bubbles: true }));",
                        field,
                        value,
                    )
                time.sleep(0.5)
                return True
            except Exception as e:
                logger.warning(f"Failed to set field value via JS: {e}")
                return False

        def _safe_click(field):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field)
                time.sleep(0.5)
                field.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", field)
                except Exception as e:
                    logger.warning(f"Failed to click field: {e}")
                    raise
            time.sleep(1)

        to_field = None
        to_selectors = [
            "//textarea[@name='to']",
            "//textarea[contains(@aria-label,'To')]",
            "//input[@aria-label='To']",
            "//input[contains(@aria-label,'To')]",
            "//input[@name='to']",
            "//div[@role='combobox' and contains(@aria-label,'To')]",
            "//div[@role='textbox' and contains(@aria-label,'To')]",
            "//div[@contenteditable='true' and contains(@aria-label,'To')]",
            "//div[@role='textbox' and @aria-label='Recipients']",
        ]

        for xpath in to_selectors:
            try:
                to_field = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                logger.info(f"Found To field via xpath: {xpath}")
                break
            except TimeoutException:
                continue

        if to_field:
            try:
                _safe_click(to_field)

                if to_field.tag_name.lower() in ('input', 'textarea'):
                    try:
                        to_field.clear()
                    except Exception:
                        to_field.send_keys(select_all_key + 'a')
                        to_field.send_keys(Keys.DELETE)
                else:
                    _set_field_value(to_field, '')
                time.sleep(0.7)

                to_field.send_keys(to_email)
                time.sleep(1.0)
                to_field.send_keys(Keys.TAB)
                time.sleep(1.0)

                current_value = _get_field_text(to_field)
                if to_email not in current_value:
                    chips = driver.find_elements(By.XPATH, f"//span[@email='{to_email}']")
                    if not chips:
                        chips = driver.find_elements(By.XPATH, f"//span[contains(@email, '{to_email}')]" )
                    if not chips:
                        raise Exception(f"Recipient field did not retain text after typing; current='{current_value}'")

                logger.info(f"Successfully populated To field with {to_email}")
            except Exception as e:
                logger.warning(f"Failed to populate To field with send_keys: {e}")
                try:
                    if not _set_field_value(to_field, to_email):
                        raise Exception("JS value set failed")
                    time.sleep(0.8)
                    to_field.send_keys(Keys.TAB)
                    time.sleep(1.0)
                    logger.info(f"Successfully populated To field (JS) with {to_email}")
                except Exception as e2:
                    logger.warning(f"Failed to populate To field via JS: {e2}")
                    return False
        else:
            logger.warning("Could not find email recipient field after multiple attempts")
            return False
        
        # Enter subject
        time.sleep(0.3)
        subject_field = None
        
        try:
            subject_field = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Subject']"))
            )
            logger.info("Found Subject field via aria-label")
        except TimeoutException:
            pass
        
        if not subject_field:
            try:
                subject_field = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Subject')]")
                logger.info("Found Subject field via placeholder")
            except NoSuchElementException:
                pass
        
        if not subject_field:
            try:
                inputs = driver.find_elements(By.XPATH, "//input[@role='textbox']")
                if len(inputs) > 0:
                    subject_field = inputs[0]
                    logger.info("Found Subject field via role=textbox")
            except NoSuchElementException:
                pass
        
        if subject_field:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", subject_field)
                time.sleep(0.3)
                _safe_click(subject_field)
                time.sleep(0.3)
                subject_field.clear()
                time.sleep(0.2)
                subject_field.send_keys(subject)
                time.sleep(0.3)
                logger.info("Successfully populated Subject field")
            except Exception as e:
                logger.warning(f"Failed to populate subject field: {e}")
                try:
                    if not _set_field_value(subject_field, subject):
                        raise Exception("JS subject set failed")
                    time.sleep(0.3)
                    logger.info("Successfully populated Subject field via JS")
                except Exception as e2:
                    logger.warning(f"Failed to populate subject field via JS: {e2}")
                    return False
        else:
            logger.warning("Could not find subject field")
            return False
        
        # Enter email body
        time.sleep(0.3)
        body_field = None
        
        try:
            body_field = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//div[@aria-label='Message body']"))
            )
            logger.info("Found Body field via aria-label")
        except TimeoutException:
            pass
        
        if not body_field:
            try:
                body_field = driver.find_element(By.XPATH, "//div[@contenteditable='true' and @role='textbox']")
                logger.info("Found Body field via contenteditable")
            except NoSuchElementException:
                pass
        
        if not body_field:
            try:
                divs = driver.find_elements(By.XPATH, "//div[@contenteditable='true']")
                if len(divs) > 0:
                    body_field = divs[-1] if len(divs) > 1 else divs[0]
                    logger.info("Found Body field via contenteditable (multiple)")
            except NoSuchElementException:
                pass
        
        if body_field:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", body_field)
                time.sleep(0.2)
                body_field.click()
                time.sleep(0.3)
                body_field.send_keys(body)
                time.sleep(0.5)
                logger.info("Successfully populated Body field")
            except Exception as e:
                logger.warning(f"Failed to populate body field via send_keys: {e}")
                try:
                    driver.execute_script("""
                        var field = arguments[0];
                        field.innerText = arguments[1];
                        field.textContent = arguments[1];
                        field.dispatchEvent(new Event('input', { bubbles: true }));
                        field.dispatchEvent(new Event('change', { bubbles: true }));
                    """, body_field, body)
                    time.sleep(0.5)
                    logger.info("Successfully populated Body field (JS)")
                except Exception as e2:
                    logger.warning(f"Failed to populate body field via JS: {e2}")
                    return False
        else:
            logger.warning("Could not find body field")
            return False

        # Attach resume
        time.sleep(0.5)
        if not attach_resume(resume_file_path):
            logger.warning("Failed to attach resume. Aborting send.")
            return False

        # Confirm before sending
        if review_mode:
            print("\n" + "="*50)
            print("REVIEW MODE - COMPOSED EMAIL (in Gmail)")
            print("="*50)
            print(f"To: {to_email}")
            print("-" * 50)
            print(f"Subject: {subject}")
            print(body)
            print("="*50)
            choice = input("Send this email now? (Y/N): ").strip().lower()
        else:
            logger.info("Review mode disabled – automatically sending email.")
            choice = 'y'
            
        if choice != 'y':
            logger.info(f"User skipped sending email to {to_email}.")
            return False
        
        # Click Send button
        time.sleep(0.5)
        send_btn = None
        
        send_xpaths = [
            "//div[@aria-label='Send']",
            "//button[@aria-label='Send ']",
            "//button[contains(@aria-label, 'Send')]",
            "//div[@role='button' and contains(@aria-label, 'Send')]",
            "//div[contains(text(), 'Send') and @role='button']",
            "//button[@data-tooltip='Send [Tab]']",
            "//div[@data-tooltip='Send [Tab]']"
        ]
        
        for xpath in send_xpaths:
            try:
                send_btn = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                if send_btn:
                    logger.info(f"Found Send button via xpath: {xpath}")
                    break
            except TimeoutException:
                continue
        
        if not send_btn:
            css_selectors = [
                "[aria-label='Send']",
                "button[aria-label*='Send']",
                ".T-I.J-J5-Ji.aoO.T-I-atl.L3",
                ".T-I.T-I-KE.L3"
            ]
            for selector in css_selectors:
                try:
                    send_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if send_btn:
                        logger.info(f"Found Send button via CSS: {selector}")
                        break
                except NoSuchElementException:
                    continue
        
        if send_btn:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", send_btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", send_btn)
                time.sleep(5)
                logger.info(f"Successfully sent email to {to_email} via Gmail web interface.")
                return True
            except Exception as e:
                logger.warning(f"Failed to click Send button: {e}")
                try:
                    send_btn.click()
                    time.sleep(5)
                    logger.info(f"Successfully sent email to {to_email} (via direct click).")
                    return True
                except Exception as e2:
                    logger.warning(f"Failed to click Send button (direct): {e2}")
                    return False
        else:
            logger.warning("Could not find Gmail send button after multiple attempts")
            return False
    
    except Exception as e:
        logger.error(f"Failed to send email via Gmail web interface to {to_email}: {e}")
        return False
