# Vision service entry
import logging
import os
import uvicorn
from vision.app import app

if __name__ == "__main__":
    level_name = os.getenv("VISION_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level, format="%(name)s %(levelname)s: %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=9000, access_log=False)
