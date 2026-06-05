import re

def extract_emails(text):
    """Extract all email addresses from the given text using regex."""
    if not text:
        return []
    
    # Regex to match email addresses
    email_pattern = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    emails = re.findall(email_pattern, text)
    
    # Return unique emails
    return list(set(emails))

def parse_preferred_locations(pref_location_str):
    """Parses a preferred location string into a list of cleaned locations.
    Intelligently merges hierarchical state/country keywords (e.g. Karnataka, India) with the city name
    while separating multiple distinct cities (e.g. Bangalore, Delhi, Mumbai).
    """
    if not pref_location_str:
        return []
    
    # Common state/country names to identify hierarchical locations
    hierarchical_keywords = {
        # Countries
        "india", "usa", "united states", "united kingdom", "uk", "canada", "australia", "germany",
        # Indian States (excluding Delhi to avoid merging "Bangalore, Delhi")
        "karnataka", "maharashtra", "telangana", "tamil nadu", "haryana", "uttar pradesh", "gujarat", 
        "west bengal", "punjab", "rajasthan", "madhya pradesh", "andhra pradesh", "kerala",
        # US States
        "california", "texas", "new york", "florida", "illinois", "pennsylvania", "ohio", "georgia", "washington"
    }
    
    parts = [p.strip() for p in pref_location_str.split(",") if p.strip()]
    locations = []
    
    current_loc_parts = []
    for part in parts:
        part_lower = part.lower()
        # If it's a known hierarchical keyword, append to the current location building block
        if part_lower in hierarchical_keywords and current_loc_parts:
            current_loc_parts.append(part)
        else:
            # If we had a previously built location, save it
            if current_loc_parts:
                locations.append(", ".join(current_loc_parts))
            current_loc_parts = [part]
            
    if current_loc_parts:
        locations.append(", ".join(current_loc_parts))
        
    return locations

