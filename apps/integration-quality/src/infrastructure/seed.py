SEED_USERS = [
    {
        "user_id": "USER-A-001",
        "display_name": "设备主管示例",
        "role_codes": ["EQUIPMENT_OPERATOR"],
        "permissions": ["EQUIPMENT_READ", "EQUIPMENT_MANAGE", "TELEMETRY_READ", "TELEMETRY_WRITE"],
        "organization": "设备科",
        "enabled": True,
    },
    {
        "user_id": "USER-C-002",
        "display_name": "维修工程师示例",
        "role_codes": ["MAINTENANCE_ENGINEER"],
        "permissions": ["WORK_ORDER_READ", "WORK_ORDER_ACCEPT", "WORK_ORDER_MAINTAIN", "SPARE_REQUEST"],
        "organization": "机加车间",
        "enabled": True,
    },
    {
        "user_id": "USER-C-003",
        "display_name": "仓管员示例",
        "role_codes": ["WAREHOUSE_MANAGER"],
        "permissions": ["SPARE_READ", "SPARE_APPROVE", "SPARE_ISSUE"],
        "organization": "备件库",
        "enabled": True,
    },
    {
        "user_id": "USER-D-001",
        "display_name": "系统管理员示例",
        "role_codes": ["SYSTEM_ADMIN"],
        "permissions": ["ADMIN_ALL", "USER_ACCESS_READ"],
        "organization": "信息中心",
        "enabled": True,
    },
]
