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

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请输入需要结构化的需求、Bug 描述或日志")
        return value


class PromptTurnRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=4000)

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请输入确认或修正意见")
        return value


class PromptOptimizeResponse(BaseModel):
    result: PromptResult
    turn: int
    session_id: str | None = None
    expires_at: str | None = None
    metadata: dict[str, int | str] = Field(default_factory=dict)


class PromptSessionResponse(BaseModel):
    session_id: str
    mode: PromptMode
    persona: PromptPersona
    turn: int
    max_turns: int
    expires_at: str
    latest_result: PromptResult
