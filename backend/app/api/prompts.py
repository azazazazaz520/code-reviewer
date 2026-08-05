from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.engine.prompt.schemas import (
    PromptOptimizeRequest,
    PromptOptimizeResponse,
    PromptSessionResponse,
    PromptTurnRequest,
)
from app.services.prompt_optimizer import PromptOptimizer, PromptOptimizerError
from app.services.prompt_session import PromptSessionError


router = APIRouter(prefix="/api/prompts", tags=["prompts"])
optimizer = PromptOptimizer()


def _raise_prompt_error(error: PromptOptimizerError | PromptSessionError) -> None:
    status_code = 422 if getattr(error, "code", "").endswith("invalid") else 502
    if getattr(error, "code", "").startswith("prompt_session"):
        status_code = 410 if "expired" in error.code else 404
        if "limit" in error.code or "context" in error.code:
            status_code = 409
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    ) from error


@router.post("/optimize", response_model=PromptOptimizeResponse)
def optimize_prompt(request: PromptOptimizeRequest) -> PromptOptimizeResponse:
    try:
        result, metadata, session = optimizer.optimize(request)
    except (PromptOptimizerError, PromptSessionError) as error:
        _raise_prompt_error(error)
    return PromptOptimizeResponse(
        result=result,
        turn=session.turn if session else 1,
        session_id=session.session_id if session else None,
        expires_at=session.expires_at.isoformat() if session else None,
        metadata=metadata,
    )


@router.post("/sessions/{session_id}/turns", response_model=PromptOptimizeResponse)
def add_prompt_session_turn(session_id: str, request: PromptTurnRequest) -> PromptOptimizeResponse:
    try:
        result, metadata, session = optimizer.add_review_turn(session_id, request.feedback)
    except (PromptOptimizerError, PromptSessionError) as error:
        _raise_prompt_error(error)
    return PromptOptimizeResponse(
        result=result,
        turn=session.turn,
        session_id=session.session_id,
        expires_at=session.expires_at.isoformat(),
        metadata=metadata,
    )


@router.get("/sessions/{session_id}", response_model=PromptSessionResponse)
def get_prompt_session(session_id: str) -> PromptSessionResponse:
    try:
        session = optimizer.sessions.get(session_id)
    except PromptSessionError as error:
        _raise_prompt_error(error)
    return PromptSessionResponse(
        session_id=session.session_id,
        mode=session.mode,
        persona=session.persona,
        turn=session.turn,
        max_turns=session.max_turns,
        expires_at=session.expires_at.isoformat(),
        latest_result=session.latest_result,
    )


@router.delete("/sessions/{session_id}")
def delete_prompt_session(session_id: str) -> dict[str, str]:
    if not optimizer.sessions.delete(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "prompt_session_not_found", "message": "审查会话不存在"},
        )
    return {"status": "deleted"}
