# Connectify – Automated LinkedIn Job Application & Outreach Hub

Connectify is a clean, modular Python and Selenium-based automation framework that automates the process of finding job postings, scraping recruiter/contact emails, sending referral request messages, and logging all applications in structured Excel sheets. It includes a user-friendly Flask-based web dashboard.

---

## 📁 Project Directory Layout

```
Connectify/
├── app.py                         # Web dashboard server (Flask)
│
├── config/                        # Dynamic profile & settings configuration
│   ├── settings.py                # Environment & directory mappings (.env loading)
│   ├── constants.py               # Central schema definitions and default keywords
│   ├── user_profiles.py           # Loads/saves profiles from users_config.json
│   └── email_templates.py         # Static fallback outreach templates
│
├── core/                          # Shared library & support package
│   ├── analytics/
│   │   └── metrics.py             # Dashboard statistics calculator
│   ├── storage/
│   │   └── database.py            # Unified openpyxl Excel read/write CRUD database
│   ├── integrations/
│   │   ├── selenium_driver.py     # Centralized Chrome WebDriver configurations
│   │   └── url_shortener.py       # TinyURL shortening service
│   ├── logging/
│   │   └── config.py              # Log setup mapping to logs/ folder
│   └── utils/
│       ├── string_utils.py        # Email address extraction regex
│       └── url_utils.py           # URL normalization, decoding, and parsing
│
├── pipelines/                     # Pipeline execution modules
│   ├── email_outreach/            # Pipeline 1: Email Scraper & Sender
│   │   ├── services/
│   │   │   ├── scraper.py         # Selenium post content email scraper
│   │   │   └── sender.py          # SMTP & Gmail Web automation senders
│   │   └── pipeline.py            # Phase 1 & 2 coordinator
│   │
│   └── linkedin_outreach/         # Pipeline 2: LinkedIn Job Search & Connect
│       ├── services/
│       │   ├── job_finder.py      # Scrapes external job postings
│       │   ├── reviewer.py        # Terminal CLI reviewer for new jobs
│       │   └── connector.py       # Connects and messages referral targets
│       └── pipeline.py            # Outreach step coordinator
│
├── data/                          # Spreadsheets and JSON tracking files
├── logs/                          # System log output files (*.log)
├── static/                        # CSS/JS dashboard assets
├── templates/                     # Flask dashboard view templates
├── resumes/                       # Uploaded applicant resumes
│
├── run_email_outreach.py          # Pipeline 1 runner
├── run_job_search.py              # Pipeline 2 runner: Find job opportunities
├── run_referral_review.py         # Pipeline 2 runner: CLI job evaluator
├── run_linkedin_connect.py        # Pipeline 2 runner: Outreach & messaging
└── run_url_shortener.py           # Utility runner to shorten job URLs
```

---

## 🚀 15-Minute Onboarding Guide

### Step 1: Install System Dependencies
Make sure you have [Google Chrome](https://www.google.com/chrome/) installed. (On MacOS, Chrome should be in your `/Applications` folder).

### Step 2: Set Up Virtual Environment & Packages
Open a terminal in the project directory and run:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`

# Install required packages
pip install -r requirements.txt
```
*Note: Pip will install Selenium, Flask, openpyxl, pandas, requests, python-dotenv, and webdriver-manager.*

### Step 3: Configure Settings
1. Copy the example configuration files:
   ```bash
   cp .env.example .env
   cp users_config.json.example users_config.json
   ```
2. Update the `.env` file with your LinkedIn login credentials:
   ```env
   LINKEDIN_EMAIL=your_email@gmail.com
   LINKEDIN_PASSWORD=your_secure_password
   ```
3. (Optional) Customize search terms and templates inside `users_config.json`.

---

## 🛠️ Running the Application

### Option A: Running the Web Dashboard (Recommended)
Launch the web interface locally:
```bash
python app.py
```
Open your browser and navigate to **`http://127.0.0.1:5001`**. From here, you can:
- Swap profile contexts (e.g. Yuvashree, Lalit).
- Upload resumes.
- Edit configurations dynamically.
- Monitor execution logs and launch scraping/outreach jobs in real time.

### Option B: Running Pipelines Individually via Terminal
You can run any pipeline or utility directly from the command line using the root wrapper scripts:

```bash
# Activate virtualenv first
source .venv/bin/activate

# 1. Run Email Scraper & Outreach Pipeline (Both phases)
python run_email_outreach.py --phase full

# 2. Run Job Search Automation
python run_job_search.py

# 3. Launch Terminal Reviewer (Flags new jobs as Interested/Skip)
python run_referral_review.py

# 4. Run TinyURL url shortener on gathered URLs
python run_url_shortener.py

# 5. Execute LinkedIn Connections & Referrals messaging outreach
python run_linkedin_connect.py
```

---

## ⚠️ Troubleshooting & Browser Tips

- **Mac Chrome Execution**: The driver is configured to automatically search for Google Chrome in the standard `/System/Volumes/Data/Volumes/Google Chrome/Google Chrome.app` path or default location.
- **Mac Excel Sheet Reloads**: The system uses AppleScript to reload active Excel/Numbers sheets automatically if they are open while data is writing. If prompted, grant terminal permission to script applications.
- **Google Sign-In**: Avoid choosing "Continue with Google" during automated sessions as Google security blocks automated login pages. Sign in directly using email and password.