import logging
import uvicorn
from kvopt.server.main import app

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting KV-OptKit server in debug mode...")
    uvicorn.run(
        "kvopt.server.main:app",
        host="0.0.0.0",
        port=9000,
        log_level="debug",
        reload=True
    )
