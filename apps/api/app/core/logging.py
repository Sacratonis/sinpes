import logging
import json
from datetime import datetime, timezone
from app.core.middleware import request_id_ctx_var

class JSONLogFormatter(logging.Formatter):
    """
    Formats logs as JSON lines for ingestion by tools like Promtail/Loki, Datadog, 
    or just easier structured parsing from the systemd journal.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get()
        }
        
        # Append exception details if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Wipe out any default handlers FastAPI/Uvicorn might have attached
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JSONLogFormatter())
    logger.addHandler(stream_handler)
    
    # Silence overly verbose third-party loggers if necessary
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    
    return logging.getLogger("sinpes")
