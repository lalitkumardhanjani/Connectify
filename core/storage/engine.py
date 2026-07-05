import os
import json
import time
import threading
from config.settings import BASE_DIR
from config.constants import GOOGLE_SHEET_WORKSHEETS
from core.logging.config import logger

# ---------------------------------------------------------------------------
# Caching Layer (In-memory, Thread-Safe, TTL-based)
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_row_cache = {}          # { (username, table_key): (fetched_at_monotonic, data) }
_config_cache = {}       # { username: (fetched_at_monotonic, config_dict) }
CACHE_TTL_SECONDS = 30   # Cache lifetime for Google Sheets reads


def _get_cached_rows(username: str, table_key: str):
    with _cache_lock:
        entry = _row_cache.get((username, table_key))
        if entry:
            ts, data = entry
            if time.monotonic() - ts < CACHE_TTL_SECONDS:
                return data
    return None


def _set_cached_rows(username: str, table_key: str, data: list):
    with _cache_lock:
        _row_cache[(username, table_key)] = (time.monotonic(), data)


def _invalidate_cached_rows(username: str, table_key: str = None):
    with _cache_lock:
        if table_key:
            _row_cache.pop((username, table_key), None)
        else:
            keys_to_remove = [k for k in _row_cache.keys() if k[0] == username]
            for k in keys_to_remove:
                _row_cache.pop(k, None)


def _get_cached_config(username: str):
    with _cache_lock:
        entry = _config_cache.get(username)
        if entry:
            ts, config = entry
            if time.monotonic() - ts < CACHE_TTL_SECONDS:
                return config
    return None


def _set_cached_config(username: str, config: dict):
    with _cache_lock:
        _config_cache[username] = (time.monotonic(), config)


def _invalidate_cached_config(username: str):
    with _cache_lock:
        _config_cache.pop(username, None)


# ---------------------------------------------------------------------------
# Dictionary Flattening/Unflattening Utilities
# ---------------------------------------------------------------------------
def flatten_dict(d, prefix=""):
    """Flattens a nested dictionary into a flat dictionary of dot-notated paths."""
    items = []
    for k, v in d.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(d):
    """Restructures a dot-notated flat dictionary back into its nested format."""
    result = {}
    for k, v in d.items():
        parts = k.split(".")
        current = result
        for p in parts[:-1]:
            current = current.setdefault(p, {})
        
        # Auto-deserialize lists and nested JSON-like structures
        val = v
        if isinstance(v, str):
            v_stripped = v.strip()
            if (v_stripped.startswith("[") and v_stripped.endswith("]")) or (v_stripped.startswith("{") and v_stripped.endswith("}")):
                try:
                    val = json.loads(v_stripped)
                except Exception:
                    pass
        current[parts[-1]] = val
    return result


# ---------------------------------------------------------------------------
# Base Storage Provider Interface
# ---------------------------------------------------------------------------
class BaseStorageProvider:
    def get_config(self, username: str) -> dict:
        raise NotImplementedError()

    def save_config(self, username: str, config: dict):
        raise NotImplementedError()

    def read_rows(self, username: str, table_key: str) -> list:
        raise NotImplementedError()

    def write_rows(self, username: str, table_key: str, data: list):
        raise NotImplementedError()

    def append_row(self, username: str, table_key: str, row: dict):
        raise NotImplementedError()


