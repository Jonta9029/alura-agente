import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    DATABASE_URL: str = "sqlite:///./alura_agente.db"
    CSV_PATH: str = "data/corporate_data.csv"
    PORT: int = 8000
    
    # Permitir cargar variables desde un archivo .env si existe
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
