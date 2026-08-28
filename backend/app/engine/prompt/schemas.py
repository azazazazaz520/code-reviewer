from enum import Enum

from pydantic import BaseModel, Field, field_validator


class PromptPersona(str, Enum):
    GENERAL = "general"
    FRONTEND = "frontend"
    BACKEND = "backend"
    UI = "ui"
    QA = "qa"
    ARCHITECTURE = "architecture"


class PromptMode(str, Enum):
    INSTANT = "instant"
    REVIEW = "review"


class PromptClassificationType(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    UX = "ux"
    ARCHITECTURE = "architecture"
    UNKNOWN = "unknown"


class PromptClassification(BaseModel):
    type: PromptClassificationType
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)


class PromptTermMapping(BaseModel):
    original: str = Field(min_length=1, max_length=200)
    professional: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=500)


class PromptResult(BaseModel):
    classification: PromptClassification
    problem_phenomenon: str = Field(min_length=1, max_length=5000)
    technical_essence: str = Field(min_length=1, max_length=5000)
    solution: list[str] = Field(min_length=1, max_length=10)
    bug_view: str = Field(min_length=1, max_length=5000)
    prd_view: str = Field(min_length=1, max_length=5000)
    team_message: str = Field(min_length=1, max_length=1000)
    term_mappings: list[PromptTermMapping] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    checks: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("solution", "assumptions", "checks")
    @classmethod
    def validate_list_items(cls, value: list[str]) -> list[str]:
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item) > 2000:
                raise ValueError("列表项必须是 1～2000 个字符的非空文本")
        return [item.strip() for item in value]


class PromptOptimizeRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    persona: PromptPersona = PromptPersona.GENERAL
    mode: PromptMode = PromptMode.INSTANT
    glossary_enabled: bool = True
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请输入需要结构化的需求、Bug 描述或日志")
        return value


class PromptTurnRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=4000)
    expected_turn: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请输入确认或修正意见")
        return value


class PromptGenerationMetadata(BaseModel):
    model: str = "unknown"
    prompt_id: str = "devprompt-pro"
    prompt_version: str = "1.0.0"
    schema_version: str = "1"
    elapsed_ms: int = Field(default=0, ge=0)
    llm_attempts: int = Field(default=0, ge=0)
    format_repaired: bool = False
    candidate_mapping_count: int = Field(default=0, ge=0)
    turn: int = Field(default=1, ge=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class PromptExportBundle(BaseModel):
    markdown: str = ""
    jira: str = ""
    issue: str = ""


class PromptOptimizeResponse(BaseModel):
    result: PromptResult
    turn: int
    max_turns: int = Field(default=3, ge=1)
    session_id: str | None = None
    expires_at: str | None = None
    metadata: PromptGenerationMetadata = Field(default_factory=PromptGenerationMetadata)
    exports: PromptExportBundle = Field(default_factory=PromptExportBundle)


class PromptSessionResponse(BaseModel):
    session_id: str
    mode: PromptMode
    persona: PromptPersona
    turn: int
    max_turns: int
    expires_at: str
    latest_result: PromptResult
