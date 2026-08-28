from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.engine.prompt.schemas import (
    PromptExportBundle,
    PromptOptimizeRequest,
    PromptOptimizeResponse,
    PromptSessionResponse,
    PromptTurnRequest,
)
from app.engine.prompt.exporters import export_text
from app.services.prompt_optimizer import PromptOptimizer, PromptOptimizerError
from app.services.prompt_session import PromptSessionError


router = APIRouter(prefix="/api/prompts", tags=["prompts"])
optimizer = PromptOptimizer()


def _raise_prompt_error(error: PromptOptimizerError | PromptSessionError) -> None:
    code = getattr(error, "code", "")
    status_code = {
        "prompt_input_invalid": 422,
        "prompt_llm_timeout": 504,
        "prompt_llm_failed": 502,
        "prompt_llm_empty_response": 502,
        "prompt_output_contract_failed": 502,
        "prompt_output_repair_failed": 502,
        "prompt_session_not_found": 404,
        "prompt_session_expired": 410,
        "prompt_session_limit_reached": 409,
        "prompt_session_context_too_long": 409,
        "prompt_session_version_conflict": 409,
    }.get(code, 502)
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    ) from error


def _build_exports(result) -> PromptExportBundle:
    return PromptExportBundle(
        markdown=export_text(result, "markdown"),
        jira=export_text(result, "jira"),
        issue=export_text(result, "issue"),
    )


@router.post("/optimize", response_model=PromptOptimizeResponse)
def optimize_prompt(request: PromptOptimizeRequest) -> PromptOptimizeResponse:
    try:
        result, metadata, session = optimizer.optimize(request)
    except (PromptOptimizerError, PromptSessionError) as error:
        _raise_prompt_error(error)
    return PromptOptimizeResponse(
        result=result,
        turn=session.turn if session else 1,
        max_turns=session.max_turns if session else 3,
        session_id=session.session_id if session else None,
        expires_at=session.expires_at.isoformat() if session else None,
        metadata=metadata,
        exports=_build_exports(result),
    )


@router.post("/sessions/{session_id}/turns", response_model=PromptOptimizeResponse)
def add_prompt_session_turn(session_id: str, request: PromptTurnRequest) -> PromptOptimizeResponse:
    try:
        result, metadata, session = optimizer.add_review_turn(
            session_id,
            request.feedback,
            expected_turn=request.expected_turn,
            idempotency_key=request.idempotency_key,
        )
    except (PromptOptimizerError, PromptSessionError) as error:
        _raise_prompt_error(error)
    return PromptOptimizeResponse(
        result=result,
        turn=session.turn,
        max_turns=session.max_turns,
        session_id=session.session_id,
        expires_at=session.expires_at.isoformat(),
        metadata=metadata,
        exports=_build_exports(result),
    )


@router.get("/sessions/{session_id}", response_model=PromptSessionResponse)
def get_prompt_session(session_id: str) -> PromptSessionResponse:
    try:
        session = optimizer.get_session(session_id)
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
    if not optimizer.delete_session(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "prompt_session_not_found", "message": "审查会话不存在"},
        )
    return {"status": "deleted"}
