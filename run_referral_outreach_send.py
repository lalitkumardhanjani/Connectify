import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')
import signal
import sys
from pipelines.linkedin_outreach.services.referral_outreach import run_phase_two_messaging

def handle_sigterm(signum, frame):
    print(f"\n[SYSTEM] Received termination signal {signum}. Closing Chrome and exiting...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    from core.logging.config import logger
    logger.info("============================================================")
    logger.info("LinkedIn Referral Messaging Runner Initiated")
    logger.info("============================================================")
    
    run_phase_two_messaging()