# ---------------------------------------------------------------------------
# Local Storage Provider (Default)
# ---------------------------------------------------------------------------
class LocalStorageProvider(BaseStorageProvider):
    def get_config_path(self, username: str) -> str:
        return os.path.join(BASE_DIR, "users", username, "config.json")

    def get_config(self, username: str) -> dict:
        path = self.get_config_path(username)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading local config for {username}: {e}")
        return {}

    def save_config(self, username: str, config: dict):
        path = self.get_config_path(username)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving local config for {username}: {e}")

    def get_excel_path(self, username: str, table_key: str) -> str:
        filename_map = {
            "jobs": "LinkedIn_Job_Tracker.xlsx",
            "emails": "job_tracker.xlsx",
            "referrals": "referrals.xlsx"
        }
        if table_key not in filename_map:
            raise ValueError(f"Unknown table key: {table_key}")
        return os.path.join(BASE_DIR, "users", username, "data", filename_map[table_key])

    def read_rows(self, username: str, table_key: str) -> list:
        path = self.get_excel_path(username, table_key)
        if not os.path.exists(path):
            # Auto-initialize with empty headers if file is missing
            self.write_rows(username, table_key, [])
            return []

        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb.active
            headers = [cell.value for cell in ws[1]]
            if not headers:
                return []
            
            rows = []
            for r in range(2, ws.max_row + 1):
                row_dict = {}
                for col_idx, h in enumerate(headers, start=1):
                    val = ws.cell(row=r, column=col_idx).value
                    row_dict[h] = val if val is not None else ""
                rows.append(row_dict)
            return rows
        except Exception as e:
            logger.error(f"Error reading local Excel database file '{path}': {e}")
            return []

    def write_rows(self, username: str, table_key: str, data: list):
        path = self.get_excel_path(username, table_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        headers = GOOGLE_SHEET_WORKSHEETS[table_key]["headers"]
        sheet_title = GOOGLE_SHEET_WORKSHEETS[table_key]["name"].replace(" & ", " ")
        
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_title
            ws.append(headers)
            
            for row in data:
                row_vals = []
                for h in headers:
                    val = row.get(h)
                    row_vals.append(str(val) if val is not None else "")
                ws.append(row_vals)
            
            wb.save(path)
        except Exception as e:
            logger.error(f"Error writing to local Excel database file '{path}': {e}")

    def append_row(self, username: str, table_key: str, row: dict):
        path = self.get_excel_path(username, table_key)
        if not os.path.exists(path):
            self.write_rows(username, table_key, [row])
            return

        headers = GOOGLE_SHEET_WORKSHEETS[table_key]["headers"]
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            row_vals = []
            for h in headers:
                val = row.get(h)
                row_vals.append(str(val) if val is not None else "")
            ws.append(row_vals)
            wb.save(path)
        except Exception as e:
            logger.error(f"Error appending row to local Excel database file '{path}': {e}")


# ---------------------------------------------------------------------------
# Google Sheets Storage Provider (Centralized Cloud Backend)
# ---------------------------------------------------------------------------
class GoogleSheetsStorageProvider(BaseStorageProvider):
    def get_sheets_config(self, username: str):
        """Extracts Sheets connection credentials from the local bootstrap configuration."""
        path = os.path.join(BASE_DIR, "users", username, "config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    gs = cfg.get("global_settings", {})
                    url = gs.get("google_sheet_url")
                    creds = gs.get("google_credentials_json")
                    if url and creds:
                        return url, creds
            except Exception:
                pass
        return None

    def get_config(self, username: str) -> dict:
        # 1. Check in-memory cache
        cached = _get_cached_config(username)
        if cached is not None:
            return cached

        # 2. Retrieve Sheets Credentials
        sheets_conf = self.get_sheets_config(username)
        if not sheets_conf:
            # Fall back to local settings if Sheets are not yet configured
            logger.warning(f"Google Sheets not configured for user {username}. Falling back to Local Storage configs.")
            return LocalStorageProvider().get_config(username)

        url, creds_content = sheets_conf
        ws_name = GOOGLE_SHEET_WORKSHEETS["config"]["name"]

        try:
            from core.storage.sheets import read_rows
            flat_rows = read_rows(url, creds_content, ws_name)
            
            # Map flat Key-Value rows to dictionary format
            flat_dict = {}
            for row in flat_rows:
                key = row.get("Key")
                val = row.get("Value")
                if key:
                    flat_dict[key] = val if val is not None else ""
            
            config_dict = unflatten_dict(flat_dict)
            
            # Merge with local config bootstrap (so we retain local credentials and DB state)
            local_config = LocalStorageProvider().get_config(username)
            if "global_settings" in local_config:
                if "global_settings" not in config_dict:
                    config_dict["global_settings"] = {}
                # Ensure local sheets credentials override anything fetched from sheets
                config_dict["global_settings"].update(local_config["global_settings"])

            _set_cached_config(username, config_dict)
            return config_dict
        except Exception as e:
            logger.error(f"Error loading config from Google Sheet for user {username}: {e}. Falling back to Local.")
            fallback_conf = LocalStorageProvider().get_config(username)
            _set_cached_config(username, fallback_conf)
            return fallback_conf

    def save_config(self, username: str, config: dict):
        # 1. Save local bootstrap settings first (handles credentials storage)
        LocalStorageProvider().save_config(username, config)

        # 2. Check Sheets Credentials
        sheets_conf = self.get_sheets_config(username)
        if not sheets_conf:
            return

        url, creds_content = sheets_conf
        ws_name = GOOGLE_SHEET_WORKSHEETS["config"]["name"]

        # Flatten nested config dict
        flat_dict = flatten_dict(config)
        
        # Format key-value dictionary for Sheets batch update
        data_dicts = []
        for k, v in flat_dict.items():
            # Don't upload massive sensitive credentials json string to the public sheet rows for privacy
            if k == "global_settings.google_credentials_json":
                continue
            
            # Convert arrays or objects to JSON string values
            val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
            data_dicts.append({"Key": k, "Value": val_str})

        try:
            from core.storage.sheets import write_rows, ensure_worksheets_exist
            # Ensure config worksheet exists
            ensure_worksheets_exist(url, creds_content)
            
            # Write to Google Sheet
            write_rows(url, creds_content, ws_name, data_dicts)
            
            # Invalidate in-memory cache
            _invalidate_cached_config(username)
            _set_cached_config(username, config)
        except Exception as e:
            logger.error(f"Failed to save configuration to Google Sheet: {e}")

    def read_rows(self, username: str, table_key: str) -> list:
        # Check cache first
        cached = _get_cached_rows(username, table_key)
        if cached is not None:
            return cached

        sheets_conf = self.get_sheets_config(username)
        if not sheets_conf:
            logger.warning(f"Google Sheets not configured. Reading from local database instead.")
            return LocalStorageProvider().read_rows(username, table_key)

        url, creds_content = sheets_conf
        ws_name = GOOGLE_SHEET_WORKSHEETS[table_key]["name"]

        try:
            from core.storage.sheets import read_rows
            data = read_rows(url, creds_content, ws_name)
            
            # Standardize ID types (convert decimal keys/ID to int strings for consistency with Local Excel)
            id_col = "JobID" if table_key == "jobs" else ("ID" if table_key == "emails" else "ReferralID")
            for row in data:
                if id_col in row and row[id_col] != "":
                    try:
                        row[id_col] = int(float(row[id_col]))
                    except (ValueError, TypeError):
                        pass

            _set_cached_rows(username, table_key, data)
            return data
        except Exception as e:
            logger.error(f"Error reading Google Sheets worksheet '{ws_name}': {e}. Falling back to Local.")
            return LocalStorageProvider().read_rows(username, table_key)

    def write_rows(self, username: str, table_key: str, data: list):
        sheets_conf = self.get_sheets_config(username)
        if not sheets_conf:
            LocalStorageProvider().write_rows(username, table_key, data)
            return

        url, creds_content = sheets_conf
        ws_name = GOOGLE_SHEET_WORKSHEETS[table_key]["name"]

        try:
            from core.storage.sheets import write_rows
            write_rows(url, creds_content, ws_name, data)
            
            # Invalidate and reset cache
            _invalidate_cached_rows(username, table_key)
            _set_cached_rows(username, table_key, data)
        except Exception as e:
            logger.error(f"Error writing to Google Sheets worksheet '{ws_name}': {e}")
            raise e

    def append_row(self, username: str, table_key: str, row: dict):
        sheets_conf = self.get_sheets_config(username)
        if not sheets_conf:
            LocalStorageProvider().append_row(username, table_key, row)
            return

        url, creds_content = sheets_conf
        ws_name = GOOGLE_SHEET_WORKSHEETS[table_key]["name"]

        try:
            from core.storage.sheets import append_row
            append_row(url, creds_content, ws_name, row)
            
            # Invalidate cache so next read downloads the appended row
            _invalidate_cached_rows(username, table_key)
        except Exception as e:
            logger.error(f"Error appending to Google Sheets worksheet '{ws_name}': {e}")
            raise e


# ---------------------------------------------------------------------------
# Storage Manager (Dynamic Provider Resolver)
# ---------------------------------------------------------------------------
class StorageManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(StorageManager, cls).__new__(cls)
                cls._instance.providers = {
                    "local": LocalStorageProvider(),
                    "google_sheets": GoogleSheetsStorageProvider()
                }
            return cls._instance

    def get_provider(self, username: str) -> BaseStorageProvider:
        # Determine the user's active database type from their local bootstrap config file
        path = os.path.join(BASE_DIR, "users", username, "config.json")
        db_type = "local"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    db_type = cfg.get("global_settings", {}).get("database_type", "local")
            except Exception:
                pass
        return self.providers.get(db_type, self.providers["local"])


# ---------------------------------------------------------------------------
# Global Access Helpers
# ---------------------------------------------------------------------------
def get_active_username():
    """Resolves active runner username via env or config file."""
    env_user = os.getenv("CONNECTIFY_USER")
    if env_user:
        return env_user
        
    active_user_file = os.path.join(BASE_DIR, "users", "active_user.json")
    if os.path.exists(active_user_file):
        try:
            with open(active_user_file, "r") as f:
                return json.load(f).get("selected_user") or "default"
        except Exception:
            pass
    return "default"


def get_active_storage_provider() -> BaseStorageProvider:
    username = get_active_username()
    return StorageManager().get_provider(username)


def get_user_config(username: str = None) -> dict:
    if not username:
        username = get_active_username()
    return StorageManager().get_provider(username).get_config(username)


def save_user_config(config: dict, username: str = None):
    if not username:
        username = get_active_username()
    StorageManager().get_provider(username).save_config(username, config)


def read_database_rows(table_key: str, username: str = None) -> list:
    if not username:
        username = get_active_username()
    return StorageManager().get_provider(username).read_rows(username, table_key)


def write_database_rows(table_key: str, data: list, username: str = None):
    if not username:
        username = get_active_username()
    StorageManager().get_provider(username).write_rows(username, table_key, data)


def append_database_row(table_key: str, row: dict, username: str = None):
    if not username:
        username = get_active_username()
    StorageManager().get_provider(username).append_row(username, table_key, row)
