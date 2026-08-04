from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", extra="ignore"
        )

    POSTGRES_USER: str = "payments"
    POSTGRES_PASSWORD: str = "payments"
    POSTGRES_DB: str = "payments"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    PROVIDER_URL: str = "http://localhost:8081"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
