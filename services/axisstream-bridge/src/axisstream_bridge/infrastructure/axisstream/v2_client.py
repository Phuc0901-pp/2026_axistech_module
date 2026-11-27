"""AxisStream v2 Core Metadata API client and Anti-Corruption Layer mappers."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from axisstream_bridge.core.exceptions import AxisStreamError, SchemaDriftError
from axisstream_bridge.domain.models import (
    Asset,
    Coordinates,
    Device,
    ExchangeDataset,
    ExchangeTokenInfo,
    FieldLocation,
    GeoPolygonSite,
    Organisation,
    Project,
    ProjectAccess,
    ProviderConnection,
)
from axisstream_bridge.domain.normalizers import (
    parse_iso_timestamp,
    parse_numeric,
    validate_geojson_geometry,
    validate_safe_path_segment,
)
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient

logger = logging.getLogger("axisstream_bridge.acl.v2")


def _warn_unexpected_keys(entity: str, raw: dict[str, Any], expected: set[str]) -> None:
    extra = set(raw.keys()) - expected
    if extra:
        logger.warning(
            "Schema drift detected: unexpected upstream keys",
            extra={"entity": entity, "unexpected_keys": sorted(extra)},
        )


async def auto_paginate(
    fetch_page: Callable[[int, int], Awaitable[Any]],
    *,
    limit: int = 100,
    max_pages: int = 100,
) -> list[dict[str, Any]]:
    """Iterate AxisStream `{data, meta}` paginated endpoints with safety cap."""
    items: list[dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        payload = await fetch_page(page, limit)
        if payload is None:
            break
        if isinstance(payload, list):
            items.extend(payload)
            break
        if not isinstance(payload, dict):
            raise SchemaDriftError(f"Expected dict or list for paginated payload, got {type(payload).__name__}")
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise SchemaDriftError("Paginated payload 'data' field must be a list")
        items.extend(rows)
        meta = payload.get("meta") or {}
        if not meta.get("hasNextPage", False):
            break
        page += 1
    else:
        raise SchemaDriftError(f"Pagination exceeded max_pages={max_pages} safety cap")
    return items


class ProjectMapper:
    _EXPECTED = {"id", "name", "description", "organisation", "role", "access", "packageSummary"}

    @classmethod
    def map_one(cls, raw: dict[str, Any]) -> Project:
        if "id" not in raw or not raw["id"]:
            raise SchemaDriftError("Project missing required primary key 'id'")
        _warn_unexpected_keys("Project", raw, cls._EXPECTED)
        org_raw = raw.get("organisation") or {}
        if not org_raw.get("id") or not org_raw.get("schema"):
            raise SchemaDriftError("Project organisation missing 'id' or 'schema'")
        org = Organisation(
            id=str(org_raw["id"]),
            name=str(org_raw.get("name", "")),
            schema_name=validate_safe_path_segment(str(org_raw["schema"]), "org_schema"),
            pbi_workspace=org_raw.get("pbi_workspace"),
        )
        acc_raw = raw.get("access") or {}
        access = ProjectAccess(
            hq=list(acc_raw.get("hq", [])),
            my=list(acc_raw.get("my", [])),
            fm4d=list(acc_raw.get("fm4d", [])),
            users=list(acc_raw.get("users", [])),
            field_app=list(acc_raw.get("fieldApp", [])),
            resources=list(acc_raw.get("resources", [])),
        )
        return Project(
            id=str(raw["id"]),
            name=str(raw.get("name", "")),
            description=str(raw.get("description") or ""),
            role=str(raw.get("role") or "VIEWER"),
            organisation=org,
            access=access,
        )


class DeviceMapper:
    _EXPECTED = {
        "id", "name", "description", "coordinates", "externalId", "sources",
        "categories", "dateInstalled", "replacementDeviceId", "commType",
        "messageType", "active", "isWorkMode", "parameters", "preferredUOM",
        "isHyperlocal", "createdAt", "updatedAt", "dmsExternalId", "sensorSetCode",
        "provider", "metadata", "sourceCode",
    }

    @classmethod
    def map_one(cls, raw: dict[str, Any]) -> Device:
        if "id" not in raw or not raw["id"]:
            raise SchemaDriftError("Device missing required primary key 'id'")
        _warn_unexpected_keys("Device", raw, cls._EXPECTED)
        coords_raw = raw.get("coordinates")
        coords = None
        if isinstance(coords_raw, dict) and coords_raw.get("latitude") is not None and coords_raw.get("longitude") is not None:
            coords = Coordinates(
                latitude=float(coords_raw["latitude"]),
                longitude=float(coords_raw["longitude"]),
            )
        source_code = str(raw.get("sourceCode") or "")
        if not source_code and isinstance(raw.get("sources"), list) and raw["sources"]:
            first_src = raw["sources"][0]
            if isinstance(first_src, dict):
                source_code = str(first_src.get("code") or first_src.get("name") or "")
        if not source_code and isinstance(raw.get("categories"), list) and raw["categories"]:
            first_cat = raw["categories"][0]
            if isinstance(first_cat, dict):
                source_code = str(first_cat.get("code") or first_cat.get("name") or "")
        if not source_code:
            msg_types = raw.get("messageType") or []
            joined = " ".join(str(x).upper() for x in msg_types) + " " + str(raw.get("name", "")).upper()
            if "WEATHER" in joined:
                source_code = "weather"
            elif "SOIL" in joined:
                source_code = "soilprobe"
            elif "FLOW" in joined:
                source_code = "waterflow"
            elif "LEVEL" in joined or "TANK" in joined:
                source_code = "waterlevel"
            else:
                source_code = "generic"
        source_norm = source_code.lower().replace(" ", "").replace("_", "")
        if "weather" in source_norm:
            source_norm = "weather"
        elif "soil" in source_norm:
            source_norm = "soilprobe"
        elif "flow" in source_norm:
            source_norm = "waterflow"
        elif "level" in source_norm or "tank" in source_norm:
            source_norm = "waterlevel"

        return Device(
            id=str(raw["id"]),
            name=str(raw.get("name", "")),
            description=str(raw.get("description") or ""),
            external_id=str(raw.get("externalId") or raw["id"]),
            source_code=source_norm,
            sensor_set_code=str(raw.get("sensorSetCode") or ""),
            comm_type=str(raw.get("commType") or ""),
            active=bool(raw.get("active", True)),
            preferred_uom=str(raw.get("preferredUOM") or "metric"),
            coordinates=coords,
            updated_at=parse_iso_timestamp(raw.get("updatedAt")),
        )


class FieldMapper:
    _EXPECTED = {
        "id", "name", "description", "category", "categoryCustom",
        "address", "isDefault", "sites",
    }

    @classmethod
    def map_one(cls, raw: dict[str, Any], project_id: str) -> FieldLocation:
        if "id" not in raw or not raw["id"]:
            raise SchemaDriftError("FieldLocation missing required primary key 'id'")
        _warn_unexpected_keys("FieldLocation", raw, cls._EXPECTED)
        sites: list[GeoPolygonSite] = []
        for s in raw.get("sites") or []:
            if not s.get("id"):
                raise SchemaDriftError("GeoPolygonSite missing 'id'")
            geojson = validate_geojson_geometry(s.get("geojson"))
            sites.append(
                GeoPolygonSite(
                    id=str(s["id"]),
                    name=str(s.get("name", "")),
                    category=str(s.get("category") or "Other"),
                    geojson=geojson,
                    area=parse_numeric(s.get("area")),
                )
            )
        return FieldLocation(
            id=str(raw["id"]),
            project_id=project_id,
            name=str(raw.get("name", "")),
            category=str(raw.get("category") or "Other"),
            address=str(raw.get("address") or ""),
            is_default=bool(raw.get("isDefault", False)),
            sites=sites,
        )


class AssetMapper:
    _EXPECTED = {
        "id", "name", "description", "assetType", "notes", "make",
        "model", "position", "capacityLitres", "numberPlate",
    }

    @classmethod
    def map_one(cls, raw: dict[str, Any], project_id: str) -> Asset:
        if "id" not in raw or not raw["id"]:
            raise SchemaDriftError("Asset missing required primary key 'id'")
        _warn_unexpected_keys("Asset", raw, cls._EXPECTED)
        pos_raw = raw.get("position")
        pos = None
        if isinstance(pos_raw, dict) and pos_raw.get("latitude") is not None and pos_raw.get("longitude") is not None:
            pos = Coordinates(
                latitude=float(pos_raw["latitude"]),
                longitude=float(pos_raw["longitude"]),
            )
        return Asset(
            id=str(raw["id"]),
            project_id=project_id,
            name=str(raw.get("name", "")),
            asset_type=str(raw.get("assetType") or "Other"),
            description=str(raw.get("description") or ""),
            make=str(raw.get("make") or ""),
            model=str(raw.get("model") or ""),
            number_plate=raw.get("numberPlate"),
            capacity_litres=parse_numeric(raw.get("capacityLitres")),
            position=pos,
        )


class ExchangeDatasetMapper:
    _EXPECTED = {
        "id", "name", "validUntil", "limit", "codes",
        "projects", "createdBy", "createdAt", "status",
    }

    @classmethod
    def map_one(cls, raw: dict[str, Any]) -> ExchangeTokenInfo:
        if "id" not in raw or not raw["id"]:
            raise SchemaDriftError("Exchange token missing required primary key 'id'")
        _warn_unexpected_keys("ExchangeTokenInfo", raw, cls._EXPECTED)
        datasets: list[ExchangeDataset] = []
        for proj in raw.get("projects") or []:
            for ds in proj.get("datasets") or []:
                cols = [str(f["columnName"]) for f in ds.get("fields") or [] if "columnName" in f]
                datasets.append(
                    ExchangeDataset(
                        table_id=str(ds.get("tableId", "")),
                        table_name=str(ds.get("tableName", "")),
                        schema_name=str(ds.get("schema", "")),
                        columns=cols,
                    )
                )
        raw_limit = raw.get("limit")
        rows_limit = int(raw_limit) if raw_limit is not None else 15000
        return ExchangeTokenInfo(
            token_id=str(raw["id"]),
            name=str(raw.get("name", "")),
            status=str(raw.get("status", "Active")),
            valid_until_utc=parse_iso_timestamp(raw.get("validUntil")),
            default_rows_per_request=rows_limit,
            unrestricted_devices=(raw.get("codes") is None),
            datasets=datasets,
        )


class AxisStreamV2Client:
    """Adapter implementing MetadataPort against v2.api.axisstream.co."""

    def __init__(self, http: ResilientHttpClient, base_url: str = "https://v2.api.axisstream.co") -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def list_projects(self) -> list[Project]:
        payload = await self._http.request_json("GET", f"{self._base_url}/api/project/list")
        rows = payload.get("data", []) if isinstance(payload, dict) else (payload or [])
        return [ProjectMapper.map_one(row) for row in rows]

    async def list_devices(self, project_id: str) -> list[Device]:
        pid = validate_safe_path_segment(project_id, "project_id")
        rows = await auto_paginate(
            lambda page, limit: self._http.request_json(
                "GET",
                f"{self._base_url}/api/device/project/{pid}",
                params={"page": page, "limit": limit},
            )
        )
        return [DeviceMapper.map_one(row) for row in rows]

    async def list_fields(self, project_id: str) -> list[FieldLocation]:
        pid = validate_safe_path_segment(project_id, "project_id")
        rows = await auto_paginate(
            lambda page, limit: self._http.request_json(
                "GET",
                f"{self._base_url}/api/field/project/{pid}",
                params={"page": page, "limit": limit, "sort": "name", "order": "ASC"},
            ),
            limit=50,
        )
        return [FieldMapper.map_one(row, pid) for row in rows]

    async def list_assets(self, project_id: str) -> list[Asset]:
        pid = validate_safe_path_segment(project_id, "project_id")
        rows = await auto_paginate(
            lambda page, limit: self._http.request_json(
                "GET",
                f"{self._base_url}/api/asset/project/{pid}",
                params={"page": page, "limit": limit, "sort": "name", "order": "asc"},
            ),
            limit=100,
        )
        return [AssetMapper.map_one(row, pid) for row in rows]

    async def list_exchange_tokens(self, project_id: str) -> list[ExchangeTokenInfo]:
        pid = validate_safe_path_segment(project_id, "project_id")
        rows = await auto_paginate(
            lambda page, limit: self._http.request_json(
                "GET",
                f"{self._base_url}/api/exchange/project/{pid}",
                params={"page": page, "limit": limit, "sort": "createdAt", "order": "DESC"},
            ),
            limit=9,
        )
        return [ExchangeDatasetMapper.map_one(row) for row in rows]

    async def list_providers(self, project_id: str) -> list[ProviderConnection]:
        pid = validate_safe_path_segment(project_id, "project_id")
        try:
            payload = await self._http.request_json(
                "GET",
                f"{self._base_url}/api/provider/project/{pid}",
            )
        except AxisStreamError as exc:
            logger.warning("Project providers endpoint returned error", extra={"project_id": pid, "error": exc.code})
            return []
        rows = payload.get("data", []) if isinstance(payload, dict) else (payload or [])
        return [
            ProviderConnection(
                id=str(r.get("id") or r.get("providerId") or ""),
                name=str(r.get("name") or (r.get("provider") or {}).get("name") or ""),
                code=str(r.get("code") or (r.get("provider") or {}).get("code") or ""),
                status=str(r.get("status", "CONNECTED")),
            )
            for r in rows
            if r.get("id") or r.get("providerId")
        ]
