# Connectify – Technical Architecture Documentation

This document describes the codebase architecture, design choices, data flow models, and extension guidelines for **Connectify**.

---

## 🏗️ Core Architecture Overview

Connectify follows clean architectural principles by separating cross-cutting configurations, common infrastructure utilities, data storage layers, and execution pipelines.

```
+-------------------------------------------------------------+
|                     Flask Web App (app.py)                  |
+------------------------------+------------------------------+
                               | launches
                               v
+-------------------------------------------------------------+
|                  Runner Scripts (run_*.py)                  |
+------------------------------+------------------------------+
                               | calls
                               v
+-------------------------------------------------------------+
|                     Pipelines Package                       |
|  - email_outreach/           - linkedin_outreach/            |
|    - scraper.py                 - job_finder.py              |
|    - sender.py                  - reviewer.py                |
|    - pipeline.py                - connector.py               |
+------------------------------+------------------------------+
                               | uses
                               v
+-------------------------------------------------------------+
|                       Core package                          |
|  - storage/database.py       - integrations/selenium_driver |
|  - analytics/metrics.py      - utils/url_utils & string_    |
+------------------------------+------------------------------+
                               | configures
                               v
+-------------------------------------------------------------+
|                     Configuration package                   |
|  - settings.py   - constants.py   - user_profiles.py        |
+-------------------------------------------------------------+
```

---

## 🛠️ Module Breakdowns

### 1. Configuration Package (`config/`)
Centralizes all settings parameters, user profile sandboxes, and handles active user contexts.
- **`settings.py`**: Resolves sandbox pathways dynamically at call time based on the active profile, ensuring setting folders (`users/<username>/data/`, `users/<username>/logs/`, `users/<username>/resumes/`) exist and are dynamically isolated. Implements PEP 562 `__getattr__` module hooks for backward-compatible lookups.
- **`constants.py`**: Keeps static database schemas, Excel column header orders, and standard search keywords.
- **`user_profiles.py`**: Interacts with individual user configuration files (`users/<username>/config.json`) and active user state (`users/active_user.json`). Handles dynamic loading, dictionary rebuilding in memory, and legacy file migrations.
- **`email_templates.py`**: Holds default message fallbacks.

### 2. Core Library Package (`core/`)
Abstracts shared utility layers so pipelines remain focused solely on execution flows.
- **`storage/database.py`**: Coordinates openpyxl and JSON file reads/writes under the active user's sandboxed `data/` directory (`users/<username>/data/`). Automatically handles duplicate checks, incrementing primary IDs, and triggers sheet reloads on macOS using AppleScript.
- **`integrations/selenium_driver.py`**: Consolidates browser profile setups. Sets remote debugging ports, maximizes windows, configures Darwin application binaries, and dynamically isolates Chrome profiles under `users/<username>/chrome-profile/`.
- **`integrations/url_shortener.py`**: Connects to TinyURL API GET endpoints to shorten company URLs.
- **`logging/config.py`**: Implements `DynamicUserFileHandler` to route log lines into the active user's log folder dynamically at record write-time.
- **`utils/`**: Split into `string_utils.py` (regex expressions for email parsing) and `url_utils.py` (handles URL normalization, decoding safety redirects, and parsing job IDs).
- **`analytics/metrics.py`**: Processes sandboxed Excel/JSON tracking files into standard dashboard stats.

### 3. Pipelines Package (`pipelines/`)
Dedicated workflows that implement browser manipulation and scraper logic.

#### Email Scraper & Outreach (`pipelines/email_outreach/`)
Scrapes emails from posts and sends outreach emails.
- **`services/scraper.py`**: Navigates to LinkedIn content boards, searches keywords, expands posts, extracts text, finds email addresses, and saves them to `data/job_tracker.xlsx`.
- **`services/sender.py`**: Formulates messages based on dynamic configurations and sends emails using SMTP or Selenium Gmail browser automation.
- **`pipeline.py`**: Standard orchestrator combining scraper (Phase 1) and sender (Phase 2) workflows.

#### Job Search & Connect (`pipelines/linkedin_outreach/`)
Finds job listings and sends connection/direct message requests.
- **`services/job_finder.py`**: Scrapes job listings, checks for duplicate postings in `data/LinkedIn_Job_Tracker.xlsx`, and opens external apply links to cache actual settled career URLs.
- **`services/reviewer.py`**: Terminal CLI prompt allowing users to choose whether to request referrals for a listed company or mark it as skipped.
- **`services/connector.py`**: Leverages Selenium to search for people working at target companies, and sends connection invites (with personalized notes) or direct messages (to 1st degree connections).
- **`pipeline.py`**: Step coordinator interface.

