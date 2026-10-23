import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "DTU Student Services Assistant"
    VERSION: str = "0.1.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Operational Mode (Section 5.1 practical tip)
    MOCK_LLM: bool = True

    # Local LLM (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # Embeddings & Reranking
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Storage paths
    DATABASE_URL: str = "sqlite:///./data/app.db"
    SQLITE_PATH: str = "./data/app.db"
    CHROMA_PERSIST_DIR: str = "./data/chromadb"
    SOURCE_REGISTER_PATH: str = "./data/source_register.csv"
    DOCUMENTS_DIR: str = "./data/documents"

    # Fallback Cloud LLM (must be disclosed in README per Section 5)
    FALLBACK_CLOUD_LLM: bool = False
    FALLBACK_LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    model_config = {"env_file": ".env", "extra": "allow"}

settings = Settings()
