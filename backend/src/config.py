import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class Config:
    app_name: str = "NewsAgent"
    debug: bool = False
    groq_api_key: str = ""
    tavily_api_key: str = ""
    model_name: str = "llama3-8b-8192"
    chunk_size: int = 1000
    verification_threshold: int = 80
    max_retries: int = 2


def load_config() -> Config:
    config = Config(
        app_name=os.getenv("APP_NAME", "NewsAgent"),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        model_name=os.getenv("MODEL_NAME", "llama3-8b-8192"),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
        verification_threshold=int(os.getenv("VERIFICATION_THRESHOLD", "80")),
        max_retries=int(os.getenv("MAX_RETRIES", "2")),
    )

    missing = [
        key
        for key, value in {
            "GROQ_API_KEY": config.groq_api_key,
            "TAVILY_API_KEY": config.tavily_api_key,
        }.items()
        if not value
    ]
    if missing:
        logger.warning("Missing configuration values: %s", ", ".join(missing))

    return config


settings = load_config()
