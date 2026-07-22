import os
import sys
import glob
import logging

logger = logging.getLogger(__name__)

def remove_chrome_lockfiles(profile_dir):
    """Recursively find and remove Chrome lockfiles that cause profile lock errors after crash/shutdown."""
    if not os.path.exists(profile_dir):
        return
        
    lock_patterns = ["SingletonLock", "SingletonSocket", "DevToolsActivePort", "LOCK"]
    for root, dirs, files in os.walk(profile_dir):
        for f in files:
            if f in lock_patterns:
                file_path = os.path.join(root, f)
                try:
                    os.remove(file_path)
                    logger.info(f"[Recovery] Removed stale Chrome lockfile: {file_path}")
                except Exception as e:
                    logger.warning(f"[Recovery] Could not remove lockfile {file_path}: {e}")

def cleanup_stale_system_state():
    """Performs full system recovery on startup/shutdown:
    1. Cleans up lingering Chrome/Edge processes for all Connectify profiles.
    2. Removes stale lockfiles from profile directories.
    3. Resets any orphaned 'In Progress' job lead statuses in the database.
    """
    logger.info("[Recovery] Initiating system startup/shutdown recovery & cleanup...")
    
    try:
        from core.integrations.selenium_driver import _kill_lingering_chrome_instances
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        users_dir = os.path.join(base_dir, "users")
        
        if os.path.exists(users_dir):
            for user_folder in os.listdir(users_dir):
                user_path = os.path.join(users_dir, user_folder)
                if os.path.isdir(user_path):
                    for item in os.listdir(user_path):
                        if item.startswith("chrome-profile"):
                            profile_dir = os.path.join(user_path, item)
                            remove_chrome_lockfiles(profile_dir)
                            _kill_lingering_chrome_instances(profile_dir)
    except Exception as e:
        logger.error(f"[Recovery] Error cleaning up Chrome profiles & processes: {e}")

    try:
        from core.storage.database import reset_orphaned_in_progress_statuses
        reset_orphaned_in_progress_statuses()
    except Exception as e:
        logger.error(f"[Recovery] Error resetting orphan job statuses: {e}")

    logger.info("[Recovery] System recovery & cleanup completed successfully.")
