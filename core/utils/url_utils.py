import re
import urllib.parse

def decode_apply_redirect(apply_url):
    if not apply_url:
        return apply_url

    parsed = urllib.parse.urlparse(apply_url)
    if parsed.netloc.endswith("linkedin.com") and parsed.path.startswith("/safety/go"):
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("url")
        if target:
            return urllib.parse.unquote(target[0])

    return apply_url

def normalize_external_url(url):
    if not url:
        return ""

    cleaned = decode_apply_redirect(url.strip())

    try:
        parsed = urllib.parse.urlparse(cleaned)

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/").lower()

        return urllib.parse.urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                "",
                ""
            )
        )

    except Exception:
        return cleaned.lower()

def is_valid_external_url(url):
    if not url:
        return False

    cleaned = url.strip()
    if not cleaned:
        return False

    invalid_placeholders = {
        "na",
        "n/a",
        "http://na",
        "https://na"
    }

    if cleaned.lower() in invalid_placeholders:
        return False

    if cleaned.startswith("javascript:") or cleaned.startswith("mailto:"):
        return False

    if cleaned.startswith("#"):
        return False

    if not re.match(r"^https?://", cleaned, re.IGNORECASE):
        return False

    return True

def extract_job_id(job_url):
    if not job_url:
        return ""

    match = re.search(r"/jobs/view/(\d+)", job_url)
    if match:
        return match.group(1)

    match = re.search(r"currentJobId=(\d+)", job_url)
    if match:
        return match.group(1)

    return ""

def extract_job_reference_code(driver, current_url="", job_url=""):
    results = []

    if current_url:
        candidates = [
            r"jobReferenceCode=([^&\"']+)",
            r"jobId=([^&\"']+)",
            r"offerID=([^&\"']+)",
            r"jobId%3D([^&\"']+)",
            r"reference=([^&\"']+)",
            r"reqid=([^&\"']+)",
            r"reqId=([^&\"']+)",
            r"id=([A-Za-z0-9-]{4,})",
            r"/jobs/view/(\d+)",
            r"/detail/job/(\d+)"
        ]
        for pattern in candidates:
            m = re.search(pattern, current_url, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if candidate and candidate not in results:
                    results.append(candidate)

    try:
        source = driver.page_source or ""
    except Exception:
        source = ""

    try:
        parsed_ext = urllib.parse.urlparse(current_url or "")
        host = parsed_ext.netloc.lower()
    except Exception:
        host = ""

    if "bnpparibas" in host or "bnpparibas" in (current_url or ""):
        m = re.search(r"(\d{10,})", source)
        if m:
            results.append(m.group(1))

    if "ripplehire" in host or "ripplehire" in (current_url or ""):
        m = re.search(r"\bID[:\s]*([0-9]{4,}-[0-9]{1,}-[0-9]{1,})\b", source, re.IGNORECASE)
        if m:
            results.append(m.group(1))

    if "meesho.io" in host or "lever.co" in (current_url or "") or "meesho" in host or "micro1.ai" in host or "micro1.ai" in (current_url or ""):
        m = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", current_url or "")
        if m:
            results.append(m.group(0))

    if "docs.google.com/forms" in (current_url or "") or "forms.gle" in (current_url or ""):
        m = re.search(r"/d/e/([A-Za-z0-9_\-]+)", current_url or "")
        if m:
            results.append(m.group(1))

    if "hsforms.com" in (current_url or ""):
        m = re.search(r"hsforms\.com/([A-Za-z0-9_\-]+)", current_url or "")
        if m:
            results.append(m.group(1))

    if "hirist" in (current_url or ""):
        m = re.search(r"-(\d+)(?:\?|$)", current_url or "")
        if m:
            results.append(m.group(1))

    if "myworkdayjobs" in host or "workday" in host:
        m = re.search(r"(R\d+)", source, re.IGNORECASE)
        if m:
            results.append(m.group(1))

    if "pwc" in host:
        m = re.search(r"(\d{4,}WD)", source, re.IGNORECASE)
        if m:
            results.append(m.group(1))

    patterns = [
        r"(?:Job\s*Id|Job\s*ID|Job\s*Requisition\s*ID|job\s*requisition\s*id|job\s*id)[:\s]*([A-Za-z0-9-]{3,})",
        r"(?:Job\s*Number|Job\s*No\.?|Reference\s*Number|Reference|Ref(?:erence)?\s*No\.?|Req\.?\s*ID|Req\s*ID)[:\s]*([A-Za-z0-9-]{3,})",
        r"jobReferenceCode=([^&\"']+)",
        r"offerID=([^&\"']+)",
        r"id=([0-9a-fA-F\-]{8,})",
        r"/detail/job/(\d+)",
        r"/jobs/.*/([0-9]{4,})\b"
    ]

    for pattern in patterns:
        for m in re.finditer(pattern, source, re.IGNORECASE):
            candidate = m.group(1).strip()
            if candidate and candidate not in results:
                results.append(candidate)

    filtered = []
    uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
    ripple_re = re.compile(r"^\d{4,}-\d{1,}-\d{1,}$")
    r_workday = re.compile(r"^R\d+$", re.IGNORECASE)
    pwc_re = re.compile(r"^\d{4,}WD$", re.IGNORECASE)
    longnum_re = re.compile(r"^\d{6,}$")

    linkedin_job_id = ""
    try:
        linkedin_job_id = extract_job_id(job_url) if job_url else ""
    except Exception:
        linkedin_job_id = ""

    for c in results:
        cs = c.strip()
        if cs == linkedin_job_id and linkedin_job_id:
            continue
        if uuid_re.match(cs):
            filtered.append(cs)
            continue
        if ripple_re.match(cs):
            filtered.append(cs)
            continue
        if r_workday.match(cs):
            filtered.append(cs)
            continue
        if pwc_re.match(cs):
            filtered.append(cs)
            continue
        if longnum_re.match(cs):
            filtered.append(cs)
            continue
        if re.search(r"\d", cs) and re.match(r"^[A-Za-z0-9-]{4,}$", cs):
            filtered.append(cs)

    out = []
    for f in filtered:
        if f not in out:
            out.append(f)
        if len(out) >= 6:
            break

    return out

def get_unique_job_key(url):
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        priority_keys = [
            "jobReferenceCode",
            "jobid",
            "jobId",
            "reqid",
            "reqId",
            "reference",
            "id"
        ]

        for key in priority_keys:
            if key in params:
                return f"{parsed.netloc}:{params[key][0]}".lower()

        return normalize_external_url(url)

    except Exception:
        return normalize_external_url(url)

def normalize_text(*parts):
    return " ".join(
        p.strip() for p in parts if isinstance(p, str) and p.strip()
    ).lower()
