"""FastAPI skin over `metrics.py`: the dashboard page and the read-only API.

The route names are fixed on purpose. Every service in the lab answering the
same `/api/metrics/*` shapes is the whole point — one dashboard file works
everywhere, `homelab-health` can ask any service the same question, and a new
server gets observability by copying three files rather than by inventing a
fourth convention.

Mount it in one line:

    from metrics_api import build_router
    app.include_router(build_router(metrics))

Everything here is read-only. Nothing in this module can change what the
service does, which is why it is safe to leave unauthenticated on the LAN the
way the rest of the lab is.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

from metrics import Metrics

DASHBOARD_HTML = Path(__file__).with_name("dashboard.html")

# Callers that want to be named rather than guessed at set one of these. Nothing
# is required to — the resolver falls back to reverse DNS and /proc — but a
# caller that says who it is always wins, and costs one header.
NAME_HEADER = "x-client-name"
NAME_PARAM = "client"


def actor_args(scope: Request | WebSocket) -> dict[str, Any]:
    """Pull the actor hints out of a request or websocket.

    Splat straight into `metrics.session(...)`:

        with metrics.session("play", **actor_args(request)) as s:
            ...
    """
    client = getattr(scope, "client", None)
    declared = scope.headers.get(NAME_HEADER) or scope.query_params.get(NAME_PARAM)
    return {
        "ip": client.host if client else None,
        "port": client.port if client else None,
        "declared": declared,
        "user_agent": scope.headers.get("user-agent"),
    }


def build_router(metrics: Metrics, *, dashboard: Path | None = None, prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix)
    page = dashboard or DASHBOARD_HTML

    @router.get("/healthz")
    def healthz() -> dict[str, Any]:
        """Liveness, cheap enough to poll. `homelab-health` reads this."""
        return {"ok": True, "service": metrics.service, "uptime_s": round(metrics.uptime_s, 1)}

    @router.get("/metrics", include_in_schema=False)
    @router.get("/metrics/", include_in_schema=False)
    def dashboard_page() -> HTMLResponse:
        if not page.exists():
            return HTMLResponse("<h1>dashboard.html is missing</h1>", status_code=500)
        # Read per request rather than at import: editing the page and hitting
        # refresh is how you actually work on it.
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @router.get("/api/metrics/schema")
    def schema() -> dict[str, Any]:
        """What this service records, so the generic dashboard can render it."""
        return {
            "service": metrics.service,
            "title": metrics.schema.get("title", metrics.service),
            "version": metrics.version,
            "kinds": metrics.schema.get("kinds", {}),
            "totals": metrics.schema.get("totals", []),
            "status": metrics.schema.get("status", []),
        }

    @router.get("/api/metrics/status")
    def status() -> dict[str, Any]:
        return metrics.status()

    @router.get("/api/metrics/actors")
    def actors(days: float | None = Query(None, ge=0)) -> list[dict[str, Any]]:
        return metrics.actors(days=days)

    @router.get("/api/metrics/sessions")
    def sessions(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        kind: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        hours: float | None = Query(None, ge=0),
    ) -> dict[str, Any]:
        since = time.time() - hours * 3600 if hours else None
        return metrics.sessions(
            limit=limit, offset=offset, kind=kind, actor=actor, status=status, since=since
        )

    @router.get("/api/metrics/events")
    def events(
        limit: int = Query(200, ge=1, le=1000),
        since_id: int | None = None,
        level: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return metrics.events(limit=limit, since_id=since_id, level=level, session_id=session_id)

    @router.get("/api/metrics/series")
    def series(
        bucket: str = Query("hour", pattern="^(hour|day)$"),
        days: float = Query(7.0, gt=0, le=400),
    ) -> dict[str, Any]:
        return metrics.series(bucket=bucket, days=days)

    @router.get("/api/metrics/export")
    def export(limit: int = Query(5000, ge=1, le=50000)) -> JSONResponse:
        """The raw log, for when a question outgrows the dashboard."""
        return JSONResponse(
            {
                "service": metrics.service,
                "exported_at": time.time(),
                "sessions": metrics.sessions(limit=limit)["rows"],
                "events": metrics.events(limit=limit),
            }
        )

    return router
