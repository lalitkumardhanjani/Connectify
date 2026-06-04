import os
import time

# Import the new shorten_url function from shorten_urls.py
from shorten_urls import shorten_url

# SHORTENER_SERVICE_URL and CHROME_PROFILE_DIR are now handled by shorten_urls.py
# The shorten_url function is now imported, so this local definition is removed.
# def shorten_url(driver, long_url):
#     """Shortens a given URL using shorturl.at via Selenium."""
#     # ... (rest of the Selenium code) ...

def run_single_test():
    test_url = "https://career.infosys.com/jobdesc?jobReferenceCode=INFSYS-EXTERNAL-246242&sourceId=4003"
    
    try:
        print(f"--- Attempting to shorten URL: {test_url} ---")
        shortened = shorten_url(test_url) # Call the imported function
        
        if shortened:
            print(f"\nTEST RESULT: PASSED")
            print(f"  Original URL: {test_url}")
            print(f"  Shortened URL: {shortened}")
        else:
            print(f"\nTEST RESULT: FAILED")
            print(f"  Could not shorten URL: {test_url}")
            
    finally:
        print("Test finished.")

if __name__ == "__main__":
    run_single_test()