"""Prompt 4 Unit Tests (UT-021 to UT-027): v2 Metadata, Paginator, ACL Mappers & Schema Drift."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from axisstream_bridge.core.exceptions import SchemaDriftError
from axisstream_bridge.infrastructure.axisstream.v2_client import (
    AssetMapper,
    AxisStreamV2Client,
    DeviceMapper,
    ExchangeDatasetMapper,
    FieldMapper,
    ProjectMapper,
    auto_paginate,
)
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from tests.fixtures.axisstream_fixtures import (
    ASSETS_FIXTURE,
    DEVICES_FIXTURE_PAGE_1,
    EXCHANGE_FIXTURE,
    FIELDS_FIXTURE,
    PROJECT_LIST_FIXTURE,
)


def test_ut_021_project_mapper_extracts_org_schema_and_rbac() -> None:
    projects = [ProjectMapper.map_one(p) for p in PROJECT_LIST_FIXTURE["data"]]
    assert len(projects) == 2
    assert projects[0].name == "TANBAOCORP_Demo"
    assert projects[0].organisation.schema_name == "tbncorp"
    assert projects[0].access.hq == ["Add", "Edit", "Delete", "View"]
    assert projects[1].name == "TBSG"


def test_ut_022_device_mapper_handles_all_4_devices() -> None:
    devices = [DeviceMapper.map_one(d) for d in DEVICES_FIXTURE_PAGE_1["data"]]
    assert [d.external_id for d in devices] == ["79DAAFB4", "79D75620", "20001DC4", "79DA26E0"]
    assert devices[0].coordinates is not None
    assert devices[0].coordinates.latitude == pytest.approx(11.690077)
    assert devices[2].updated_at is None


def test_ut_023_field_mapper_polygon_and_empty_sites() -> None:
    pid = "1b73e2fe-1e6c-46c6-8534-82c0e03be283"
    fields = [FieldMapper.map_one(f, pid) for f in FIELDS_FIXTURE["data"]]
    assert fields[0].name == "TRUONG TON FARM"
    assert len(fields[0].sites) == 1
    assert fields[1].name == "TBSG"
    assert fields[1].sites == []


def test_ut_024_asset_mapper_handles_optional_position_and_plate() -> None:
    pid = "1b73e2fe-1e6c-46c6-8534-82c0e03be283"
    assets = [AssetMapper.map_one(a, pid) for a in ASSETS_FIXTURE["data"]]
    assert assets[0].name == "Nước"
    assert assets[0].capacity_litres == 100.0
    assert assets[0].position is not None
    assert assets[1].name == "POC IoT Đà Lạt"
    assert assets[1].position is None
    assert assets[1].number_plate == "500000"


def test_ut_025_exchange_mapper_17_weather_columns() -> None:
    tok = ExchangeDatasetMapper.map_one(EXCHANGE_FIXTURE[0])
    assert tok.name == "TBSG"
    assert tok.default_rows_per_request == 15000
    assert tok.unrestricted_devices is True
    assert tok.datasets[0].schema_name == "tbncorp"
    assert tok.datasets[0].table_name == "weather"
    assert len(tok.datasets[0].columns) == 17


async def test_ut_026_auto_paginator_boundary_and_cap() -> None:
    async def empty_fetch(_p: int, _l: int):
        return {"data": [], "meta": {"total": 0, "hasNextPage": False}}

    assert await auto_paginate(empty_fetch) == []

    async def multi_fetch(page: int, _l: int):
        if page == 1:
            return {"data": [{"id": "1"}], "meta": {"hasNextPage": True}}
        return {"data": [{"id": "2"}], "meta": {"hasNextPage": False}}

    assert len(await auto_paginate(multi_fetch)) == 2

    async def infinite_fetch(page: int, _l: int):
        return {"data": [{"id": str(page)}], "meta": {"hasNextPage": True}}

    with pytest.raises(SchemaDriftError, match="max_pages"):
        await auto_paginate(infinite_fetch, max_pages=3)


def test_ut_027_schema_drift_warns_on_extra_keys_and_rejects_missing_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        raw = dict(ASSETS_FIXTURE["data"][0], brandNewColumn="unexpected")
        mapped = AssetMapper.map_one(raw, "proj-1")
        assert mapped.id == "asset-nuoc-01"
        assert "unexpected upstream keys" in caplog.text

    with pytest.raises(SchemaDriftError):
        AssetMapper.map_one({"name": "Missing ID"}, "proj-1")
