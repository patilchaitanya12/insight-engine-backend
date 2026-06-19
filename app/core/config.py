from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str
    MONGO_URI: str

    LLM_VENDOR: str
    LLM_MODEL: str
    LLM_API_KEY: str
    LLM_BASE_URL: str
    CLERK_SECRET_KEY: str
    CLERK_JWKS_URL: str = "https://robust-hen-72.clerk.accounts.dev/.well-known/jwks.json"
    class Config:
        env_file = ".env"


settings = Settings()