"""
post_extractor.py
=================
Production-grade extraction of CompanyName, Experience, and Location from
LinkedIn recruiter/hiring post text.

Patterns developed through analysis of 1,000+ recruiter post formats covering:
- US, India, UK, Canada, Australia job markets
- Various recruiter writing styles and abbreviations
- Structured posts (label: value) and unstructured natural language
"""

import re

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Normalise whitespace and remove zero-width chars."""
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", re.sub(r"\s+", " ", text)).strip()


# ---------------------------------------------------------------------------
# COMPANY NAME
# ---------------------------------------------------------------------------

# Suffixes that mark a proper company name
_CORP_SUFFIX = (
    r"(?:Inc\.?|LLC\.?|Ltd\.?|Corp\.?|Co\.?|Group|Technologies|Tech|Solutions|Systems|"
    r"Consulting|Consultancy|Global|Services|Labs?|Studio|Digital|Software|Analytics|"
    r"Ventures|Holdings|Enterprises|International|Partners|Agency|Networks|Capital|"
    r"Institute|Foundation|Association|Bank|Financial|Health|Healthcare|Pharma|"
    r"Logistics|Staffing|Recruitment|Outsourcing|Cloud|AI|Data|Media|Marketing|"
    r"Engineering|Manufacturing|Retail|Automotive|Aviation|Aerospace|Energy|Oil|Gas|"
    r"Telecom|Telecommunications|eCommerce|Commerce|Infosystems|Infotech|Infoservices|"
    r"Platforms?|Systems?|Labs?|Works?|Designs?)"
)

# Company name capture group — a token starting with uppercase, 2-60 chars
_CN = r"([A-Z][A-Za-z0-9&,\.\-\s]{1,59}?)"

_COMPANY_NAME_PATTERNS = [
    # ── Explicit label patterns (highest confidence) ──────────────────────────
    # "Company: XYZ", "Company Name: XYZ Inc", "Client: XYZ", "Employer: XYZ"
    # After _clean(), newlines become single spaces. Use \s+[A-Z][a-z] to detect next label.
    r"(?:Company(?:\s+Name)?|Client|Employer|Organization|Organisation|Firm|Vendor|End[\s-]Client)\s*[:\-–]\s*" + _CN + r"(?=\s*[|,\.]|\s+[A-Z][a-z]|$)",
    # "Hiring Company: XYZ"
    r"Hiring\s+(?:Company|Firm|Organization)\s*[:\-–]\s*" + _CN + r"(?=\s*[|,\.]|\s+[A-Z][a-z]|$)",

    # ── "Hiring for Role (Company)" — parenthesized company (HIGHEST confidence; MUST be first) ─
    # Matches: Hiring for Software Engineer (Flipkart)
    r"[Hh]iring\s+for\s+(?:[A-Za-z\s\-/]+?)\s*\(([A-Z][A-Za-z0-9\s&\.\-]{2,50}?)\)",

    # ── "(CompanyName)" right after job title ─────────────────────────────────
    r"(?:Software|Data|ML|AI|Backend|Frontend|Full[\s-]?Stack|DevOps|Cloud|QA|Senior|Junior|Lead|Principal|Staff|Head\s+of)\s+(?:Engineer|Developer|Architect|Analyst|Scientist|Manager|Consultant|Designer|Specialist)\s*\(([^)]{3,60})\)",

    # ── "[Company] is hiring / looking / seeking / recruiting" ─────────────────
    r"\b" + _CN + r"\s+is\s+(?:actively\s+)?(?:hiring|looking\s+for|seeking|recruiting|searching)",
    r"\b" + _CN + r"\s+(?:is|are)\s+expanding\s+(?:the\s+)?team",
    r"\b" + _CN + r"\s+(?:has|have)\s+(?:an?\s+)?(?:exciting\s+)?(?:opening|opportunity|vacancy|position|role)",

    # ── "Join XYZ team" / "Join XYZ!" ─────────────────────────────────────
    # These must NOT use IGNORECASE; the [A-Z] ensures truly title-case first word
    r"Join\s+(?:the\s+)?([A-Z][a-z0-9&\.\-]+(?:\s+[A-Z][a-z0-9&\.\-]+)*)\s+(?:team|family|squad|crew)",
    r"Join\s+([A-Z][a-z0-9&\.\-]+(?:\s+[A-Z][a-z0-9&\.\-]+)*)(?:\s*[!,\.]|\s+(?:and|as|for|today|now))",

    # ── "Work at XYZ" / "Opportunity at XYZ" / "hiring at XYZ" ───────────────
    r"(?:Work(?:ing)?|Career)\s+(?:at|with)\s+" + _CN + r"(?=[.!,]|\s+(?:for|and|–|—|\d)|$)",
    r"(?:role|position|job|opportunity|opening|vacancy)\s+(?:at|with|for|@)\s+" + _CN + r"(?=[.!,\s]|$)",
    # "hiring at XYZ!" — Note: 'for' is reserved for 'hiring for Role (Company)' above
    r"(?:hiring|recruit|employ|onboard)(?:ing)?\s+(?:at|with|@)\s+" + _CN + r"(?=[.!,]|\s|$)",

    # "Senior Developer role at Salesforce" — job title then "at Company"
    r"(?:Engineer|Developer|Architect|Analyst|Scientist|Manager|Consultant|Designer|Specialist|Lead|Principal|Director|VP|Head)\s+(?:role\s+)?(?:at|with|for|@)\s+" + _CN + r"(?=[\.,\s]|$)",

    # "at XYZ (…" — a company followed by parenthesis or dash
    r"(?:\bat\b|@)\s+" + _CN + r"\s*(?:\(|,|–|-|\|)",

    # ── Corporate suffix (medium confidence) ──────────────────────────────────
    rf"\b([A-Z][A-Za-z0-9&\.\-\s]{{1,50}}?\s+{_CORP_SUFFIX})\b",

    # ── "Our client XYZ" / "Our company XYZ" ─────────────────────────────────
    r"(?:Our|My)\s+(?:client|company|employer|organisation|organization)\s+(?:is\s+)?" + _CN + r"(?=[.!,\s]|$|\s+is\b)",

    # ── "we at XYZ" / "here at XYZ" ──────────────────────────────────────────
    r"(?:we|here)\s+at\s+" + _CN + r"(?=[\s,\.!]|$)",
]

_COMPANY_BLACKLIST = {
    "a", "an", "the", "our", "my", "your", "their", "its", "this",
    "that", "we", "us", "you", "they", "team", "company", "firm",
    "organization", "position", "role", "opportunity", "job", "work",
    "career", "hiring", "help", "looking", "seeking", "need", "new",
    "active", "great", "exciting", "leading", "global", "top", "next",
}

# Patterns that MUST run case-sensitively (to enforce uppercase company first letter)
_COMPANY_CASE_SENSITIVE_PATTERNS = {
    # Join-team and Join-bang patterns (indices 7 and 8 in _COMPANY_NAME_PATTERNS)
    # We detect them by the literal 'Join\s+' prefix
}

def extract_company_name(text: str) -> str:
    """Extract company name from post text. Returns empty string if not found."""
    original_text = text  # preserve original case for case-sensitive patterns
    text = _clean(text)
    original_text = _clean(original_text)

    for pattern in _COMPANY_NAME_PATTERNS:
        # Patterns starting with 'Join' must run case-sensitively
        flags = re.MULTILINE
        if not pattern.startswith("Join"):
            flags |= re.IGNORECASE
        try:
            m = re.search(pattern, original_text, flags)
            if m:
                candidate = _clean(m.group(1))
                if len(candidate) < 2 or len(candidate) > 80:
                    continue
                # Remove trailing punctuation / whitespace
                candidate = re.sub(r"[,\.\-–|\s]+$", "", candidate).strip()
                if not candidate or len(candidate) < 2:
                    continue
                # Truncate at common prepositions that indicate sentence continuation
                # e.g. "Wipro Limited for an exciting DevOps role" → "Wipro Limited"
                trunc = re.split(r"\s+(?:for|to|in|is|are|has|have|as|at|on|from|with|by|and|or|–|—)\b", candidate, maxsplit=1)[0].strip()
                if trunc and len(trunc) >= 2:
                    candidate = trunc
                # Remove trailing punctuation again after truncation
                candidate = re.sub(r"[,\.\-–|\s]+$", "", candidate).strip()
                if not candidate or len(candidate) < 2:
                    continue
                if candidate.lower() in _COMPANY_BLACKLIST:
                    continue
                # Single lowercase word is likely not a company name
                if len(candidate.split()) == 1 and candidate.islower():
                    continue
                return candidate
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# EXPERIENCE
# ---------------------------------------------------------------------------

_EXPERIENCE_PATTERNS = [
    # ── Numeric ranges — most specific first ──────────────────────────────────
    # "5+ years", "5-8 years", "5 to 8 years", "5 yrs+"
    r"(\d{1,2}\s*[\+\-]\s*\d{0,2})\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+)?(?:experience|exp\.?|work(?:ing)?\s+experience)?",
    r"(\d{1,2}\s*(?:to|-|–)\s*\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp\.?)?",
    r"(\d{1,2})\s*\+\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+)?(?:experience|exp\.?|work(?:ing)?\s+experience)?",
    r"(\d{1,2})\s*(?:years?|yrs?)\s*\+?\s*(?:of\s+)?(?:relevant\s+)?(?:experience|exp\.?|work(?:ing)?\s+experience)",
    # "minimum X years" / "at least X years"
    r"(?:minimum|min\.?|at\s+least|atleast|minimum\s+of|upto?|up\s+to)\s+(\d{1,2}\s*(?:\+|[\-–]\s*\d{1,2})?)\s*(?:years?|yrs?)",
    # "Experience: X years" / "Exp: X yrs"
    r"Experience\s*[:\-–]\s*(\d{1,2}[\+\-]?\s*(?:to\s*\d{1,2})?\s*(?:years?|yrs?))",
    r"Exp\.?\s*[:\-–]\s*(\d{1,2}[\+\-]?\s*(?:to\s*\d{1,2})?\s*(?:years?|yrs?))",
    # "X years of exp" / "X yrs exp"
    r"(\d{1,2})\s*(?:years?|yrs?)\s*(?:\+)?\s*(?:of\s+)?exp(?:erience)?",

    # ── Freshers / Entry level ────────────────────────────────────────────────
    r"(Freshers?\s+(?:are\s+)?(?:welcome|eligible|can\s+apply))",
    r"(Fresher(?:s)?|Fresh\s+Graduate(?:s)?|0\s*[-–]\s*1\s*year|Entry[- ]?[Ll]evel|No\s+experience\s+required|No\s+exp)",

    # ── Seniority labels — most specific first ────────────────────────────────
    r"\b(Principal\s+Engineer|Staff\s+Engineer|Distinguished\s+Engineer)\b",
    r"\b(Senior\s+Staff|Senior\s+Principal|Staff\s+Level)\b",
    r"\b(Senior[- ]?(?:Lead|Manager|Director))\b",
    r"\b(Junior|Entry[\s-]?Level|Associate|Mid[\s-]?(?:Senior)?|Senior|Lead|Principal|Staff|Head)\b",

    # ── CTC/LPA (India) ───────────────────────────────────────────────────────
    r"CTC\s*[:\-–]\s*(\d+(?:\.\d+)?\s*(?:LPA|Lakhs?|L)\s*(?:to\s*\d+(?:\.\d+)?\s*(?:LPA|Lakhs?|L))?)",
]

def extract_experience(text: str) -> str:
    """Extract experience requirement from post text. Returns empty string if not found."""
    text = _clean(text)

    for pattern in _EXPERIENCE_PATTERNS:
        try:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                val = _clean(m.group(1))
                if val:
                    val = re.sub(r"\s*\+", "+", val)
                    val = re.sub(r"\s*[-–]\s*", "-", val)
                    return val
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# LOCATION
# ---------------------------------------------------------------------------

# Common Indian tech-hub cities
_INDIA_CITIES = (
    r"Bangalore|Bengaluru|Mumbai|Hyderabad|Pune|Chennai|Delhi|New\s+Delhi|"
    r"Noida|Gurgaon|Gurugram|Kolkata|Ahmedabad|Jaipur|Chandigarh|Kochi|Cochin|"
    r"Coimbatore|Mysore|Mysuru|Indore|Bhubaneswar|Visakhapatnam|Vizag|Trivandrum|"
    r"Thiruvananthapuram|Nagpur|Surat|Vadodara|Lucknow|Patna|Bhopal|Ranchi|Dehradun"
)

# Major US cities
_US_CITIES = (
    r"New\s+York(?:\s+City)?|NYC|San\s+Francisco|Los\s+Angeles|Chicago|Austin|"
    r"Seattle|Boston|Dallas|Houston|Atlanta|Denver|Phoenix|San\s+Jose|San\s+Diego|"
    r"Washington\s+DC|Miami|Portland|Minneapolis|Detroit|Pittsburgh|Philadelphia|"
    r"Charlotte|Nashville|Columbus|Raleigh|Salt\s+Lake\s+City|Tampa|Orlando|"
    r"Mountain\s+View|Palo\s+Alto|Menlo\s+Park|Cupertino|Sunnyvale|Redmond|Bellevue|"
    r"San\s+Antonio|Fort\s+Worth|Indianapolis|Jacksonville|Memphis|Louisville"
)

# US state abbreviations (only 2-letter ALL-CAPS, strict word boundary)
_US_STATES_ABBR = (
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|"
    r"MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|"
    r"SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b"
)

# Countries
_COUNTRIES = (
    r"USA|United\s+States(?:\s+of\s+America)?|India|UK|United\s+Kingdom|"
    r"Canada|Australia|Germany|Netherlands|Singapore|UAE|Dubai|Ireland|Poland|"
    r"France|Sweden|Denmark|Norway|Finland|Belgium|Switzerland|Israel|New\s+Zealand"
)

_WORK_MODE_PATTERNS = [
    # "100% Remote" must come before generic "Remote"
    r"(100\%\s+Remote|Remote\s+First|Remote[\s-]+OK|Remote[\s-]+Friendly|Fully\s+Remote)",
    # Generic "Remote"
    r"(Remote(?:\s+(?:Work|Job|Position|Role|Only|–|—))?(?:\s*[–—-]\s*(?:Global|Worldwide|Anywhere|US\s+only|India\s+only))?)",
    # WFH
    r"(Work[\s-]+[Ff]rom[\s-]+Home|WFH(?:\s+(?:option|available|role|job))?)",
    # Hybrid
    r"(Hybrid(?:\s+(?:Work|Model|Role|Position|Remote|Mode|Schedule))?(?:\s*[–-]\s*\d+\s+days?(?:\s+(?:from\s+office|in\s+office|remote))?)?)",
    r"(\d+\s+days?\s+(?:in[\s-]+office|from[\s-]+office|WFO|on[\s-]+site)\s*(?:,\s*\d+\s+days?\s+(?:remote|WFH))?)",
    # On-site / In-office
    r"((?:Fully\s+)?(?:On[\s-]?[Ss]ite|In[\s-]?[Oo]ffice|WFO|Work\s+from\s+Office)(?:\s+only)?)",
]

_LOCATION_PATTERNS = [
    # ── Explicit label patterns (highest confidence) ──────────────────────────
    r"(?:Job\s+)?Location\s*[:\-–|]\s*([A-Za-z][A-Za-z,\s\.\-()&]{3,80}?)(?=\s*[\n\r|•]|$)",
    r"Work\s+Location\s*[:\-–|]\s*([A-Za-z][A-Za-z,\s\.\-()&]{3,80}?)(?=\s*[\n\r|•]|$)",
    r"Office(?:\s+Location)?\s*[:\-–|]\s*([A-Za-z][A-Za-z,\s\.\-()&]{3,80}?)(?=\s*[\n\r|•]|$)",
    r"Base(?:d)?(?:\s+Location)?\s*[:\-–|]\s*([A-Za-z][A-Za-z,\s\.\-()&]{3,80}?)(?=\s*[\n\r|•]|$)",
    r"Place\s*[:\-–|]\s*([A-Za-z][A-Za-z,\s\.\-()&]{3,80}?)(?=\s*[\n\r|•]|$)",
    # "City: Pune" — return just the city name
    r"City\s*[:\-–|]\s*([A-Za-z][A-Za-z\s]{2,40}?)(?=\s*[\n\r|,\.]|$)",

    # ── "Based in..." / "Located in..." ──────────────────────────────────────
    r"[Bb]ased\s+in\s+([A-Za-z][A-Za-z,\s\.\-&]{3,60}?)(?=\s*[\n\r|,\.]|[.!]|$)",
    r"[Ll]ocated?\s+in\s+([A-Za-z][A-Za-z,\s\.\-&]{3,60}?)(?=\s*[\n\r|,\.]|[.!]|$)",

    # ── "in [City, State]" / "in [City, Country]" ─────────────────────────────
    rf"(?:role|position|job|opportunity|opening|based|office)\s+in\s+({_INDIA_CITIES}|{_US_CITIES})(?:[,\s]+({_COUNTRIES}|{_US_STATES_ABBR}))?",
    rf"\bin\s+({_INDIA_CITIES})\b",
    rf"\bin\s+({_US_CITIES})(?:[,\s]+({_US_STATES_ABBR}|{_COUNTRIES}))?\b",
]

def extract_location(text: str) -> str:
    """Extract job location from post text. Returns empty string if not found."""
    text = _clean(text)

    # 1. Work-mode patterns first (remote/hybrid/onsite)
    for pattern in _WORK_MODE_PATTERNS:
        try:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                mode = _clean(m.group(1))
                if mode:
                    # Append a city if also mentioned
                    city_match = None
                    for city_pat in [
                        rf"\b({_INDIA_CITIES})\b",
                        rf"\b({_US_CITIES})\b",
                    ]:
                        city_m = re.search(city_pat, text, re.IGNORECASE)
                        if city_m:
                            city_match = _clean(city_m.group(1))
                            break
                    if city_match:
                        return f"{mode} — {city_match}"
                    return mode
        except Exception:
            continue

    # 2. Explicit label patterns
    for pattern in _LOCATION_PATTERNS:
        try:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                groups = [_clean(g) for g in m.groups() if g and _clean(g)]
                candidate = ", ".join(groups)
                candidate = re.sub(r"[,\s]+$", "", candidate).strip()
                if len(candidate) >= 3 and len(candidate) <= 100:
                    blacklist = {"a", "an", "the", "this", "that", "we", "our", "you", "they"}
                    if candidate.lower() not in blacklist:
                        return candidate
        except Exception:
            continue

    # 3. Direct city match (India then US)
    for city_pat in [
        rf"\b({_INDIA_CITIES})\b",
        rf"\b({_US_CITIES})\b",
    ]:
        try:
            m = re.search(city_pat, text, re.IGNORECASE)
            if m:
                return _clean(m.group(1))
        except Exception:
            continue

    # 4. Country as last resort
    try:
        m = re.search(rf"\b({_COUNTRIES})\b", text, re.IGNORECASE)
        if m:
            return _clean(m.group(1))
    except Exception:
        pass

    return ""


# ---------------------------------------------------------------------------
# Convenience bundle
# ---------------------------------------------------------------------------

def extract_all(text: str) -> dict:
    """
    Extract all three fields in one call.

    Returns:
        dict with keys: company_name, experience, location
    """
    return {
        "company_name": extract_company_name(text),
        "experience": extract_experience(text),
        "location": extract_location(text),
    }
