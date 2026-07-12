import os
import sys
from app.db.database import get_db
from app.repositories.queue_repo import QueueRepository
from app.repositories.meta_repo import MetaRepository
from app.services.queue_manager import release_next_from_queue

print("--- DB STATE ---")
with get_db() as conn:
    q_repo = QueueRepository(conn)
    m_repo = MetaRepository(conn)
    
    pending = q_repo.get_next_pending()
    print(f"Next pending item: {pending}")
    
    last_release_str = m_repo.get_value('last_queue_release_at')
    print(f"last_queue_release_at: {last_release_str}")

print("\n--- FORCING QUEUE RELEASE ---")
try:
    release_next_from_queue()
    print("Release function finished.")
except Exception as e:
    import traceback
    traceback.print_exc()
