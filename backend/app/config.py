from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    database_url: str = "sqlite:///./data/code_reviewer.db"

    # 审查引擎
    max_reflection_rounds: int = 3
    max_incremental_reflection_rounds: int = 1
    reviewer_timeout_seconds: int = 120
    review_worker_poll_seconds: float = 1.0
    context_files_per_round: int = 20
    review_unit_max_chars: int = 24000
    review_context_max_files: int = 10
    review_context_max_chars: int = 24000
    review_context_padding_lines: int = 80
    max_review_calls: int = 48
    max_review_duration_seconds: int = 1200
    max_tool_rounds: int = 2
    max_tool_calls_per_unit: int = 4
    max_related_files_per_unit: int = 4
    review_parallelism: int = 3

    # 提示词工作区
    prompt_timeout_seconds: int = 60
    prompt_min_input_chars: int = 1
    prompt_max_input_chars: int = 12000
    prompt_max_output_tokens: int = 3000
    prompt_session_ttl_seconds: int = 1800
    prompt_session_max_count: int = 100
    prompt_session_max_context_chars: int = 24000

    # LLM
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # GitHub
    github_token: str = ""

    # Gitee
    gitee_token: str = ""

    # CRG
    crg_enabled: bool = True

    # 仓库存储
    repos_dir: str = "./data/repos"

    # 前端静态文件
    frontend_dist_dir: str = "../frontend/dist"

    # CORS — 开发环境默认覆盖常见 Vite 端口
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
