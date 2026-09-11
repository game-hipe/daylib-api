from loguru import logger
from pydantic import Field, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataBaseSettigs(BaseSettings):
    user: str
    password: str
    db: str
    host: str
    port: int

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="postgres_",
    )

    @computed_field
    @property
    def database_url(self) -> PostgresDsn:
        """Construct PostgreSQL connection URL from individual parameters."""
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            path=self.db,
        )

    @computed_field
    @property
    def url_sync(self) -> str:
        """Sync version of database URL (for SQLAlchemy sync engines)."""
        return str(self.database_url).replace("postgresql+asyncpg", "postgresql")

    @computed_field
    @property
    def url(self) -> str:
        """Async version of database URL (for asyncpg)."""
        return str(self.database_url)


class APISettings(BaseSettings):
    host: str = Field("0.0.0.0")
    port: int = Field(8000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="api_",
    )


class AdminSettings(BaseSettings):
    login: str
    password: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="admin_",
    )


class SecuritySettings(BaseSettings):
    secret_key: str
    service_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15

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


class Settings(BaseSettings):
    broker: str
    backend: str

    database: DataBaseSettigs = DataBaseSettigs()
    api: APISettings = APISettings()
    admin: AdminSettings = AdminSettings()
    security: SecuritySettings = SecuritySettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


setting = Settings()