---

## 🔄 Pipeline Data Flow Models

### 1. Email Scraper Pipeline Data Flow
```
[LinkedIn Content Boards] --(Selenium Scrapes Text)--> [Scraped Content]
                                                               |
                                                     (extracts via regex)
                                                               v
                                                       [Email Addresses]
                                                               |
                                                         (database check)
                                                               v
[SMTP Server / Gmail UI] <--(Send Mail Compose)-- [users/<user>/data/job_tracker.xlsx]
```

### 2. LinkedIn Job & Connect Pipeline Data Flow
```
[LinkedIn Search Jobs] --(Discovers Job Card)--> [External Apply Button]
                                                               |
                                                       (decodes redirect)
                                                               v
[Review Option (CLI)] <--(Presents NEW Job)-- [users/<user>/data/LinkedIn_Job_Tracker.xlsx]
          |
     (Sets status)
          v
[Ask For Referral] --(TinyURL shortens links)--> [ShortenURL column updated]
                                                               |
                                                     (Selenium Search People)
                                                               v
[Send Connection / Note] --(Status marked Done/Sent)--> [Status column updated]
```

---

## 🖥️ Dashboard Database Tabs

### Outreach Leads (Email Scraper Database)
- Displays emails scraped from LinkedIn posts sorted by **ID ascending** (incremental).
- Paginated view: **10 records per page** with dynamic ellipsis page controls.
- Supports per-column filtering on ID, Email, Status, Keyword, and Timestamp.
- In-place status update and record deletion from the UI.
- Edit dialog for correcting email, status, or keyword inline.

### Referral Opportunities (LinkedIn Job Tracker)
- Displays job opportunities tracked for LinkedIn referral outreach, sorted by **ID ascending** (incremental).
- Paginated view: **10 records per page** with dynamic ellipsis page controls.
- Supports full-text search, status-based filtering, and date recency filters.
- In-place status dropdown selector and delete action per row.

---

## ⚙️ Dashboard Settings Tabs

### Outreach Engine (Email Scraper Settings)
- **Search Execution Frequency**: Controls how frequently the scraper paginates LinkedIn feeds between post reads.
- **Outreach Quality Gate**: When enabled, emails are held in the database for manual review before sending. When disabled, outreach is sent automatically after scraping.
- **Target Post Keywords**: Tag-based keyword manager. Add or remove terms searched on LinkedIn content boards.
- **Outreach Email Template Studio**: Rich text editor with clickable variable tokens (`{FIRST_NAME}`, `{EXPERIENCE}`, etc.) and a **Real-time Preview** mode that renders your template inside a mock email window.

### LinkedIn Automator (LinkedIn Connect Settings)
- **Action Timing Delay**: Controls wait time between LinkedIn browser automation steps.
- **Invite Quality Gate**: When enabled, connection requests are staged in the Referral Opportunities database for review before being sent. When disabled, requests are sent automatically.
- **Target Network Keywords**: Tag-based keyword manager. Add or remove terms used for LinkedIn people search during connection routines.
- **LinkedIn Invite Note Studio**: Rich text editor with clickable variable tokens and character counter (300-char LinkedIn limit enforced). **Real-time Preview** renders your note inside a mock LinkedIn invitation modal.

---

## 🚀 Guidelines for Adding New Features

### Adding a new Configuration Variable
1. If the setting is system-wide, add it to `config/settings.py` (if it loads from environment variables) or `config/constants.py` (if it is a static configuration constant).
2. If it is user-specific, add it to the default user profile initializer dictionary inside `create_user_profile()` in `app.py` and the fallback dictionary inside `load_all_configs()` in `config/user_profiles.py`. This ensures that new user profiles created via the dashboard will inherit the parameter inside their isolated `config.json`.

### Adding a new Outreach Pipeline
1. Create a subfolder under `pipelines/` (e.g., `pipelines/new_platform_outreach/`).
2. Implement your browser scraper and automation routines under a `services/` folder inside it.
3. Expose a central `run_pipeline()` entrypoint in `pipelines/new_platform_outreach/pipeline.py`.
4. Create a corresponding thin wrapper script in the root directory (e.g. `run_new_outreach.py`) that imports and calls your runner function.
5. In `app.py`, update `SubprocessRunner` commands to support triggering the new wrapper script.
6. Ensure that inside your scraper or database operations, you resolve file paths by importing and calling the settings getter functions (e.g. `get_job_leads_file()`) instead of importing static constants.
