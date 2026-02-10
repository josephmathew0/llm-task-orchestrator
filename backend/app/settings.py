from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # TODO: Create as constants.py file with these values and import it here
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "mock"  # "mock" or "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    class Config:
        env_prefix = ""
        case_sensitive = False


settings = Settings()
