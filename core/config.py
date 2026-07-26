from loguru import logger
from pydantic import Field, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    broker: str
    backend: str

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int

    host_api: str = Field("0.0.0.0")
    port_api: int = Field(8000)

    video_path: str = "./video"

    admin_login: str
    admin_password: str

    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    service_key: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def service_key_validate(self):
        if len(self.service_key) < 32:
            logger.warning(
                "Длина сервисного ключа мене 32 символов, пожалуйста поменяйте на более надёжный"
            )

        if len(self.secret_key) < 32:
            logger.warning(
                "Длина секретного ключа мене 32 символов, пожалуйста поменяйте на более надёжный"
            )

        return self

    @computed_field
    @property
    def database_url(self) -> PostgresDsn:
        """Construct PostgreSQL connection URL from individual parameters."""
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )

    @computed_field
    @property
    def database_url_sync(self) -> str:
        """Sync version of database URL (for SQLAlchemy sync engines)."""
        return str(self.database_url).replace("postgresql+asyncpg", "postgresql")

    @computed_field
    @property
    def database_url_async(self) -> str:
        """Async version of database URL (for asyncpg)."""
        return str(self.database_url)


setting = Settings()
