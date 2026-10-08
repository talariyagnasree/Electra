import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    data_dir = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    chroma_dir = Path(os.getenv("CHROMA_DIR", BASE_DIR / ".chroma"))
    embedding_backend = os.getenv("EMBEDDING_BACKEND", "default").lower()
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    verbose = os.getenv("AGENT_VERBOSE", "false").lower() == "true"
    api_url = os.getenv("API_URL", "http://localhost:8000")

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key) or self.llm_model.startswith("ollama")


settings = Settings()
