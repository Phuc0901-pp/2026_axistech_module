"""AxisStream Alert, Provider, and API Exchange (`tbncorp.weather`) clients."""

from __future__ import annotations

import logging
from typing import Any

from axisstream_bridge.domain.models import (
    AlertCondition,
    AlertHistoryItem,
    AlertPolicy,
    ProviderConnection,
    WeatherExchangeRow,
)
from axisstream_bridge.domain.normalizers import (
    parse_iso_timestamp,
    parse_numeric,
    validate_safe_path_segment,
)
from axisstream_bridge.infrastructure.axisstream.v2_client import auto_paginate
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient

logger = logging.getLogger("axisstream_bridge.acl.alerts")


class AxisStreamAlertClient:
    """Adapter implementing AlertPort & provider config queries."""

    def __init__(
        self,
        http: ResilientHttpClient,
        v2_base_url: str = "https://v2.api.axisstream.co",
        provider_base_url: str = "https://provider.api.axisstream.co",
    ) -> None:
        self._http = http
        self._v2_base_url = v2_base_url.rstrip("/")
        self._provider_base_url = provider_base_url.rstrip("/")

    async def list_alert_templates(self) -> list[dict[str, Any]]:
        payload = await self._http.request_json("GET", f"{self._v2_base_url}/api/alert/templates")
        return list(payload) if isinstance(payload, list) else []

    async def list_alert_policies(self, project_id: str) -> list[AlertPolicy]:
        pid = validate_safe_path_segment(project_id, "project_id")
        payload = await self._http.request_json(
            "GET", f"{self._v2_base_url}/api/alert/policies/project/{pid}"
        )
        rows = payload if isinstance(payload, list) else (payload or {}).get("data", [])
        policies: list[AlertPolicy] = []
        for raw in rows:
            if not raw.get("id"):
                continue
            dev = raw.get("device") or {}
            conds = [
                AlertCondition(
                    name=str(c.get("name", "")),
                    condition_type=str(c.get("type", "value")),
                    column=str(c.get("column", "")),
                    operator=str((c.get("operator") or {}).get("symbol", "")),
                    threshold=str(c.get("value", "")),
                )
                for c in (raw.get("policies") or [])
            ]
            policies.append(
                AlertPolicy(
                    id=str(raw["id"]),
                    project_id=pid,
                    name=str(raw.get("name", "")),
                    entity_id=str(raw.get("entityId", "")),
                    entity_type=str(raw.get("entityType", "device")),
                    device_name=str(dev.get("name", "")),
                    status=str(raw.get("status", "PAUSED")),
                    priority=str(raw.get("priority", "MEDIUM")),
                    frequency_window_minutes=int(raw.get("frequencyWindowMinutes") or 60),
                    notification_types=[str(x) for x in (raw.get("notificationTypes") or [])],
                    conditions=conds,
                    message_template=str(raw.get("messageTemplate", "")),
                )
            )
        return policies

    async def list_alert_history(
        self, project_id: str, limit: int = 200
    ) -> list[AlertHistoryItem]:
        pid = validate_safe_path_segment(project_id, "project_id")
        payload = await self._http.request_json(
            "GET",
            f"{self._v2_base_url}/api/alert/project/{pid}",
            params={"page": 1, "limit": limit},
        )
        if payload is None:
            return []
        rows = payload if isinstance(payload, list) else (payload.get("data", []) if isinstance(payload, dict) else [])
        history: list[AlertHistoryItem] = []
        for raw in rows:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            pol_obj = raw.get("alertPolicy") or {}
            dev_obj = raw.get("device") or {}
            notif_obj = raw.get("notificationLogCount") or {}
            history.append(
                AlertHistoryItem(
                    id=str(raw["id"]),
                    project_id=pid,
                    policy_name=str(
                        pol_obj.get("name")
                        or raw.get("policyName")
                        or raw.get("title")
                        or raw.get("name")
                        or ""
                    ),
                    device_name=str(dev_obj.get("name") or raw.get("deviceName") or ""),
                    rule_description=str(
                        raw.get("body")
                        or raw.get("ruleDescription")
                        or raw.get("message")
                        or raw.get("title")
                        or ""
                    ),
                    delivery_status=str(raw.get("status") or "DELIVERED"),
                    notification_count=int(
                        notif_obj.get("logCount")
                        if notif_obj.get("logCount") is not None
                        else (raw.get("notificationCount") or 0)
                    ),
                    triggered_at_utc=parse_iso_timestamp(
                        raw.get("originalEventTimestamp")
                        or raw.get("createdAt")
                        or raw.get("triggeredAt")
                    ),
                )
            )
        return history

    async def list_provider_configs(self) -> list[ProviderConnection]:
        payload = await self._http.request_json(
            "GET", f"{self._provider_base_url}/providers/connection-config"
        )
        rows = payload if isinstance(payload, list) else (payload or {}).get("data", [])
        return [
            ProviderConnection(
                id=str(r.get("id", r.get("code", ""))),
                name=str(r.get("name", "")),
                code=str(r.get("code", "")),
                status=str(r.get("status", "CONNECTED")),
            )
            for r in rows
            if r.get("id") or r.get("code")
        ]


