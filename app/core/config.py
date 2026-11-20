from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    mysql_host: str = "127.0.0.1"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_user: str = "admin"
    mysql_password: SecretStr = SecretStr("")
    mysql_database: str = "vehiculo_iot"
    mysql_ssl_ca: str = ""
    exhibicion_habilitada: bool = False
    comercial_habilitado: bool = False
    control_token: SecretStr = SecretStr("")
    device_token: SecretStr = SecretStr("")
    device_vehicle_id: int = Field(default=1, gt=0)
    device_tokens_por_unidad: dict[int, SecretStr] = Field(default_factory=dict)
    browser_origins: list[str] = Field(default_factory=list)
    openai_api_key: SecretStr = SecretStr("")
    openai_voice_model: str = "gpt-4.1-mini"
