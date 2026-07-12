import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- YOUR EXISTING IMPORTS ---
from app.db.database import init_db, get_db_connection, run_migrations 
from app.routers import build_verify, webhook, snapshot, edit, category_admin, queue_status, blog_admin
from app.services.queue_manager import start_scheduler

# --- NEW IMPORTS FOR FIXES ---
from app.core.config import config 
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware, request_id_ctx_var
from app.core.errors import SinpesError

# --- STRUCTURED LOGGING SETUP ---
logger = setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Run our new safe migrations (Adds the retry/fail columns automatically)
    run_migrations()
    
    # 3. Start the Scheduler (Your existing logic)
    logger.info("Starting SINPES API & Scheduler...")
    scheduler = start_scheduler()
    
    yield
    
    # 4. Safe Shutdown (Fixes Review 2, Point 4 - prevents crash if startup fails)
    if scheduler and getattr(scheduler, 'running', False):
        logger.info("Shutting down Scheduler...")
        scheduler.shutdown(wait=False)

app = FastAPI(title="SINPES API", version="1.0", lifespan=lifespan)

# --- CORS CONFIGURATION (Driven by Environment) ---
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS, # Replaces your hardcoded list
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.exception_handler(SinpesError)
async def sinpes_error_handler(request: Request, exc: SinpesError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.__class__.__name__,
            "request_id": request_id_ctx_var.get()
        }
    )

# --- MOUNT ROUTERS (Your existing logic) ---
app.include_router(build_verify.router)
app.include_router(snapshot.router)
app.include_router(webhook.router)
app.include_router(edit.router)
app.include_router(category_admin.router)
app.include_router(queue_status.router)
app.include_router(blog_admin.router)

# --- ENDPOINTS ---

@app.get("/health")
def health_check():
    """Shallow health check for Load Balancers / Uptime Monitors."""
    return {"status": "ok", "system": "SINPES Vault", "environment": config.APP_ENV}

