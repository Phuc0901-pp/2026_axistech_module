"""Sanitized real-world AxisStream HQ JSON fixtures (TANBAOCORP_Demo & TBSG)."""

from __future__ import annotations

PROJECT_LIST_FIXTURE = {
    "data": [
        {
            "id": "1b73e2fe-1e6c-46c6-8534-82c0e03be283",
            "name": "TANBAOCORP_Demo",
            "description": "Primary Farm",
            "organisation": {
                "id": "org-tbncorp-0001",
                "name": "TANBAOCORP",
                "schema": "tbncorp",
                "pbi_workspace": "pbi-ws-01",
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
            "id": "1c623db4-80a3-4523-9aa4-979c8620a7a9",
            "name": "TBSG",
            "description": "",
            "organisation": {
                "id": "org-tbncorp-0001",
                "name": "TANBAOCORP",
                "schema": "tbncorp",
                "pbi_workspace": None,
            },
            "role": "OWNER",
            "access": {"hq": ["View"], "my": ["View"], "fm4d": ["View"], "users": ["View"], "fieldApp": ["View"], "resources": ["View"]},
        },
    ]
}

DEVICES_FIXTURE_PAGE_1 = {
    "data": [
        {
            "id": "dff22e06-e860-4722-ad1c-eb870e97bfdf",
            "name": "TanBao Weather Station (A23)",
            "externalId": "79DAAFB4",
            "sourceCode": "weather",
            "commType": "wifi",
            "sensorSetCode": "A23",
            "active": True,
            "preferredUOM": "metric",
            "coordinates": {"latitude": 11.690077, "longitude": 106.849446},
            "updatedAt": "11/25/2026",
        },
        {
            "id": "dev-soil-79d75620",
            "name": "TanBao Soil Probe (300mm)",
            "externalId": "79D75620",
            "sourceCode": "soilprobe",
            "commType": "wifi",
            "sensorSetCode": "S300",
            "active": True,
            "preferredUOM": "metric",
            "coordinates": {"latitude": 11.69015, "longitude": 106.84952},
            "updatedAt": "2026-05-17T02:10:17.000Z",
        },
        {
            "id": "dev-tank-20001dc4",
            "name": "TanBao Tank Level Monitor",
            "externalId": "20001DC4",
            "sourceCode": "waterlevel",
            "commType": "lorawan",
            "sensorSetCode": "WL01",
            "active": True,
            "preferredUOM": "metric",
        },
        {
            "id": "dev-flow-79da26e0",
            "name": "TanBao Flow Meter (200mm)",
            "externalId": "79DA26E0",
            "sourceCode": "waterflow",
            "commType": "wifi",
            "sensorSetCode": "WF200",
            "active": True,
            "preferredUOM": "metric",
        },
    ],
    "meta": {"page": 1, "limit": 100, "total": 4, "totalPages": 1, "hasNextPage": False},
}

FIELDS_FIXTURE = {
    "data": [
        {
            "id": "fld-truong-ton-01",
            "name": "TRUONG TON FARM",
            "description": "",
            "category": "Other",
            "categoryCustom": "",
            "address": "67700, Long Tân, Long Hà, Đồng Nai, Vietnam",
            "isDefault": False,
            "sites": [
                {
                    "id": "site-truong-ton-01",
                    "name": "TRUONG TON FARM",
                    "category": "Other",
                    "geojson": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        [
                                            [106.849457, 11.690432],
                                            [106.849957, 11.690432],
                                            [106.849957, 11.689932],
                                            [106.849457, 11.689932],
                                            [106.849457, 11.690432],
                                        ]
                                    ],
                                },
                                "properties": {"name": "Polygon 1"},
                            }
                        ],
                    },
                    "area": None,
                }
            ],
        },
        {
            "id": "fld-tbsg-02",
            "name": "TBSG",
            "category": "Cropping",
            "address": "Ho Chi Minh City, Vietnam",
            "isDefault": False,
            "sites": [],
        },
    ],
    "meta": {"page": 1, "limit": 50, "total": 2, "totalPages": 1, "hasNextPage": False},
}

ASSETS_FIXTURE = {
    "data": [
        {
            "id": "asset-nuoc-01",
            "name": "Nước",
            "description": "",
            "assetType": "Water Tank",
            "notes": "",
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
            "notes": "",
            "make": "N/A",
            "model": "Nhân Tạo",
            "numberPlate": "500000",
        },
    ],
    "meta": {"page": 1, "limit": 100, "total": 2, "totalPages": 1, "hasNextPage": False},
}

EXCHANGE_FIXTURE = [
    {
        "id": "token-tbsg-synthetic-id",
        "name": "TBSG",
        "validUntil": "2/15/2053, 2:53:43 PM",
        "limit": None,
        "codes": None,
        "projects": [
            {
                "projectId": "1b73e2fe-1e6c-46c6-8534-82c0e03be283",
                "name": "TANBAOCORP_Demo",
                "datasets": [
                    {
                        "tableId": "94783889-6011-4333-8a69-7f5a6af7c223",
                        "tableName": "weather",
                        "schema": "tbncorp",
                        "fields": [
                            {"columnName": "atmos_pressure_avg"},
                            {"columnName": "temperature_avg"},
                            {"columnName": "deltat_avg"},
                            {"columnName": "dewpoint_avg"},
                            {"columnName": "humidity_avg"},
                            {"columnName": "uv_index_avg"},
                            {"columnName": "wind_dir_deg_avg"},
                            {"columnName": "wind_speed_avg"},
                            {"columnName": "solar_rad_avg"},
                            {"columnName": "code"},
                            {"columnName": "wind_speed_min"},
                            {"columnName": "msl_pressure"},
                            {"columnName": "rainfall"},
                            {"columnName": "time"},
                            {"columnName": "rainfall_total"},
                            {"columnName": "wind_dir_var_avg"},
                            {"columnName": "wind_speed_max"},
                        ],
                    }
                ],
            }
        ],
        "createdBy": "operator@example.com",
        "createdAt": "10/1/2025, 6:53:09 AM",
        "status": "Active",
    }
]

