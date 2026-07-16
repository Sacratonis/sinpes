"""One guarded path for every Cloudflare Pages deployment."""

from __future__ import annotations

import hashlib
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import config
from app.repositories.meta_repo import MetaRepository
from app.services.indexnow import queue_indexnow_urls, submit_pending_indexnow


@dataclass(frozen=True)
class DeploymentDecision:
    triggered: bool
    reason: str
    artifact_hash: str


def snapshot_hash(*snapshots: str) -> str:
    digest = hashlib.sha256()
    for snapshot in snapshots:
        digest.update(snapshot.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _month_key(now: datetime) -> str:
    return f"deployment_count_{now:%Y_%m}"


def _as_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: str | None) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clear_stale_build_lock(meta: MetaRepository, now: datetime) -> bool:
    """Release a build lock when Cloudflare never sent its success callback."""
    if meta.get_value("build_in_progress") != "true":
        return False
    triggered_at = _as_float(meta.get_value("last_build_triggered_at"))
    if triggered_at and now.timestamp() - triggered_at < config.DEPLOY_STALE_LOCK_SECONDS:
        return False
    meta.set_value("build_in_progress", "false")
    meta.set_value("pending_snapshot_hash", "")
    meta.set_value("last_build_error", "Cloudflare build confirmation timed out")
    meta.conn.commit()
    return True


def get_deployment_status(conn) -> dict:
    meta = MetaRepository(conn)
    now = datetime.now(timezone.utc)
    _clear_stale_build_lock(meta, now)
    return {
        "in_progress": meta.get_value("build_in_progress") == "true",
        "triggered_at": meta.get_value("last_build_triggered_at"),
        "successful_at": meta.get_value("last_successful_build_at"),
        "last_error": meta.get_value("last_build_error"),
        "last_source": meta.get_value("last_deployment_source"),
        "monthly_count": _as_int(meta.get_value(_month_key(now))),
        "monthly_limit": config.DEPLOY_MONTHLY_LIMIT,
        "last_successful_hash": meta.get_value("last_successful_snapshot_hash"),
        "pending_hash": meta.get_value("pending_snapshot_hash"),
    }


def trigger_deployment(
    conn,
    *,
    artifact_hash: str,
    source: str,
    indexnow_urls: list[str] | None = None,
    force: bool = False,
    automatic: bool = False,
    now: datetime | None = None,
) -> DeploymentDecision:
    """Apply all deploy guards and invoke the Pages hook once when allowed."""
    meta = MetaRepository(conn)
    now = now or datetime.now(timezone.utc)
    timestamp = now.timestamp()
    _clear_stale_build_lock(meta, now)

    if not config.CF_PAGES_DEPLOY_HOOK_URL:
        return DeploymentDecision(False, "Cloudflare deploy hook is not configured", artifact_hash)

    if not force and artifact_hash == meta.get_value("last_successful_snapshot_hash"):
        return DeploymentDecision(False, "snapshot is unchanged", artifact_hash)

    last_triggered = _as_float(meta.get_value("last_build_triggered_at"))
    build_is_recent = last_triggered and timestamp - last_triggered < config.DEPLOY_STALE_LOCK_SECONDS
    if not force and meta.get_value("build_in_progress") == "true" and build_is_recent:
        return DeploymentDecision(False, "a deployment is already running", artifact_hash)

    month_key = _month_key(now)
    monthly_count = _as_int(meta.get_value(month_key))
    if not force and monthly_count >= config.DEPLOY_MONTHLY_LIMIT:
        return DeploymentDecision(False, "monthly deployment safety limit reached", artifact_hash)

    if not force and automatic:
        automatic_date = meta.get_value("last_automatic_deploy_date")
        if automatic_date == now.date().isoformat():
            return DeploymentDecision(False, "automatic deployment already used today", artifact_hash)

    if not force and not automatic and last_triggered:
        if timestamp - last_triggered < config.DEPLOY_MANUAL_COOLDOWN_SECONDS:
            return DeploymentDecision(False, "manual deployment cooldown is active", artifact_hash)

    meta.set_value("build_in_progress", "true")
    meta.set_value("last_build_triggered_at", str(timestamp))
    meta.set_value("last_build_error", "")
    meta.set_value("last_deployment_source", source)
    meta.set_value("pending_snapshot_hash", artifact_hash)
    if indexnow_urls:
        queue_indexnow_urls(conn, indexnow_urls)
    conn.commit()

    try:
        request = urllib.request.Request(config.CF_PAGES_DEPLOY_HOOK_URL, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            if getattr(response, "status", 200) >= 300:
                raise RuntimeError(f"Cloudflare deploy hook returned HTTP {response.status}")
    except Exception as exc:
        meta.set_value("build_in_progress", "false")
        meta.set_value("last_build_error", str(exc))
        meta.set_value("pending_snapshot_hash", "")
        conn.commit()
        raise

    meta.set_value(month_key, str(monthly_count + 1))
    if automatic:
        meta.set_value("last_automatic_deploy_date", now.date().isoformat())
    conn.commit()
    return DeploymentDecision(True, "deployment triggered", artifact_hash)


def confirm_deployment_success(conn) -> dict:
    """Confirm only a deployment that the application currently expects."""
    meta = MetaRepository(conn)
    if meta.get_value("build_in_progress") != "true":
        return {"status": "ignored", "reason": "no deployment is awaiting confirmation"}

    pending_hash = meta.get_value("pending_snapshot_hash")
    if not pending_hash:
        return {"status": "ignored", "reason": "deployment has no pending snapshot hash"}

    meta.set_value("last_successful_build_at", str(time.time()))
    meta.set_value("last_successful_snapshot_hash", pending_hash)
    meta.set_value("pending_snapshot_hash", "")
    meta.set_value("build_in_progress", "false")
    meta.set_value("last_build_error", "")
    conn.commit()
    indexnow = submit_pending_indexnow(conn)
    return {"status": "ok", "snapshot_hash": pending_hash, "indexnow": indexnow}
