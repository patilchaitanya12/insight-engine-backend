from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str
    MONGO_URI: str

    LLM_VENDOR: str
    LLM_MODEL: str
    LLM_API_KEY: str
    LLM_BASE_URL: str

    class Config:
        env_file = ".env"


settings = Settings()