import shutil
import time
import os
from app.core.config import config
from app.ingestion.storage_archive import upload_to_r2

def backup_database():
    timestamp = time.strftime("%Y-%m-%d")
    backup_path = f"/tmp/sinpes-{timestamp}.db"
    
    try:
        # Safely copy the database file while in WAL mode
        shutil.copy(config.DATABASE_PATH, backup_path)
        
        with open(backup_path, 'rb') as f:
            data = f.read()
            
        upload_to_r2(
            data=data,
            key=f"backups/sinpes-{timestamp}.db",
            content_type="application/octet-stream",
            cache_control="private"
        )
    finally:
        # Clean up the temporary copy from the Droplet
        if os.path.exists(backup_path):
            os.remove(backup_path)