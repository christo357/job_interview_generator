import os
import json
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    DB_URL : str = os.getenv("DB_URL", f"sqlite:///{PROJECT_ROOT}/data/app.db")
    STACKEXCHANGE_KEY: str = os.getenv("STACKEXCHANGE_KEY", "")


    # DB_PATH: str = os.getenv("DB_PATH", "data/app.db")
    OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "90"))
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    
    # Crawling defaults (used by role-aware crawl button elsewhere)
    CRAWL_SITES = os.getenv("CRAWL_SITES", "stackoverflow,softwareengineering,dba,datascience,ai").split(",")
    CRAWL_PAGES = int(os.getenv("CRAWL_PAGES", "2"))
    CRAWL_PAGE_SIZE = int(os.getenv("CRAWL_PAGE_SIZE", "50"))
    CRAWL_QUERY_HINT = os.getenv("CRAWL_QUERY_HINT", "interview")
    
    LLM_GEN_COUNTS = json.loads(os.getenv("LLM_GEN_COUNTS", '{"Technical":10,"Coding":10,"Behavioral":10}'))

    
    

settings = Settings()


# fail fast in dev
if not settings.OPENAI_API_KEY:
    print("[cfg] WARNING: OPENAI_API_KEY missing")
print(f"[cfg] DB_URL={settings.DB_URL}")