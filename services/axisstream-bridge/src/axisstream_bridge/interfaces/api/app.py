"""FastAPI OpenAPI 3.1 Integration Gateway + Real-Time SSE Stream + RFC 9457 Problem JSON."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
from typing import Any

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from axisstream_bridge.application.demo_provider import DemoAxisStreamProvider
from axisstream_bridge.application.live_provider import LiveAxisStreamProvider
from axisstream_bridge.application.sync_service import (
    IncrementalSyncOrchestrator,
    SseEventHub,
)
from axisstream_bridge.domain.models import ProjectForecastBundle, WeatherForecastReport
from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import AxisStreamError
from axisstream_bridge.core.logging import configure_logging, get_or_create_correlation_id
from axisstream_bridge.domain.normalizers import validate_safe_path_segment
from axisstream_bridge.infrastructure.http.circuit_breaker import CircuitBreaker, CircuitState
from axisstream_bridge.infrastructure.storage.state_store import SqliteStateStore
from axisstream_bridge.interfaces.api.security import (
    CorrelationAndSecurityMiddleware,
    require_api_key,
)

logger = logging.getLogger("axisstream_bridge.api")


def _problem_response(
    *,
    status_code: int,
    title: str,
    detail: str,
    error_type: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://errors.axisstream-bridge.local/{error_type.lower()}",
            "title": title,
            "status": status_code,
            "detail": detail,
            "correlation_id": get_or_create_correlation_id(),
        },
    )


def create_app(
    settings: BridgeSettings | None = None,
    *,
    provider: Any | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    state_store: SqliteStateStore | None = None,
    enable_background_sync: bool = True,
) -> FastAPI:
    cfg = settings or BridgeSettings()
    configure_logging(cfg.log_level)

    store = state_store or SqliteStateStore(
        cfg.sqlite_path,
        encryption_key=cfg.encryption_key.get_secret_value(),
    )
    cb = circuit_breaker or CircuitBreaker(
        failure_threshold=cfg.circuit_failure_threshold,
        recovery_timeout_sec=cfg.circuit_recovery_sec,
    )
    hub = SseEventHub()
    if provider is not None:
        active_provider = provider
    else:
        active_provider = (
            LiveAxisStreamProvider(cfg, circuit_breaker=cb)
            if cfg.mode == "live"
            else DemoAxisStreamProvider()
        )
    orchestrator = IncrementalSyncOrchestrator(
        provider=active_provider,
        state_store=store,
        event_hub=hub,
        local_timezone=cfg.local_timezone,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop_event = asyncio.Event()
        try:
            await orchestrator.sync_all()
        except Exception as exc:
            logger.warning("Initial sync cycle failed (fail-open startup)", extra={"error": str(exc)})

        async def _loop() -> None:
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=cfg.sync_interval_sec)
                except asyncio.TimeoutError:
                    try:
                        await orchestrator.sync_all()
                    except Exception as exc:
                        logger.error("Background sync cycle failed", extra={"error": str(exc)})

        task = asyncio.create_task(_loop()) if enable_background_sync else None
        try:
            yield
        finally:
            stop_event.set()
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if state_store is None:
                store.close()
            if hasattr(active_provider, "aclose"):
                await active_provider.aclose()

    app = FastAPI(
        title="AxisStream ISO Integration Bridge API",
        version="1.0.0",
        description="ISO/IEC 42010, 27001, 25010 & 29119 compliant read-only real-time AxisStream gateway.",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationAndSecurityMiddleware)
    app.state.orchestrator = orchestrator
    app.state.circuit_breaker = cb
    app.state.state_store = store
    app.state.event_hub = hub

    @app.exception_handler(AxisStreamError)
    async def _handle_domain_error(_req: Request, exc: AxisStreamError) -> JSONResponse:
        return _problem_response(
            status_code=exc.http_status_hint,
            title=exc.code,
            detail=str(exc),
            error_type=exc.code,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_req_validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem_response(
            status_code=422,
            title="VALIDATION_ERROR",
            detail=str(exc.errors()),
            error_type="validation_error",
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_req: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled gateway exception", extra={"error_type": type(exc).__name__})
        return _problem_response(
            status_code=500,
            title="INTERNAL_SERVER_ERROR",
            detail="Internal bridge error; inspect correlation_id in server logs",
            error_type="internal_server_error",
        )

    @app.get("/health/live", tags=["Health"])
    async def health_live() -> dict[str, Any]:
        return {"status": "UP", "mode": cfg.mode}

    @app.get("/health/ready", tags=["Health"])
    async def health_ready() -> JSONResponse:
        cb_state = cb.state
        store_ok = store.is_healthy()
        sync_failed = orchestrator.sync_count == 0 and bool(orchestrator.last_error)
        ready = (cb_state != CircuitState.OPEN) and store_ok and (not sync_failed)
        code = 200 if ready else 503
        return JSONResponse(
            status_code=code,
            content={
                "status": "READY" if ready else "DEGRADED",
                "mode": cfg.mode,
                "circuit_breaker": cb_state.value,
                "state_store": "UP" if store_ok else "DOWN",
                "sync_count": orchestrator.sync_count,
                "projects_cached": len(orchestrator.get_projects()),
                "last_error": orchestrator.last_error,
            },
        )

    @app.get("/metrics", tags=["Observability"])
    async def metrics() -> dict[str, Any]:
        return {
            "mode": cfg.mode,
            "sync_count": orchestrator.sync_count,
            "last_sync_utc": orchestrator.last_sync_utc.isoformat()
            if orchestrator.last_sync_utc
            else None,
            "last_error": orchestrator.last_error,
            "circuit_breaker_state": cb.state.value,
            "circuit_failure_count": cb.failure_count,
            "projects_cached": len(orchestrator.get_projects()),
        }

    api_v1 = APIRouter(prefix="/api/v1", dependencies=[require_api_key(cfg)])

    @api_v1.get("/projects", tags=["Projects"])
    async def list_projects() -> dict[str, Any]:
        items = [p.model_dump(mode="json") for p in orchestrator.get_projects()]
        return {
            "data": items,
            "count": len(items),
            "mode": cfg.mode,
            "sync_count": orchestrator.sync_count,
            "last_error": orchestrator.last_error,
        }

    @api_v1.get("/projects/{project_id}/devices", tags=["Devices"])
    async def list_devices(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        items = [d.model_dump(mode="json") for d in orchestrator.get_devices(pid)]
        return {"data": items, "count": len(items)}

    @api_v1.get("/projects/{project_id}/telemetry", tags=["Telemetry"])
    async def get_telemetry(
        project_id: str,
        device_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        snaps = orchestrator.get_telemetry(pid)
        if device_id:
            snaps = [s for s in snaps if s.device_id == device_id or s.external_id == device_id]
        return {"data": [s.model_dump(mode="json") for s in snaps], "count": len(snaps)}

    @api_v1.get("/projects/{project_id}/telemetry/history", tags=["Telemetry"])
    async def get_telemetry_history(
        project_id: str,
        device_id: str | None = Query(default=None),
        hours: int = Query(default=24, ge=1, le=720),
    ) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        did = validate_safe_path_segment(device_id, "device_id") if device_id else None
        rows = orchestrator.get_telemetry_history(pid, device_id=did, hours=hours)
        return {
            "project_id": pid,
            "device_id": did,
            "hours": hours,
            "data": rows,
            "count": len(rows),
        }

    @api_v1.get("/projects/{project_id}/fields", tags=["Location"])
    async def list_fields(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        items = [f.model_dump(mode="json") for f in orchestrator.get_fields(pid)]
        return {"data": items, "count": len(items)}

    @api_v1.get("/projects/{project_id}/assets", tags=["Assets"])
    async def list_assets(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        items = [a.model_dump(mode="json") for a in orchestrator.get_assets(pid)]
        return {"data": items, "count": len(items)}

    @api_v1.get("/projects/{project_id}/alerts/policies", tags=["Alerts"])
    async def list_alert_policies(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        items = [p.model_dump(mode="json") for p in orchestrator.get_alert_policies(pid)]
        return {"data": items, "count": len(items)}

    @api_v1.get("/projects/{project_id}/alerts/history", tags=["Alerts"])
    async def list_alert_history(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        items = [h.model_dump(mode="json") for h in orchestrator.get_alert_history(pid)]
        return {"data": items, "count": len(items)}

    @api_v1.get("/projects/{project_id}/providers", tags=["Providers"])
    async def list_providers(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        items = [p.model_dump(mode="json") for p in orchestrator.get_providers(pid)]
        return {"data": items, "count": len(items)}

    @api_v1.get("/projects/{project_id}/exchange/weather", tags=["API Exchange"])
    async def get_exchange_weather(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        tokens = [t.model_dump(mode="json") for t in orchestrator.get_exchange_tokens(pid)]
        rows = [r.model_dump(mode="json") for r in orchestrator.get_exchange_weather(pid)]
        return {"tokens": tokens, "data": rows, "count": len(rows)}

    @api_v1.get("/projects/{project_id}/forecast", tags=["Weather Forecast"])
    async def get_weather_forecast(project_id: str) -> dict[str, Any]:
        pid = validate_safe_path_segment(project_id, "project_id")
        bundle = orchestrator.get_forecast(pid)
        if bundle is None:
            bundle = ProjectForecastBundle(
                project_id=pid,
                met_norway=WeatherForecastReport(provider="MET Norway", status="DISCONNECTED"),
                janes_weather=WeatherForecastReport(provider="Jane's Weather", status="DISCONNECTED"),
            )
        return bundle.model_dump(mode="json")

    @api_v1.get("/metrics", tags=["Observability"])
    async def api_v1_metrics() -> dict[str, Any]:
        return await metrics()

    @api_v1.get("/security/posture", tags=["Security"])
    async def security_posture() -> dict[str, Any]:
        return {
            "encryption_at_rest": store.encryption_enabled,
            "encryption_algorithm": store.encryption_algorithm,
            "tls_strict_host_suffix": cfg.allowed_host_suffix,
            "auth_mode": cfg.auth_mode,
            "read_only_sync": True,
            "rate_limit_rps": cfg.rate_limit_rps,
            "circuit_breaker_state": cb.state.value,
        }

    @api_v1.post("/sync/trigger", tags=["Sync"])
    async def trigger_sync() -> dict[str, Any]:
        return await orchestrator.sync_all()

    @api_v1.get("/stream", tags=["Real-Time SSE"])
    async def stream_events(request: Request) -> StreamingResponse:
        q = hub.subscribe()

        async def _event_gen():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"event: {evt.event_type}\ndata: {json.dumps(evt.model_dump(mode='json'))}\n\n"
                    except asyncio.TimeoutError:
                        yield "event: heartbeat\ndata: {\"status\":\"alive\"}\n\n"
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(_event_gen(), media_type="text/event-stream")

    app.include_router(api_v1)
    return app


app = create_app()