class AxisStreamExchangeClient:
    """Normalizes the 17-column `tbncorp.weather` API Exchange dataset."""

    WEATHER_COLUMNS = (
        "atmos_pressure_avg",
        "temperature_avg",
        "deltat_avg",
        "dewpoint_avg",
        "humidity_avg",
        "uv_index_avg",
        "wind_dir_deg_avg",
        "wind_speed_avg",
        "solar_rad_avg",
        "code",
        "wind_speed_min",
        "msl_pressure",
        "rainfall",
        "time",
        "rainfall_total",
        "wind_dir_var_avg",
        "wind_speed_max",
    )

    def __init__(self, http: ResilientHttpClient, data_base_url: str = "https://data.api.axisstream.co") -> None:
        self._http = http
        self._data_base_url = data_base_url.rstrip("/")

    @staticmethod
    def map_weather_row(raw: dict[str, Any]) -> WeatherExchangeRow | None:
        ts = parse_iso_timestamp(raw.get("time"))
        if ts is None:
            return None
        return WeatherExchangeRow(
            code=str(raw.get("code") or ""),
            time=ts,
            temperature_avg=parse_numeric(raw.get("temperature_avg")),
            humidity_avg=parse_numeric(raw.get("humidity_avg")),
            deltat_avg=parse_numeric(raw.get("deltat_avg")),
            dewpoint_avg=parse_numeric(raw.get("dewpoint_avg")),
            atmos_pressure_avg=parse_numeric(raw.get("atmos_pressure_avg")),
            msl_pressure=parse_numeric(raw.get("msl_pressure")),
            rainfall=parse_numeric(raw.get("rainfall")),
            rainfall_total=parse_numeric(raw.get("rainfall_total")),
            wind_speed_avg=parse_numeric(raw.get("wind_speed_avg")),
            wind_speed_min=parse_numeric(raw.get("wind_speed_min")),
            wind_speed_max=parse_numeric(raw.get("wind_speed_max")),
            wind_dir_deg_avg=parse_numeric(raw.get("wind_dir_deg_avg")),
            wind_dir_var_avg=parse_numeric(raw.get("wind_dir_var_avg")),
            solar_rad_avg=parse_numeric(raw.get("solar_rad_avg")),
            uv_index_avg=parse_numeric(raw.get("uv_index_avg")),
        )

    async def fetch_weather_exchange(
        self,
        org_code: str,
        project_id: str,
        limit: int = 15000,
    ) -> list[WeatherExchangeRow]:
        org = validate_safe_path_segment(org_code, "org_code")
        pid = validate_safe_path_segment(project_id, "project_id")
        payload = await self._http.request_json(
            "GET",
            f"{self._data_base_url}/exchange/{org}/weather",
            params={"projectId": pid, "limit": min(max(1, limit), 15000)},
        )
        rows = payload if isinstance(payload, list) else (payload or {}).get("data", [])
        mapped: list[WeatherExchangeRow] = []
        for raw in rows:
            item = self.map_weather_row(raw)
            if item is not None:
                mapped.append(item)
        return mapped
