from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str
    MONGO_URI: str
    LLM_PROVIDER: str
    OPENAI_API_KEY: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()