WATERFLOW_TELEMETRY_FIXTURE = {
    "recentData": {
        "time": "2026-01-28T10:28:24.000Z",
        "waterVolume": "0.00",
        "cumulativeWater": "81.00",
        "battery": "20",
        "sensor": "Hunter-HC-20mm",
    },
    "timeSeriesData": {"waterVolume": [], "cumulativeWater": []},
    "timeSegments": {
        "startDate": None,
        "endDate": None,
        "earliestDate": "2025-12-12T04:24:18.000Z",
        "latestDate": "2026-01-28T10:28:24.000Z",
    },
    "metadata": {
        "time": "2026-01-28T10:28:24.000Z",
        "batteryLevel": "20",
        "signalStrength": "-33",
        "readingInterval": "17 mins",
    },
    "uom": {
        "recentData.waterVolume": "L",
        "recentData.cumulativeWater": "L",
        "recentData.battery": "V",
    },
}

SOILPROBE_TELEMETRY_FIXTURE = {
    "recentData": {
        "1": {"temperature": "29.53", "vic": "1377", "moist": "28.36"},
        "2": {"temperature": "29.75", "vic": "1404", "moist": "33.49"},
        "3": {"temperature": "30.34", "vic": "957", "moist": "10.96"},
        "time": "2026-05-17T02:10:17.000Z",
    },
    "timeSeriesData": {"temperature": {}, "moisture": {}, "vic": {}},
    "timeSegments": {
        "earliestDate": "2025-12-09T03:27:08.000Z",
        "latestDate": "2026-05-17T02:09:18.000Z",
    },
    "metadata": {
        "time": "2026-05-17T02:09:18.000Z",
        "batteryLevel": "35",
        "signalStrength": "-92",
        "readingInterval": "36 mins",
    },
    "uom": {
        "timeSeriesData.temperature": "°C",
        "timeSeriesData.moisture": "%",
        "timeSeriesData.vic": "VIC",
    },
}

WATERLEVEL_EMPTY_FIXTURE = {
    "recentData": {},
    "timeSeriesData": {"rawDistance": [], "fluidLevel": [], "full": []},
    "timeSegments": {
        "startDate": None,
        "endDate": None,
        "earliestDate": "2026-11-26T07:17:29.684Z",
        "latestDate": "1970-01-01T00:00:00.000Z",
    },
    "metadata": {
        "time": None,
        "batteryLevel": None,
        "signalStrength": None,
        "readingInterval": None,
    },
    "uom": {
        "recentData.rawDistance": "m",
        "recentData.fluidLevel": "m",
        "recentData.full": "%",
    },
}

WEATHER_TELEMETRY_FIXTURE = {
    "recentData": {
        "time": "2026-11-26T07:00:00.000Z",
        "temperature": "30.40",
        "humidity": "68.5",
        "rainfall": "0.0",
        "atmos_pressure": "1010.5",
        "msl_pressure": "1012.8",
        "delta_t": "4.5",
        "dew_point": "23.9",
        "wind_speed": "14.2",
        "wind_direction": "135",
        "wind_gust": "21.0",
        "solar_radiation": "680",
        "uv_index": "6.5",
    },
    "timeSegments": {
        "earliestDate": "2025-12-02T00:00:00.000Z",
        "latestDate": "2026-11-26T07:00:00.000Z",
    },
    "metadata": {
        "time": "2026-11-26T07:00:00.000Z",
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
        "recentData.wind_direction": "deg",
        "recentData.wind_gust": "km/h",
        "recentData.solar_radiation": "W/m²",
        "recentData.uv_index": "index",
    },
}

ALERT_TEMPLATES_FIXTURE = [
    {
        "id": "tpl-soil-temp-01",
        "createdAt": "8/7/2024, 5:14:41 PM",
        "updatedAt": "2024-08-07T17:14:41.933Z",
        "name": "Soil Probe Temperature",
        "type": "value",
        "policy": {
            "type": "value",
            "column": "soil_temperature_1",
            "operators": [
                {"name": "lessThan", "symbol": "<"},
                {"name": "lessThanOrEqualTo", "symbol": "<="},
                {"name": "equalTo", "symbol": "="},
                {"name": "notEqualTo", "symbol": "!="},
                {"name": "greaterThanOrEqualTo", "symbol": ">="},
                {"name": "greaterThan", "symbol": ">"},
                {"name": "in", "symbol": "IN"},
                {"name": "notIn", "symbol": "NOT IN"},
            ],
        },
    }
]

ALERT_POLICIES_FIXTURE = [
    {
        "id": "pol-strong-wind-01",
        "name": "Strong wind alert",
        "entityId": "dff22e06-e860-4722-ad1c-eb870e97bfdf",
        "entityType": "device",
        "device": {"id": "dff22e06-e860-4722-ad1c-eb870e97bfdf", "name": "TanBao Weather Station (A23)"},
        "policies": [
            {
                "name": "High wind speed",
                "type": "value",
                "value": "20",
                "column": "wind_speed_avg",
                "operator": {"name": "greaterThanOrEqualTo", "symbol": ">="},
            }
        ],
        "notificationTypes": ["PUSH_NOTIFICATION"],
        "frequencyWindowMinutes": 60,
        "status": "PAUSED",
        "priority": "MEDIUM",
        "messageTemplate": "Wind speed: %wind_speed_avg%km/h",
    }
]
