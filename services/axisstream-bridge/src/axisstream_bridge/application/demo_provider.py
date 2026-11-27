"""Sanitized real-time demo provider mirroring TANBAOCORP_Demo and TBSG schemas."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from typing import Any

from axisstream_bridge.domain.models import (
    AlertHistoryItem,
    AlertPolicy,
    Asset,
    BatchTelemetryResult,
    Device,
    DeviceTelemetrySnapshot,
    ExchangeTokenInfo,
    FieldLocation,
    ForecastDay,
    ForecastLocation,
    ForecastStep,
    Project,
    ProjectForecastBundle,
    ProviderConnection,
    WeatherExchangeRow,
    WeatherForecastReport,
)
from axisstream_bridge.infrastructure.axisstream.alert_client import AxisStreamExchangeClient
from axisstream_bridge.infrastructure.axisstream.telemetry_client import (
    SoilProbeTelemetryMapper,
    WaterFlowTelemetryMapper,
    WaterLevelTelemetryMapper,
    WeatherTelemetryMapper,
)
from axisstream_bridge.infrastructure.axisstream.v2_client import (
    AssetMapper,
    DeviceMapper,
    ExchangeDatasetMapper,
    FieldMapper,
    ProjectMapper,
)

DEMO_PROJECT_TANBAO_ID = "1b73e2fe-1e6c-46c6-8534-82c0e03be283"
DEMO_PROJECT_TBSG_ID = "1c623db4-80a3-4523-9aa4-979c8620a7a9"


class DemoAxisStreamProvider:
    """Provides sanitized realistic AxisStream data with live per-tick variation."""

    def __init__(self) -> None:
        self._tick = 0

    def bump_tick(self) -> int:
        self._tick += 1
        return self._tick

    async def list_projects(self) -> list[Project]:
        raw_projects = [
            {
                "id": DEMO_PROJECT_TANBAO_ID,
                "name": "TANBAOCORP_Demo",
                "description": "Primary AgTech IoT & Weather Telemetry Project",
                "organisation": {
                    "id": "org-tbncorp-0001",
                    "name": "TANBAOCORP",
                    "schema": "tbncorp",
                    "pbi_workspace": "pbi-tbncorp-demo",
                },
                "role": "OWNER",
                "access": {
                    "hq": ["Add", "Edit", "Delete", "View"],
                    "my": ["Add", "Edit", "Delete", "View"],
                    "fm4d": ["Add", "Edit", "Delete", "View"],
                    "users": ["Add", "Edit", "Delete", "View"],
                    "fieldApp": ["Add", "Edit", "Delete", "View"],
                    "resources": ["Add", "Edit", "Delete", "View"],
                },
            },
            {
                "id": DEMO_PROJECT_TBSG_ID,
                "name": "TBSG",
                "description": "TBSG Cropping & MET Norway Provider Project",
                "organisation": {
                    "id": "org-tbncorp-0001",
                    "name": "TANBAOCORP",
                    "schema": "tbncorp",
                    "pbi_workspace": None,
                },
                "role": "OWNER",
                "access": {
                    "hq": ["Add", "Edit", "Delete", "View"],
                    "my": ["Add", "Edit", "Delete", "View"],
                    "fm4d": ["Add", "Edit", "Delete", "View"],
                    "users": ["Add", "Edit", "Delete", "View"],
                    "fieldApp": ["Add", "Edit", "Delete", "View"],
                    "resources": ["Add", "Edit", "Delete", "View"],
                },
            },
        ]
        return [ProjectMapper.map_one(p) for p in raw_projects]

    async def list_devices(self, project_id: str) -> list[Device]:
        if project_id != DEMO_PROJECT_TANBAO_ID:
            return []
        raw_devices = [
            {
                "id": "dff22e06-e860-4722-ad1c-eb870e97bfdf",
                "name": "TanBao Weather Station (A23)",
                "externalId": "79DAAFB4",
                "sourceCode": "weather",
                "sensorSetCode": "A23",
                "commType": "wifi",
                "active": True,
                "preferredUOM": "metric",
                "coordinates": {"latitude": 11.690077, "longitude": 106.849446},
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "dev-soil-79d75620",
                "name": "TanBao Soil Probe (300mm)",
                "externalId": "79D75620",
                "sourceCode": "soilprobe",
                "sensorSetCode": "S300",
                "commType": "wifi",
                "active": True,
                "preferredUOM": "metric",
                "coordinates": {"latitude": 11.69015, "longitude": 106.84952},
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "dev-tank-20001dc4",
                "name": "TanBao Tank Level Monitor",
                "externalId": "20001DC4",
                "sourceCode": "waterlevel",
                "sensorSetCode": "WL01",
                "commType": "lorawan",
                "active": True,
                "preferredUOM": "metric",
                "coordinates": {"latitude": 11.69025, "longitude": 106.84961},
                "updatedAt": None,
            },
            {
                "id": "dev-flow-79da26e0",
                "name": "TanBao Flow Meter (200mm)",
                "externalId": "79DA26E0",
                "sourceCode": "waterflow",
                "sensorSetCode": "WF200",
                "commType": "wifi",
                "active": True,
                "preferredUOM": "metric",
                "coordinates": {"latitude": 11.69031, "longitude": 106.84971},
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            },
        ]
        return [DeviceMapper.map_one(d) for d in raw_devices]

    async def list_fields(self, project_id: str) -> list[FieldLocation]:
        if project_id == DEMO_PROJECT_TANBAO_ID:
            raw_fields = [
                {
                    "id": "fld-truong-ton-01",
                    "name": "TRUONG TON FARM",
                    "category": "Other",
                    "address": "67700, Long Tân, Long Hà, Đồng Nai, Vietnam",
                    "isDefault": False,
                    "sites": [
                        {
                            "id": "site-truong-ton-01",
                            "name": "TRUONG TON FARM",
                            "category": "Other",
                            "area": 14.5,
                            "geojson": {
                                "type": "FeatureCollection",
                                "features": [
                                    {
                                        "type": "Feature",
                                        "geometry": {
                                            "type": "Polygon",
                                            "coordinates": [
                                                [
                                                    [106.8491, 11.6906],
                                                    [106.8501, 11.6906],
                                                    [106.8501, 11.6897],
                                                    [106.8491, 11.6897],
                                                    [106.8491, 11.6906],
                                                ]
                                            ],
                                        },
                                        "properties": {"name": "Polygon 1"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "id": "fld-tanbao-test-02",
                    "name": "TanBao TEST",
                    "category": "Cropping",
                    "address": "Đồng Nai, Vietnam",
                    "isDefault": True,
                    "sites": [],
                },
            ]
        else:
            raw_fields = [
                {
                    "id": "fld-dalat-01",
                    "name": "Farm Dalat",
                    "category": "Cropping",
                    "address": "Đà Lạt, Lâm Đồng, Vietnam",
                    "isDefault": True,
                    "sites": [
                        {
                            "id": "site-dalat-01",
                            "name": "Paddock Boundary",
                            "category": "Cropping",
                            "area": 8.2,
                            "geojson": {
                                "type": "FeatureCollection",
                                "features": [
                                    {
                                        "type": "Feature",
                                        "geometry": {
                                            "type": "Polygon",
                                            "coordinates": [
                                                [
                                                    [108.5018, 12.0472],
                                                    [108.5030, 12.0472],
                                                    [108.5030, 12.0462],
                                                    [108.5018, 12.0462],
                                                    [108.5018, 12.0472],
                                                ]
                                            ],
                                        },
                                        "properties": {"name": "Paddock Boundary"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "id": "fld-tbsg-hq-02",
                    "name": "TBSG",
                    "category": "Cropping",
                    "address": "Ho Chi Minh City, Vietnam",
                    "isDefault": False,
                    "sites": [],
                },
            ]
        return [FieldMapper.map_one(f, project_id) for f in raw_fields]

    async def list_assets(self, project_id: str) -> list[Asset]:
        if project_id != DEMO_PROJECT_TANBAO_ID:
            return []
        raw_assets = [
            {
                "id": "asset-nuoc-01",
                "name": "Nước",
                "assetType": "Water Tank",
                "make": "N/A",
                "model": "",
                "position": {"latitude": 12.046912425, "longitude": 108.502432626},
                "capacityLitres": 100,
            },
            {
                "id": "asset-poc-dalat-02",
                "name": "POC IoT Đà Lạt",
                "description": "POC IoT Đà Lạt",
                "assetType": "Cultivator",
                "make": "N/A",
                "model": "Nhân Tạo",
                "numberPlate": "500000",
            },
        ]
        return [AssetMapper.map_one(a, project_id) for a in raw_assets]

    async def fetch_batch_telemetry(
        self,
        org_code: str,
        devices: list[Device],
        start_date: date,
        end_date: date,
        local_timezone: str = "Asia/Ho_Chi_Minh",
    ) -> BatchTelemetryResult:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        delta = math.sin(self._tick * 0.4)
        snapshots: list[DeviceTelemetrySnapshot] = []

        for dev in devices:
            if dev.source_code == "weather":
                body: dict[str, Any] = {
                    "recentData": {
                        "time": now_iso,
                        "temperature": f"{29.8 + delta * 1.1:.2f}",
                        "humidity": f"{71.5 - delta * 2.5:.1f}",
                        "rainfall": "0.0",
                        "atmos_pressure": f"{1010.2 + delta * 0.4:.1f}",
                        "msl_pressure": f"{1012.4 + delta * 0.4:.1f}",
                        "delta_t": f"{4.2 + abs(delta) * 0.6:.1f}",
                        "dew_point": f"{23.9 + delta * 0.5:.1f}",
                        "wind_speed": f"{12.4 + abs(delta) * 4.2:.1f}",
                        "wind_gust": f"{18.2 + abs(delta) * 5.0:.1f}",
                        "solar_radiation": f"{645.0 + delta * 45.0:.0f}",
                        "uv_index": f"{6.1 + abs(delta) * 0.8:.1f}",
                    },
                    "timeSegments": {
                        "earliestDate": "2025-12-02T00:00:00.000Z",
                        "latestDate": now_iso,
                    },
                    "metadata": {
                        "time": now_iso,
                        "batteryLevel": "95",
                        "signalStrength": "-66",
                        "readingInterval": "17 mins",
                    },
                    "uom": {
                        "recentData.temperature": "°C",
                        "recentData.humidity": "%",
                        "recentData.rainfall": "mm",
                        "recentData.atmos_pressure": "hPa",
                        "recentData.msl_pressure": "hPa",
                        "recentData.delta_t": "°C",
                        "recentData.dew_point": "°C",
                        "recentData.wind_speed": "km/h",
                        "recentData.wind_gust": "km/h",
                        "recentData.solar_radiation": "W/m²",
                        "recentData.uv_index": "index",
                    },
                }
                snapshots.append(WeatherTelemetryMapper().map_payload(dev, body))
            elif dev.source_code == "soilprobe":
                body = {
                    "recentData": {
                        "1": {"temperature": f"{29.5 + delta * 0.3:.2f}", "vic": "1377", "moist": f"{28.3 + delta * 0.6:.2f}"},
                        "2": {"temperature": f"{29.7 + delta * 0.2:.2f}", "vic": "1404", "moist": f"{33.4 + delta * 0.5:.2f}"},
                        "3": {"temperature": f"{30.3 + delta * 0.2:.2f}", "vic": "957", "moist": f"{10.9 + delta * 0.3:.2f}"},
                        "time": now_iso,
                    },
                    "timeSegments": {"earliestDate": "2025-12-09T03:27:08.000Z", "latestDate": now_iso},
                    "metadata": {"time": now_iso, "batteryLevel": "35", "signalStrength": "-92", "readingInterval": "36 mins"},
                    "uom": {
                        "timeSeriesData.temperature": "°C",
                        "timeSeriesData.moisture": "%",
                        "timeSeriesData.vic": "VIC",
                    },
                }
                snapshots.append(SoilProbeTelemetryMapper().map_payload(dev, body))
            elif dev.source_code == "waterlevel":
                body = {
                    "recentData": {},
                    "timeSegments": {"earliestDate": now_iso, "latestDate": "1970-01-01T00:00:00.000Z"},
                    "metadata": {"time": None, "batteryLevel": None, "signalStrength": None, "readingInterval": None},
                    "uom": {"recentData.rawDistance": "m", "recentData.fluidLevel": "m", "recentData.full": "%"},
                }
                snapshots.append(WaterLevelTelemetryMapper().map_payload(dev, body))
            elif dev.source_code == "waterflow":
                cum = 81.0 + self._tick * 0.5
                body = {
                    "recentData": {
                        "time": now_iso,
                        "waterVolume": f"{max(0.0, 0.5 + delta * 0.5):.2f}",
                        "cumulativeWater": f"{cum:.2f}",
                        "battery": "20",
                        "sensor": "Hunter-HC-20mm",
                    },
                    "timeSegments": {"earliestDate": "2025-12-12T04:24:18.000Z", "latestDate": now_iso},
                    "metadata": {"time": now_iso, "batteryLevel": "20", "signalStrength": "-33", "readingInterval": "17 mins"},
                    "uom": {"recentData.waterVolume": "L", "recentData.cumulativeWater": "L", "recentData.battery": "V"},
                }
                snapshots.append(WaterFlowTelemetryMapper().map_payload(dev, body))

        return BatchTelemetryResult(snapshots=snapshots, errors=[])

    async def list_alert_policies(self, project_id: str) -> list[AlertPolicy]:
        if project_id != DEMO_PROJECT_TANBAO_ID:
            return []
        return [
            AlertPolicy(
                id="pol-strong-wind-01",
                project_id=project_id,
                name="Strong wind alert",
                entity_id="dff22e06-e860-4722-ad1c-eb870e97bfdf",
                device_name="TanBao Weather Station (A23)",
                status="ACTIVE",
                priority="HIGH",
                frequency_window_minutes=60,
                notification_types=["PUSH_NOTIFICATION", "EMAIL"],
                message_template="Wind speed: %wind_speed_avg%km/h | Location: TanBao Weather Station (A23)",
            ),
            AlertPolicy(
                id="pol-low-soil-moisture-02",
                project_id=project_id,
                name="Low Rootzone Soil Moisture",
                entity_id="dev-soil-79d75620",
                device_name="TanBao Soil Probe (300mm)",
                status="ACTIVE",
                priority="MEDIUM",
                frequency_window_minutes=120,
                notification_types=["EMAIL"],
                message_template="Soil moisture depth 3 below 12%",
            ),
            AlertPolicy(
                id="pol-tank-offline-03",
                project_id=project_id,
                name="Tank Sensor Silent Alert",
                entity_id="dev-tank-20001dc4",
                device_name="TanBao Tank Level Monitor",
                status="PAUSED",
                priority="LOW",
                frequency_window_minutes=240,
                notification_types=["PUSH_NOTIFICATION"],
                message_template="Tank sensor not reporting",
            ),
        ]

    async def list_alert_history(self, project_id: str, limit: int = 50) -> list[AlertHistoryItem]:
        if project_id != DEMO_PROJECT_TANBAO_ID:
            return []
        now = datetime.now(timezone.utc)
        return [
            AlertHistoryItem(
                id="alrt-hist-001",
                project_id=project_id,
                policy_name="Strong wind alert",
                device_name="TanBao Weather Station (A23)",
                rule_description="wind_speed_avg >= 15 km/h",
                delivery_status="Delivered",
                notification_count=2,
                triggered_at_utc=now - timedelta(minutes=12),
            ),
            AlertHistoryItem(
                id="alrt-hist-002",
                project_id=project_id,
                policy_name="Low Rootzone Soil Moisture",
                device_name="TanBao Soil Probe (300mm)",
                rule_description="moisture_3 <= 12.0 %",
                delivery_status="Delivered",
                notification_count=1,
                triggered_at_utc=now - timedelta(minutes=45),
            ),
        ][:limit]

    async def list_providers(self, project_id: str) -> list[ProviderConnection]:
        if project_id == DEMO_PROJECT_TBSG_ID:
            return [
                ProviderConnection(
                    id="prov-met-norway",
                    name="MET Norway Weather",
                    code="met_norway",
                    status="CONNECTED",
                )
            ]
        return []

    async def list_exchange_tokens(self, project_id: str) -> list[ExchangeTokenInfo]:
        if project_id != DEMO_PROJECT_TANBAO_ID:
            return []
        raw = {
            "id": "exch-tbsg-token-ref",
            "name": "TBSG",
            "validUntil": "2/15/2053, 2:53:43 PM",
            "limit": None,
            "codes": None,
            "projects": [
                {
                    "projectId": DEMO_PROJECT_TANBAO_ID,
                    "name": "TANBAOCORP_Demo",
                    "datasets": [
                        {
                            "tableId": "94783889-6011-4333-8a69-7f5a6af7c223",
                            "tableName": "weather",
                            "schema": "tbncorp",
                            "fields": [{"columnName": col} for col in AxisStreamExchangeClient.WEATHER_COLUMNS],
                        }
                    ],
                }
            ],
            "status": "Active",
        }
        return [ExchangeDatasetMapper.map_one(raw)]

    async def fetch_weather_exchange(
        self, org_code: str, project_id: str, limit: int = 15000
    ) -> list[WeatherExchangeRow]:
        if project_id != DEMO_PROJECT_TANBAO_ID:
            return []
        now = datetime.now(timezone.utc)
        rows: list[WeatherExchangeRow] = []
        for idx in range(min(limit, 12)):
            t = now - timedelta(minutes=15 * idx)
            wave = math.sin((self._tick + idx) * 0.35)
            rows.append(
                WeatherExchangeRow(
                    code="79DAAFB4",
                    time=t,
                    temperature_avg=round(29.6 + wave * 1.2, 2),
                    humidity_avg=round(72.0 - wave * 3.0, 1),
                    deltat_avg=round(4.1 + abs(wave) * 0.5, 2),
                    dewpoint_avg=round(23.8 + wave * 0.4, 2),
                    atmos_pressure_avg=round(1010.2 + wave * 0.3, 1),
                    msl_pressure=round(1012.3 + wave * 0.3, 1),
                    rainfall=0.0 if idx % 4 else 0.4,
                    rainfall_total=round(12.4 + (0.4 if idx % 4 == 0 else 0.0), 1),
                    wind_speed_avg=round(11.8 + abs(wave) * 4.0, 1),
                    wind_speed_min=round(7.5 + abs(wave) * 2.0, 1),
                    wind_speed_max=round(17.9 + abs(wave) * 5.2, 1),
                    wind_dir_deg_avg=round((135 + idx * 12) % 360, 0),
                    wind_dir_var_avg=18.0,
                    solar_rad_avg=round(620.0 + wave * 60.0, 1),
                    uv_index_avg=round(5.9 + abs(wave) * 1.1, 1),
                )
            )
        return rows

    async def fetch_project_forecast(self, project_id: str) -> ProjectForecastBundle:
        now = datetime.now(timezone.utc)
        loc = ForecastLocation(
            name="67700, Long Tân, Long Hà, Đồng Nai, Vietnam"
            if project_id == DEMO_PROJECT_TANBAO_ID
            else "Đà Lạt, Lâm Đồng, Vietnam",
            latitude=11.6901 if project_id == DEMO_PROJECT_TANBAO_ID else 12.0469,
            longitude=106.8494 if project_id == DEMO_PROJECT_TANBAO_ID else 108.5024,
            time_zone="Asia/Ho_Chi_Minh",
            utc_offset_minutes=420,
        )
        days = [
            ForecastDay(
                date=(now + timedelta(days=i)).date().isoformat(),
                complete=True,
                hours_covered=24,
                temperature_min=round(23.0 + (i % 2) * 1.0, 1),
                temperature_max=round(29.0 + ((i + 1) % 4) * 1.0, 1),
                precipitation=[0.3, 5.9, 18.1, 20.9, 7.0, 0.3, 7.2][i],
                symbol=["fair_day", "rainshowers_day", "heavyrain", "heavyrain", "lightrainshowers_day", "partlycloudy_day", "rain"][i],
            )
            for i in range(7)
        ]
        steps = [
            ForecastStep(
                time_utc=now + timedelta(hours=h),
                time_local=(now + timedelta(hours=h + 7)).strftime("%Y-%m-%dT%H:00"),
                interval_hours=1,
                is_night=((now.hour + 7 + h) % 24 >= 18 or (now.hour + 7 + h) % 24 < 6),
                temperature=round(31.5 - (h % 6) * 0.7, 1),
                feels_like=round(36.0 - (h % 6) * 0.6, 1),
                humidity=round(59.0 + (h % 6) * 2.5, 1),
                pressure=1010.0,
                wind_speed=5.0 + (h % 4),
                wind_gust=9.0 + (h % 5),
                wind_direction=327.0,
                uv_index=2.6 if h == 0 else 0.5,
                cloud_cover=16.0 + (h % 5) * 8.0,
                fog=0.0,
                precipitation_1h=0.0 if h < 3 else 0.3,
                precipitation_6h=0.3,
                symbol="fair_day" if h < 3 else "lightrainshowers_day",
            )
            for h in range(12)
        ]
        met = WeatherForecastReport(
            provider="MET Norway",
            status="CONNECTED",
            location=loc,
            updated_at_utc=now,
            expires_at_utc=now + timedelta(hours=3),
            current_step_index=0,
            days=days,
            steps=steps,
        )
        janes = WeatherForecastReport(
            provider="Jane's Weather",
            status="DISCONNECTED",
            location=loc,
        )
        return ProjectForecastBundle(
            project_id=project_id,
            met_norway=met,
            janes_weather=janes,
        )
