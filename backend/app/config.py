from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    database_url: str = "sqlite:///./data/code_reviewer.db"

    # 审查引擎
    max_reflection_rounds: int = 3
    reviewer_timeout_seconds: int = 120

    # LLM
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # GitHub
    github_token: str = ""

    # CRG
    crg_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
