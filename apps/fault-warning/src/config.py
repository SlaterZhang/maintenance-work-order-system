"""B 模块运行时配置。

环境变量命名与仓库根目录 ``.env.example`` 保持一致
（``EQUIPMENT_SERVICE_URL`` / ``MAINTENANCE_SERVICE_URL`` /
``INTEGRATION_SERVICE_URL`` / ``INTERNAL_API_TOKEN``），
端口沿用各模块自己的 ``MEMBER_x_PORT`` 约定。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # protected_namespaces 置空：model_version 与 pydantic 的 "model_" 保护前缀冲突
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    member_b_port: int = 8102
    database_url: str = "sqlite:///./member_b.db"
    internal_api_token: str = "dev-internal-token-change-me"

    # 跨模块直连地址
    equipment_service_url: str = "http://127.0.0.1:8101"
    maintenance_service_url: str = "http://127.0.0.1:8103"
    integration_service_url: str = "http://127.0.0.1:8104"

    # 评分模型版本，写入每条预警的 modelVersion
    model_version: str = "rule-engine-1.0.0"

    # 外部服务不可达时是否降级为本地 mock。
    # 默认 False（阶段1鉴权闭合，2026-10-06）：联调/演示/生产一律 fail closed，
    # "取不到设备/权限"直接失败，绝不伪造数据或静默放行；
    # 本地单品开发可在 .env 显式设置 ALLOW_CLIENT_MOCK=true。
    allow_client_mock: bool = False

    client_timeout_seconds: float = 3.0

    # outbox 待发送事件的最大投递次数
    event_max_retries: int = 3

    # 单次评估最多尝试分配多少个 WarningId 序号（防止序号被占满时死循环）
    warning_id_max_attempts: int = 20


settings = Settings()
