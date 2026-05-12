import sys
import logging
import traceback

# Configure logging for the wrapper
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OROVA-Wrapper")

def run_nova():
    try:
        logger.info("🚀 Attempting to launch OROVA Nova core (app.main)...")
        from app.main import main
        main()
    except Exception as e:
        logger.error("🔥 CRITICAL FAILURE: OROVA Nova failed to start.")
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(f"Error Message: {str(e)}")
        logger.error("---- FULL TRACEBACK ----")
        traceback.print_exc()
        logger.error("------------------------")
        sys.exit(1)

if __name__ == "__main__":
    run_nova()
