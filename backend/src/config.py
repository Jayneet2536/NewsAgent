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
    youtube_api_key: str = ""
    database_path: str = "data/newsagent.sqlite3"
    model_name: str = "llama3-8b-8192"
    planner_model: str = "openai/gpt-oss-120b"
    writer_model: str = "openai/gpt-oss-120b"
    verifier_model: str = "openai/gpt-oss-120b"
    groq_tpm_limit: int = 8000
    llm_input_budget: int = 5000
    llm_output_budget: int = 1200
    research_max_queries: int = 6
    research_max_sources: int = 12
    chunk_size: int = 1000
    verification_threshold: int = 80
    max_retries: int = 2


def load_config() -> Config:
    config = Config(
        app_name=os.getenv("APP_NAME", "NewsAgent"),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
        database_path=os.getenv("DATABASE_PATH", "data/newsagent.sqlite3"),
        model_name=os.getenv("MODEL_NAME", "llama3-8b-8192"),
        planner_model=os.getenv("PLANNER_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b",
        writer_model=os.getenv("WRITER_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b",
        verifier_model=os.getenv("VERIFIER_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b",
        groq_tpm_limit=int(os.getenv("GROQ_TPM_LIMIT", "8000")),
        llm_input_budget=int(os.getenv("LLM_INPUT_BUDGET", "5000")),
        llm_output_budget=int(os.getenv("LLM_OUTPUT_BUDGET", "1200")),
        research_max_queries=int(os.getenv("RESEARCH_MAX_QUERIES", "6")),
        research_max_sources=int(os.getenv("RESEARCH_MAX_SOURCES", "12")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
        verification_threshold=int(os.getenv("VERIFICATION_THRESHOLD", "80")),
        max_retries=int(os.getenv("MAX_RETRIES", "2")),
    )

    if min(config.groq_tpm_limit, config.llm_input_budget, config.llm_output_budget,
           config.research_max_queries, config.research_max_sources) <= 0:
        raise ValueError("LLM budgets and research limits must be positive.")
    if config.llm_input_budget + config.llm_output_budget + 256 > config.groq_tpm_limit:
        raise ValueError("LLM input/output budgets plus 256 safety tokens must fit GROQ_TPM_LIMIT.")

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
