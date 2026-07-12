import logging
import os
import sys
import time
from datetime import datetime

def cleanup_old_logs(logs_dir, days=7):
    """
    Deletes log files in the given directory that are older than the specified number of days.
    """
    try:
        if not os.path.exists(logs_dir):
            return
        cutoff = time.time() - (days * 24 * 60 * 60)
        for filename in os.listdir(logs_dir):
            if filename.endswith(".log"):
                file_path = os.path.join(logs_dir, filename)
                if os.path.isfile(file_path):
                    if os.path.getmtime(file_path) < cutoff:
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
    except Exception:
        pass

class DynamicUserFileHandler(logging.Handler):
    """
    A logging Handler that dynamically determines the active user's log folder
    at record-write time, keeping user logs completely isolated.
    """
    def __init__(self, filename_base="automation.log"):
        super().__init__()
        self.filename_base = filename_base
        self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Determine unique timestamped filename for CLI runs
        entry_script = os.path.basename(sys.argv[0]) if (sys.argv and sys.argv[0]) else "automation.py"
        entry_name = os.path.splitext(entry_script)[0].replace(".", "_")
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.timestamped_filename = f"{entry_name}_{run_timestamp}.log"

    def emit(self, record):
        try:
            from config.settings import get_logs_dir
            logs_dir = get_logs_dir()
            
            # Ensure the logs directory exists
            os.makedirs(logs_dir, exist_ok=True)
            
            formatted_record = self.format(record)
            
            # 1. Do NOT write to automation.log (general log file) anymore
            # 2. Do NOT write to file if it is app.py (entry_name == "app")
            is_subprocess_runner = os.getenv("CONNECTIFY_SUBPROCESS_RUNNER") == "true"
            if self.timestamped_filename.startswith("app_"):
                # Ignore Flask app.py logging to files (app log and automation log)
                return
                
            if not is_subprocess_runner:
                # For CLI scripts (e.g. run_email_scraper.py), write to their specific timestamped log file
                timestamped_file = os.path.join(logs_dir, self.timestamped_filename)
                with open(timestamped_file, "a", encoding="utf-8") as f:
                    f.write(formatted_record + "\n")
        except Exception:
            self.handleError(record)


def setup_logger(log_file=None):
    """
    Sets up a logger configured to write to console and dynamically to the active user's logs directory.
    If log_file is specified as a full path, it isolates the filename.
    """
    logger = logging.getLogger("Connectify")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if already setup
    if not logger.handlers:
        filename_base = "automation.log"
        if log_file:
            filename_base = os.path.basename(log_file)
            
        dynamic_handler = DynamicUserFileHandler(filename_base)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        logger.addHandler(dynamic_handler)
        logger.addHandler(stream_handler)
        
    # Automatically clean up logs older than 30 days
    try:
        from config.settings import get_logs_dir
        cleanup_old_logs(get_logs_dir())
    except Exception:
        pass
        
    return logger

# Expose a default configured logger
logger = setup_logger()
