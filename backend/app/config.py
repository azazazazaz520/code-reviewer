from pydantic_settings import BaseSettings


# 审查上下文的运行时安全上限；用户配置可以低于此值，不能突破此值。
REVIEW_CONTEXT_HARD_MAX_FILES = 20
REVIEW_CONTEXT_HARD_MAX_CHARS = 60_000


class Settings(BaseSettings):
    # 数据库
    database_url: str = "sqlite:///./data/code_reviewer.db"

    # 审查引擎
    reviewer_timeout_seconds: int = 120
    review_worker_poll_seconds: float = 1.0
    # 同一 Reviewer 的相邻变更按批次合并，完整 Hunk 不跨批次拆分。
    review_batch_max_chars: int = 12000
    review_context_max_files: int = 10
    review_context_max_chars: int = 32000
    supplement_context_max_chars: int = 12000
    # Reviewer 动态后缀只保留变更 Hunk 附近的窄窗口。
    review_context_padding_lines: int = 24
    max_review_duration_seconds: int = 1200
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
    llm_model: str = "deepseek-v4-flash"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    # 主要审查、一次性上下文补充和 JSON 修复使用独立输出预算。
    llm_review_max_tokens: int = 4096
    llm_supplement_max_tokens: int = 2048
    llm_json_repair_max_tokens: int = 1024
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    # GitHub
    github_token: str = ""

    # Gitee
    gitee_token: str = ""

    # CRG
    crg_enabled: bool = False

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
