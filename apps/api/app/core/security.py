import ipaddress
import hmac
import logging
from fastapi import Request, HTTPException, status
from app.core.config import config

logger = logging.getLogger(__name__)

def get_client_ip(request: Request) -> str:
    """
    Extract the true client IP, respecting Cloudflare and standard proxies.
    """
    if cf_ip := request.headers.get("CF-Connecting-IP"):
        return cf_ip
    
    if xff := request.headers.get("X-Forwarded-For"):
        return xff.split(",")[0].strip()
    
    if xri := request.headers.get("X-Real-IP"):
        return xri.strip()
    
    if request.client:
        return request.client.host
    
    logger.warning("Could not determine client IP – using loopback fallback")
    return "127.0.0.1"

def verify_webhook_ip(request: Request) -> None:
    """
    Validates that the incoming request originates from a Telegram-authorized IP.
    """
    client_ip_str = get_client_ip(request)
    
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        logger.warning(f"Invalid IP format received: {client_ip_str}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client IP address"
        )
    
    allowed_networks = []
    if hasattr(config, "WEBHOOK_ALLOWED_IPS") and config.WEBHOOK_ALLOWED_IPS:
        for net_str in config.WEBHOOK_ALLOWED_IPS:
            try:
                allowed_networks.append(ipaddress.ip_network(net_str.strip()))
            except ValueError:
                logger.error(f"Invalid CIDR in config.WEBHOOK_ALLOWED_IPS: {net_str}")
                continue
    
    if not allowed_networks:
        if config.APP_ENV == "production":
            logger.critical("WEBHOOK_ALLOWED_IPS is empty in production – blocking ALL requests!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfiguration: no IPs allowed"
            )
        else:
            logger.warning("WEBHOOK_ALLOWED_IPS is empty – skipping IP validation in dev mode")
            return  
    
    allowed = any(client_ip in net for net in allowed_networks)
    
    if not allowed:
        logger.error(
            f"BLOCKED: Unauthorized webhook attempt from {client_ip_str} "
            f"(allowed networks: {[str(n) for n in allowed_networks]})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: IP not in allowed range"
        )
    
    logger.debug(f"Allowed webhook from {client_ip_str}")
    return

def verify_build_secret(request: Request) -> None:
    """
    Validates the x-build-secret header for internal admin endpoints.
    FAILS CLOSED: If the secret is missing from config, it blocks all requests.
    """
    expected = getattr(config, "BUILD_SECRET", None)
    
    if not expected:
        logger.critical("BUILD_SECRET is not set in config! Blocking admin access.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: missing build secret"
        )
    
    secret = request.headers.get("x-build-secret")
    if not secret or not hmac.compare_digest(secret, expected):
        logger.warning(f"Invalid build secret provided (from {get_client_ip(request)})")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing build secret"
        )
        
    return
