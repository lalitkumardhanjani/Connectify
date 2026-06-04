import os
import pandas as pd
from datetime import datetime, timedelta
from config.settings import JOB_TRACKER_FILE, JOB_LEADS_FILE

def _load_excel(path):
    """Utility to load an Excel file into a pandas DataFrame.
    Returns an empty DataFrame if the file does not exist.
    """
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_excel(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return pd.DataFrame()


def _find_col(df, *candidates):
    """Case-insensitive column finder. Returns the actual column name or None."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


# ---------------------- Email Scraper Metrics ----------------------

def get_email_metrics():
    """Compute email-scraper analytics from job_tracker.xlsx."""
    df = _load_excel(JOB_TRACKER_FILE)

    empty_result = {
        "total_emails": 0,
        "sent": 0,
        "pending": 0,
        "new": 0,
        "added_today": 0,
        "status_distribution": {"sent": 0, "pending": 0, "new": 0},
        "keyword_counts": {},
        "daily_counts": [],
        "pending_queue": [],
        "new_queue": []
    }

    if df.empty:
        return empty_result

    # Identify columns (case-insensitive)
    status_col    = _find_col(df, 'Status')
    keyword_col   = _find_col(df, 'Keyword')
    timestamp_col = _find_col(df, 'Timestamp')
    email_col     = _find_col(df, 'Email')

    if not status_col:
        return empty_result

    # Normalise status to lowercase for comparison
    df['_status'] = df[status_col].astype(str).str.strip().str.lower()

    total_emails = len(df)
    sent    = int((df['_status'] == 'sent').sum())
    new_count = int((df['_status'] == 'new').sum())

    # Added today (based on timestamp)
    added_today = 0
    if timestamp_col:
        today_str = datetime.now().strftime('%Y-%m-%d')
        added_today = int(df[timestamp_col].astype(str).str.startswith(today_str).sum())

    status_distribution = {"sent": sent, "pending": new_count, "new": new_count}

    # Keyword counts — only count non-null, non-empty values
    keyword_counts = {}
    if keyword_col:
        kw_series = df[keyword_col].dropna().astype(str).str.strip()
        kw_series = kw_series[kw_series != '' ].str.title()
        if not kw_series.empty:
            keyword_counts = kw_series.value_counts().to_dict()

    # Daily email counts (last 30 days)
    daily_counts = []
    if timestamp_col:
        try:
            df['_ts'] = pd.to_datetime(df[timestamp_col], errors='coerce')
            last_30 = datetime.now() - timedelta(days=30)
            recent = df[df['_ts'] >= last_30].copy()
            if not recent.empty:
                daily = (
                    recent.groupby(recent['_ts'].dt.date)
                    .size()
                    .reset_index(name='count')
                )
                daily_counts = [
                    {"date": str(row['_ts']), "count": int(row['count'])}
                    for _, row in daily.iterrows()
                ]
        except Exception as e:
            print(f"Daily count error: {e}")

    # New/Pending queue (most recent 20 new)
    new_queue = []
    if email_col:
        new_df = df[df['_status'] == 'new'].copy()
        if timestamp_col and not new_df.empty:
            new_df = new_df.sort_values(by=timestamp_col, ascending=False).head(20)
        rows = []
        for _, row in new_df.head(20).iterrows():
            kw_val = str(row.get(keyword_col, '')) if keyword_col else ''
            rows.append({
                'Email':     str(row.get(email_col, '')) if email_col else '',
                'Keyword':   '' if kw_val in ('nan', 'None', 'NaN') else kw_val,
                'Timestamp': str(row.get(timestamp_col, '')) if timestamp_col else '',
            })
        new_queue = rows

    return {
        "total_emails":        total_emails,
        "sent":                sent,
        "pending":             new_count,
        "new":                 new_count,
        "added_today":         added_today,
        "status_distribution": status_distribution,
        "keyword_counts":      keyword_counts,
        "daily_counts":        daily_counts,
        "pending_queue":       new_queue,
        "new_queue":           new_queue,
    }


# ---------------------- Company Scraper Metrics ----------------------

def get_company_metrics():
    """Compute company-scraper analytics from LinkedIn_Job_Tracker.xlsx."""
    df = _load_excel(JOB_LEADS_FILE)

    empty_result = {
        "total_companies": 0,
        "new": 0,
        "done": 0,
        "not_interested": 0,
        "status_distribution": {},
        "keyword_counts": {},
        "keyword_status": {}
    }

    if df.empty:
        return empty_result

    # Identify columns (case-insensitive) — SearchKeyword is the real name
    status_col  = _find_col(df, 'Status')
    keyword_col = _find_col(df, 'SearchKeyword', 'Search Keyword', 'Keyword')

    if not status_col:
        return empty_result

    # Normalise status
    df['_status'] = df[status_col].astype(str).str.strip().str.lower()

    total_companies = len(df)
    new          = int((df['_status'] == 'new').sum())
    done         = int((df['_status'] == 'done').sum())
    not_interested = int((df['_status'] == 'not interested').sum())

    status_distribution = {
        "new":            new,
        "done":           done,
        "not_interested": not_interested,
    }

    # Keyword counts
    keyword_counts = {}
    if keyword_col:
        kw_series = df[keyword_col].dropna().astype(str).str.strip()
        kw_series = kw_series[kw_series != '']
        if not kw_series.empty:
            keyword_counts = kw_series.value_counts().to_dict()

    # Keyword vs Status breakdown
    keyword_status = {}
    if keyword_col and status_col:
        for kw, group in df.groupby(keyword_col):
            if pd.isna(kw) or str(kw).strip() == '':
                continue
            kw_stats = group['_status'].value_counts().to_dict()
            keyword_status[str(kw)] = {
                "new":            int(kw_stats.get('new', 0)),
                "done":           int(kw_stats.get('done', 0)),
                "not_interested": int(kw_stats.get('not interested', 0)),
            }

    return {
        "total_companies":    total_companies,
        "new":                new,
        "done":               done,
        "not_interested":     not_interested,
        "status_distribution": status_distribution,
        "keyword_counts":     keyword_counts,
        "keyword_status":     keyword_status,
    }
