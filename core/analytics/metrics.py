import os
import pandas as pd
from datetime import datetime, timedelta

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

def _load_data_as_df(table_key):
    """Utility to load table rows as a pandas DataFrame from active storage provider."""
    try:
        from core.storage.engine import read_database_rows
        rows = read_database_rows(table_key, bypass_cache=False)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"Error loading {table_key} database table: {e}")
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
    """Compute email-scraper analytics from active storage provider."""
    df = _load_data_as_df("emails")

    empty_result = {
        "total_emails": 0,
        "sent": 0,
        "pending": 0,
        "new": 0,
        "skipped": 0,
        "added_today": 0,
        "sent_today": 0,
        "status_distribution": {"sent": 0, "pending": 0, "new": 0, "skipped": 0},
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
    skipped = int((df['_status'] == 'skipped').sum())

    # Added today (based on Generated_Time, with fallback to Timestamp)
    added_today = 0
    gen_time_col = _find_col(df, 'Generated_Time')
    if gen_time_col:
        today_str = datetime.now().strftime('%Y-%m-%d')
        added_today = int(df[gen_time_col].astype(str).str.startswith(today_str).sum())
    elif timestamp_col:
        today_str = datetime.now().strftime('%Y-%m-%d')
        added_today = int(df[timestamp_col].astype(str).str.startswith(today_str).sum())

    # Sent today
    sent_today = 0
    sent_time_col = _find_col(df, 'Sent_Time')
    if sent_time_col:
        today_str = datetime.now().strftime('%Y-%m-%d')
        sent_today = int(df[(df['_status'] == 'sent') & (df[sent_time_col].astype(str).str.startswith(today_str))].shape[0])
    elif timestamp_col:
        today_str = datetime.now().strftime('%Y-%m-%d')
        sent_today = int(df[(df['_status'] == 'sent') & (df[timestamp_col].astype(str).str.startswith(today_str))].shape[0])

    status_distribution = {"sent": sent, "pending": new_count, "new": new_count, "skipped": skipped}

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
            # Parse Generated_Time for generation date (fallback to Timestamp if missing)
            gen_time_col = _find_col(df, 'Generated_Time')
            if gen_time_col:
                df['_ts_gen'] = pd.to_datetime(df[gen_time_col], errors='coerce')
            else:
                df['_ts_gen'] = pd.to_datetime(df[timestamp_col], errors='coerce')
            
            # Parse Sent_Time
            sent_time_col = _find_col(df, 'Sent_Time')
            if sent_time_col:
                df['_ts_sent'] = pd.to_datetime(df[sent_time_col], errors='coerce')
            else:
                df['_ts_sent'] = pd.NaT
                
            # For rows where status is sent and _ts_sent is NaT, fallback to Timestamp
            sent_mask = df['_status'] == 'sent'
            df.loc[sent_mask & df['_ts_sent'].isna(), '_ts_sent'] = pd.to_datetime(df.loc[sent_mask & df['_ts_sent'].isna(), timestamp_col], errors='coerce')
            
            # Get start date (90 days ago)
            last_90_date = (datetime.now() - timedelta(days=90)).date()
            
            # We want to collect all dates in the last 90 days
            today = datetime.now().date()
            dates_range = [today - timedelta(days=i) for i in range(90)]
            dates_range.reverse() # chronologically ascending
            
            # Create a dictionary to hold counts
            counts_by_date = {str(d): {"generated": 0, "sent": 0} for d in dates_range}
            
            # Count generated emails
            gen_df = df[df['_ts_gen'].dt.date >= last_90_date]
            if not gen_df.empty:
                for d, g in gen_df.groupby(gen_df['_ts_gen'].dt.date):
                    d_str = str(d)
                    if d_str in counts_by_date:
                        counts_by_date[d_str]["generated"] = int(len(g))
                        
            # Count sent emails
            sent_df = df[(df['_status'] == 'sent') & (df['_ts_sent'].dt.date >= last_90_date)]
            if not sent_df.empty:
                for d, g in sent_df.groupby(sent_df['_ts_sent'].dt.date):
                    d_str = str(d)
                    if d_str in counts_by_date:
                        counts_by_date[d_str]["sent"] = int(len(g))
            
            daily_counts = [
                {"date": d_str, "generated": val["generated"], "sent": val["sent"]}
                for d_str, val in counts_by_date.items()
            ]
        except Exception as e:
            print(f"Daily count error: {e}")

    # New/Pending queue (most recent 20 new)
    new_queue = []
    if email_col:
        new_df = df[df['_status'] == 'new'].copy()
        if timestamp_col and not new_df.empty:
            new_df = new_df.sort_values(by=timestamp_col, ascending=False)
        rows = []
        for _, row in new_df.iterrows():
            kw_val = str(row.get(keyword_col, '')) if keyword_col else ''
            rows.append({
                'Email':     str(row.get(email_col, '')) if email_col else '',
                'Keyword':   '' if kw_val in ('nan', 'None', 'NaN') else kw_val,
                'Timestamp': str(row.get(timestamp_col, '')) if timestamp_col else '',
            })
        new_queue = rows

    # Domain counts
    domain_distribution = {}
    if email_col:
        emails_series = df[email_col].dropna().astype(str).str.strip().str.lower()
        emails_series = emails_series[emails_series.str.contains('@')]
        if not emails_series.empty:
            domains = emails_series.apply(lambda e: e.split('@')[-1] if '@' in e else 'unknown')
            domain_distribution = domains.value_counts().to_dict()

    send_success_rate = 0.0
    if total_emails > 0:
        send_success_rate = round((sent / total_emails) * 100, 1)

    return {
        "total_emails":        total_emails,
        "sent":                sent,
        "pending":             new_count,
        "new":                 new_count,
        "skipped":             skipped,
        "added_today":         added_today,
        "sent_today":          sent_today,
        "send_success_rate":   send_success_rate,
        "status_distribution": status_distribution,
        "domain_distribution": domain_distribution,
        "keyword_counts":      keyword_counts,
        "daily_counts":        daily_counts,
        "pending_queue":       new_queue,
        "new_queue":           new_queue,
    }


# ---------------------- Company Scraper Metrics ----------------------

def get_company_metrics():
    """Compute company-scraper analytics from active storage provider."""
    df = _load_data_as_df("jobs")
    ref_df = _load_data_as_df("referrals")

    empty_result = {
        "total_companies": 0,
        "new": 0,
        "done": 0,
        "not_interested": 0,
        "interested": 0,
        "referral_outreach": 0,
        "status_distribution": {},
        "keyword_counts": {},
        "keyword_status": {},
        "top_hiring_companies": {},
        "daily_counts": []
    }

    if df.empty:
        return empty_result

    # Identify columns (case-insensitive) — SearchKeyword is the real name
    status_col  = _find_col(df, 'Status')
    keyword_col = _find_col(df, 'SearchKeyword', 'Search Keyword', 'Keyword')
    company_col = _find_col(df, 'CompanyName', 'Company Name', 'Company')

    if not status_col:
        return empty_result

    # Normalise status
    df['_status'] = df[status_col].astype(str).str.strip().str.lower()

    total_companies = len(df)
    new          = int((df['_status'] == 'new').sum())
    done         = int((df['_status'] == 'done').sum())
    not_interested = int((df['_status'] == 'not interested').sum())
    interested   = int((df['_status'] == 'interested').sum())
    referral_outreach = int(df['_status'].isin(['ask for referral', 'asked for referral', 'referred', 'referral outreach completed']).sum())

    # Dynamic status distribution
    status_distribution = {}
    status_series = df[status_col].dropna().astype(str).str.strip().str.title()
    status_series = status_series[status_series != '']
    if not status_series.empty:
        status_distribution = status_series.value_counts().to_dict()

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

    # Top hiring companies
    top_hiring_companies = {}
    if company_col:
        comp_series = df[company_col].dropna().astype(str).str.strip()
        comp_series = comp_series[comp_series != '']
        if not comp_series.empty:
            top_hiring_companies = comp_series.value_counts().head(10).to_dict()

    # Build daily counts (last 90 days)
    daily_counts = []
    try:
        today = datetime.now().date()
        dates_range = [today - timedelta(days=i) for i in range(90)]
        dates_range.reverse()
        counts_by_date = {str(d): {"companies_added": 0, "connections_sent": 0} for d in dates_range}

        # Jobs created daily
        created_col = _find_col(df, 'CreatedDateTime', 'Created DateTime', 'Timestamp')
        if created_col:
            df['_ts_created'] = pd.to_datetime(df[created_col], errors='coerce')
            last_90_date = (datetime.now() - timedelta(days=90)).date()
            recent_jobs = df[df['_ts_created'].dt.date >= last_90_date]
            if not recent_jobs.empty:
                for d, g in recent_jobs.groupby(recent_jobs['_ts_created'].dt.date):
                    d_str = str(d)
                    if d_str in counts_by_date:
                        counts_by_date[d_str]["companies_added"] = int(len(g))

        # Connections sent daily
        if not ref_df.empty:
            sent_time_col = _find_col(ref_df, 'Sent_Time', 'Sent Time')
            if sent_time_col:
                ref_df['_ts_sent'] = pd.to_datetime(ref_df[sent_time_col], errors='coerce')
                source_col = _find_col(ref_df, 'Referral_Source')
                if source_col:
                    conn_df = ref_df[ref_df[source_col].astype(str).str.lower().str.contains('connection|connect')]
                else:
                    conn_df = ref_df
                
                last_90_date = (datetime.now() - timedelta(days=90)).date()
                recent_conn = conn_df[conn_df['_ts_sent'].dt.date >= last_90_date]
                if not recent_conn.empty:
                    for d, g in recent_conn.groupby(recent_conn['_ts_sent'].dt.date):
                        d_str = str(d)
                        if d_str in counts_by_date:
                            counts_by_date[d_str]["connections_sent"] = int(len(g))

        daily_counts = [
            {
                "date": d_str,
                "companies_added": val["companies_added"],
                "connections_sent": val["connections_sent"]
            }
            for d_str, val in counts_by_date.items()
        ]
    except Exception as e:
        print(f"Daily company analytics count error: {e}")

    return {
        "total_companies":    total_companies,
        "new":                new,
        "done":               done,
        "not_interested":     not_interested,
        "interested":         interested,
        "referral_outreach":  referral_outreach,
        "status_distribution": status_distribution,
        "keyword_counts":     keyword_counts,
        "keyword_status":     keyword_status,
        "top_hiring_companies": top_hiring_companies,
        "daily_counts":       daily_counts
    }


# ---------------------- Outreach & Referral Metrics ----------------------

def get_outreach_metrics():
    """Compute outreach and referral analytics from active storage provider."""
    df = _load_data_as_df("referrals")

    empty_result = {
        "total_contacts": 0,
        "sent": 0,
        "pending": 0,
        "failed": 0,
        "status_distribution": {},
        "source_distribution": {},
        "company_distribution": {},
        "daily_counts": [],
        "recent_outreach": []
    }

    if df.empty:
        return empty_result

    # Identify columns (case-insensitive/flexible)
    status_col = _find_col(df, 'Referral_Status', 'Referral Status', 'Status')
    source_col = _find_col(df, 'Referral_Source', 'Referral Source', 'Source')
    company_col = _find_col(df, 'CompanyName', 'Company Name', 'Company')
    time_col = _find_col(df, 'Sent_Time', 'Sent Time', 'Time')
    name_col = _find_col(df, 'Referral_Person_Name', 'Referral Person Name', 'Name')
    error_col = _find_col(df, 'Error_Reason', 'Error Reason', 'Error')

    # Normalize status values
    df['_status'] = df[status_col].astype(str).str.strip().str.lower() if status_col else ''
    
    total_contacts = len(df)
    sent = int((df['_status'] == 'sent').sum()) if status_col else 0
    pending = int((df['_status'] == 'pending').sum()) if status_col else 0
    
    # Classify failed status
    failed = 0
    if status_col:
        failed_mask = (df['_status'] == 'failed') | (df['_status'] == 'error')
        if error_col:
            # Also count if error reason is present but status is not sent or pending (meaning it failed)
            error_present = (df[error_col].astype(str).str.strip() != '') & (df[error_col].notna()) & (~df[error_col].astype(str).str.strip().str.lower().isin(['nan', 'none', '']))
            not_sent = df['_status'] != 'sent'
            failed_mask = failed_mask | (error_present & not_sent)
        failed = int(failed_mask.sum())

    # Build distributions
    status_distribution = {}
    if status_col:
        status_series = df[status_col].dropna().astype(str).str.strip().str.title()
        status_series = status_series[status_series != '']
        if not status_series.empty:
            status_distribution = status_series.value_counts().to_dict()

    source_distribution = {}
    if source_col:
        source_series = df[source_col].dropna().astype(str).str.strip()
        source_series = source_series[source_series != '']
        if not source_series.empty:
            source_distribution = source_series.value_counts().to_dict()

    company_distribution = {}
    if company_col:
        comp_series = df[company_col].dropna().astype(str).str.strip()
        comp_series = comp_series[comp_series != '']
        if not comp_series.empty:
            company_distribution = comp_series.value_counts().to_dict()

    # Build daily counts
    daily_counts = []
    if time_col:
        try:
            df['_ts'] = pd.to_datetime(df[time_col], errors='coerce')
            last_30 = datetime.now() - timedelta(days=30)
            recent = df[(df['_ts'].notna()) & (df['_ts'] >= last_30)].copy()
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
            print(f"Daily outreach count error: {e}")

    # Build recent outreach queue
    recent_outreach = []
    if time_col:
        try:
            df['_ts'] = pd.to_datetime(df[time_col], errors='coerce')
            sorted_df = df.sort_values(by='_ts', ascending=False)
        except Exception:
            sorted_df = df.iloc[::-1]
    else:
        sorted_df = df.iloc[::-1]

    for _, row in sorted_df.head(20).iterrows():
        name_val = str(row.get(name_col, '')) if name_col and not pd.isna(row.get(name_col)) else ''
        comp_val = str(row.get(company_col, '')) if company_col and not pd.isna(row.get(company_col)) else ''
        src_val = str(row.get(source_col, '')) if source_col and not pd.isna(row.get(source_col)) else ''
        status_val = str(row.get(status_col, '')) if status_col and not pd.isna(row.get(status_col)) else ''
        time_val = str(row.get(time_col, '')) if time_col and not pd.isna(row.get(time_col)) else ''
        err_val = str(row.get(error_col, '')) if error_col and not pd.isna(row.get(error_col)) else ''

        if name_val.lower() in ('nan', 'none'): name_val = ''
        if comp_val.lower() in ('nan', 'none'): comp_val = ''
        if src_val.lower() in ('nan', 'none'): src_val = ''
        if status_val.lower() in ('nan', 'none'): status_val = ''
        if time_val.lower() in ('nan', 'none'): time_val = ''
        if err_val.lower() in ('nan', 'none'): err_val = ''

        if time_val and len(time_val) > 16:
            time_val = time_val[:16].replace('T', ' ')

        recent_outreach.append({
            "Name": name_val,
            "Company": comp_val,
            "Source": src_val,
            "Status": status_val,
            "SentTime": time_val,
            "Error": err_val
        })

    return {
        "total_contacts": total_contacts,
        "sent": sent,
        "pending": pending,
        "failed": failed,
        "status_distribution": status_distribution,
        "source_distribution": source_distribution,
        "company_distribution": company_distribution,
        "daily_counts": daily_counts,
        "recent_outreach": recent_outreach
    }
