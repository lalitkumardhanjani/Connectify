import time
from selenium.webdriver.common.by import By
from linkedin_job_driver import wait_for_page
from linkedin_job_helpers import (
    extract_job_id,
    decode_apply_redirect,
    is_valid_external_url,
    normalize_external_url
)
from linkedin_job_scraper import find_external_apply_url
from linkedin_job_io import seen_external_urls, load_saved_jobs, save_job

def process_current_job(driver, job_data, seen_linkedin_urls, search_keyword):
    job_url = job_data.get("url")
    position = job_data.get("position", "").replace("(Verified job)", "").strip()

    if not job_url:
        print("Missing job detail URL, skipping")
        return False

    linkedin_key = extract_job_id(job_url) or job_url

    # avoid reprocessing the same LinkedIn job within this run
    if linkedin_key in seen_linkedin_urls:
        print("LinkedIn job already seen in this run. Skipping.")
        return False

    seen_linkedin_urls.add(linkedin_key)

    try:
        # open job detail in a new tab
        driver.execute_script("window.open(arguments[0], '_blank');", job_url)
        # wait for window handles to include the new tab
        for _ in range(10):
            handles = driver.window_handles
            if len(handles) > 1:
                break
            time.sleep(0.5)

        # switch to the newest tab
        try:
            driver.switch_to.window(driver.window_handles[-1])
        except Exception:
            # fallback: try to switch to last handle
            handles = driver.window_handles
            if handles:
                driver.switch_to.window(handles[-1])

        wait_for_page(4)

    except Exception as e:
        print(f"Unable to open job detail page: {str(e)}")
        try:
            driver.switch_to.window(driver.current_window_handle)
        except Exception:
            pass
        return False

    try:
        external_apply_url = find_external_apply_url(driver)

        if external_apply_url:
            external_apply_url = decode_apply_redirect(external_apply_url)

            if not is_valid_external_url(external_apply_url):
                print(f"Invalid external apply URL '{external_apply_url}' found, skipping")
                return False

            normalized_external_url = normalize_external_url(external_apply_url)
            if normalized_external_url in seen_external_urls:
                print("Already processed (memory cache)")
                return False

            jobs, existing_urls = load_saved_jobs()

            if normalized_external_url in existing_urls:
                print("Already exists in JSON")
                seen_external_urls.add(normalized_external_url)
                return False

            # Navigate to the external career portal to verify the job title
            print(f"Navigating to external portal to verify title: {external_apply_url}")
            try:
                driver.get(external_apply_url)
                time.sleep(5)  # Wait for page load and any redirects

                portal_title = (driver.title or "").lower()
                portal_h1s = []
                try:
                    h1_elements = driver.find_elements(By.TAG_NAME, "h1")
                    for el in h1_elements:
                        txt = el.text.strip().lower()
                        if txt:
                            portal_h1s.append(txt)
                except Exception:
                    pass

                print(f"Verified external portal: '{driver.title}'")

                # Check if portal page title contains DB2, Oracle, or Postgres keywords (case-insensitive)
                if portal_title and ("db2" in portal_title or "oracle" in portal_title or "postgres" in portal_title):
                    print(f"Company portal page title '{driver.title}' contains DB2, Oracle, or Postgres. Skipping.")
                    return False

            except Exception as e:
                print(f"Error loading external portal to verify title: {str(e)}")
                return False

            save_job({
                "url": external_apply_url,
                "company": job_data.get("company", "").strip(),
                "search_keyword": search_keyword
            })
            seen_external_urls.add(normalized_external_url)
            return True

        print("Skipping job because no external apply link was found")
        return False

    except Exception as e:
        print(f"Error processing job page: {str(e)}")
        return False

    finally:
        try:
            driver.close()
        except Exception:
            pass
        try:
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        except Exception:
            pass
