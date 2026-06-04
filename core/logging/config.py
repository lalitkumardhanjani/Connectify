import logging
import os

class DynamicUserFileHandler(logging.Handler):
    """
    A logging Handler that dynamically determines the active user's log folder
    at record-write time, keeping user logs completely isolated.
    """
    def __init__(self, filename_base="automation.log"):
        super().__init__()
        self.filename_base = filename_base
        self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    def emit(self, record):
        try:
            from config.settings import get_logs_dir
            logs_dir = get_logs_dir()
            log_file = os.path.join(logs_dir, self.filename_base)
            
            # Ensure the logs directory exists
            os.makedirs(logs_dir, exist_ok=True)
            
            # Append log message
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(self.format(record) + "\n")
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
        
    return logger

# Expose a default configured logger
logger = setup_logger()
