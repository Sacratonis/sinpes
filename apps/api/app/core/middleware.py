import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import contextvars

# Global context var for request ID tracing
request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="system")

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Prefer client-provided request ID (useful for chained traces), fallback to generating one
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Set the ID in context for logging
        token = request_id_ctx_var.set(req_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx_var.reset(token)
