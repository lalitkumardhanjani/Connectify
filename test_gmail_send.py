from linkedin_scraper import LinkedInScraper
from email_sender_gmail_web import send_email_via_gmail

TEST_RECIPIENT = "lk356003@gmail.com"

if __name__ == '__main__':
    scraper = LinkedInScraper()
    try:
        driver = scraper.driver
        success = send_email_via_gmail(driver, TEST_RECIPIENT)
        print('Send result:', success)
    finally:
        scraper.close()
