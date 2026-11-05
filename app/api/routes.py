from uuid import uuid4

from app.storage.database import (
    get_owned_analysis_session,
    owns_dataset,
    save_analysis_session_owned,
    get_owned_report_asset,
    get_owned_report_assets,
    list_owned_datasets,
    get_owned_dataset_details,
    delete_owned_dataset,
    list_owned_sessions,
    list_owned_reports,
    list_owned_traces,
    list_evaluations,
    run_evaluation,
)

from fastapi import APIRouter, HTTPException, Depends
from app.auth import Principal, get_user_id, require_principal
from pydantic import BaseModel, Field
import re
from pathlib import Path
import os
from fastapi.responses import StreamingResponse

import asyncio
import threading

from app.graph.workflow import create_analysis_graph
from app.services.suggestion_service import generate_suggested_questions
from app.security import MAX_CONCURRENT_ANALYSES


router = APIRouter()

analysis_graph = create_analysis_graph()
# Bounded semaphore: each analysis loads a full DataFrame into
# memory.  Reject requests beyond MAX_CONCURRENT_ANALYSES with
# HTTP 503 rather than exhausting process memory.
_analysis_semaphore = threading.Semaphore(MAX_CONCURRENT_ANALYSES)
PRIVATE_REPORT_ROOT = Path(__file__).resolve().parents[2] / "reports" / "private"


def _safe_report(text: str) -> str:
    """Avoid returning generated server filesystem paths in API text."""
    return re.sub(r"(?:[A-Za-z]:[\\/]|/(?:[^\s`]+/)+)[^\s`]*", "[private asset]", text)


def _open_private_asset(relative_path: str, private_root: Path):
    candidate = private_root / relative_path
    try:
        if candidate.is_symlink():
            raise ValueError
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(private_root)
        if not resolved.is_file():
            raise ValueError
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        opened = os.fdopen(descriptor, "rb")
        if not os.path.samefile(resolved, opened.fileno()):
            opened.close()
            raise ValueError
        return opened
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Chart not found.") from None


class AnalyzeRequest(BaseModel):
    user_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language analytical question.",
    )

    dataset_id: str = Field(
        ...,
        min_length=1,
        max_length=36,
        description="Opaque ID returned by the dataset upload endpoint.",
    )


class AnalyzeResponse(BaseModel):
    session_id: str
    status: str
    user_query: str
    dataset_id: str

    analysis_plan: list = Field(default_factory=list)
    tool_calls: list = Field(default_factory=list)
    findings: list = Field(default_factory=list)
    visualizations: list = Field(default_factory=list)
    evidence: list = Field(default_factory=list)
    validation_results: list = Field(default_factory=list)
    errors: list = Field(default_factory=list)

    final_report: str = ""


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "autonomous-data-analyst",
    }


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    if not owns_dataset(request.dataset_id, owner_id):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    session_id = str(uuid4())

    initial_state = {
        "session_id": session_id,
        "user_query": request.user_query,
        "dataset_id": request.dataset_id,
        "owner_user_id": owner_id,
        "status": "created",
        "replan_count": 0,
        "max_replans": 2,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }

    if not _analysis_semaphore.acquire(blocking=True, timeout=60):
        raise HTTPException(
            status_code=503,
            detail="Server is busy. Please retry shortly.",
        )
    try:
        result = analysis_graph.invoke(initial_state)
        save_analysis_session_owned(result, owner_id)

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Dataset could not be processed.",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Analysis execution failed.",
        ) from exc
    finally:
        _analysis_semaphore.release()

    return AnalyzeResponse(
        session_id=result.get("session_id", session_id),
        status=result.get("status", "failed"),
        user_query=result.get("user_query", request.user_query),
        dataset_id=result.get("dataset_id", request.dataset_id),
        analysis_plan=result.get("analysis_plan", []),
        tool_calls=result.get("tool_calls", []),
        findings=result.get("findings", []),
        visualizations=[
            f"/api/analysis/{session_id}/charts/{asset['asset_id']}"
            for asset in get_owned_report_assets(session_id, owner_id)
        ],
        evidence=[{**item, "result": "[private asset]" if item.get("operation", "").startswith("create_") else item.get("result")} for item in result.get("evidence", [])],
        validation_results=result.get("validation_results", []),
        errors=[_safe_report(str(error)) for error in result.get("errors", [])],
        final_report=_safe_report(result.get("final_report", "")),
    )
@router.get("/analysis/{session_id}")
def get_analysis(session_id: str, principal: Principal = Depends(require_principal)):
    session = get_owned_analysis_session(session_id, get_user_id(principal))

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis session not found.",
        )

    session["final_report"] = _safe_report(session.get("final_report", ""))
    session["errors"] = [_safe_report(str(error)) for error in session.get("errors", [])]
    session["evidence"] = [{**item, "result": "[private asset]" if item.get("operation", "").startswith("create_") else item.get("result")} for item in session.get("evidence", [])]
    session["visualizations"] = [
        f"/api/analysis/{session_id}/charts/{asset['asset_id']}"
        for asset in get_owned_report_assets(session_id, get_user_id(principal))
    ]
    return session


@router.get("/analysis/{session_id}/charts/{asset_id}")
def get_analysis_chart(session_id: str, asset_id: str, principal: Principal = Depends(require_principal)):
    asset = get_owned_report_asset(session_id, asset_id, get_user_id(principal))
    if asset is None or asset["media_type"] != "image/png":
        raise HTTPException(status_code=404, detail="Chart not found.")
    private_root = PRIVATE_REPORT_ROOT.resolve()
    opened = _open_private_asset(asset["relative_path"], private_root)

    async def chunks():
        try:
            while chunk := opened.read(64 * 1024):
                yield chunk
        finally:
            opened.close()

    return StreamingResponse(
        chunks(),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )


# ---------------------------------------------------------
# Workspace Module Endpoints
# ---------------------------------------------------------

@router.get("/datasets")
def get_datasets(principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    return list_owned_datasets(owner_id)


@router.get("/datasets/item/{dataset_id}")
def get_dataset_item(dataset_id: str, principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    dataset = get_owned_dataset_details(dataset_id, owner_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


@router.delete("/datasets/item/{dataset_id}")
def delete_dataset_item(dataset_id: str, principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    success = delete_owned_dataset(dataset_id, owner_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return {"status": "deleted", "dataset_id": dataset_id}


@router.get("/datasets/{dataset_id}/suggested-questions")
@router.get("/datasets/suggested-questions/{dataset_id}")
def get_dataset_suggested_questions(
    dataset_id: str,
    offset: int = 0,
    principal: Principal = Depends(require_principal),
):
    owner_id = get_user_id(principal)
    if not owns_dataset(dataset_id, owner_id):
        raise HTTPException(status_code=404, detail="Dataset not found.")

    details = get_owned_dataset_details(dataset_id, owner_id)
    profile = (details or {}).get("profile")
    if not profile:
        from app.tools.data_tools import load_dataset_by_id, profile_dataset
        df = load_dataset_by_id(dataset_id)
        profile = profile_dataset(df)

    return generate_suggested_questions(dataset_id, profile, offset=offset)


@router.get("/sessions")
def get_sessions(principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    return list_owned_sessions(owner_id)


@router.get("/reports")
def get_reports(principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    return list_owned_reports(owner_id)


@router.get("/traces")
def get_traces(principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    return list_owned_traces(owner_id)


@router.get("/evaluations")
def get_evaluations(principal: Principal = Depends(require_principal)):
    owner_id = get_user_id(principal)
    return list_evaluations(owner_id)


class RunEvaluationRequest(BaseModel):
    benchmark_id: str | None = None


@router.post("/evaluations/run")
def post_run_evaluation(
    request: RunEvaluationRequest = RunEvaluationRequest(),
    principal: Principal = Depends(require_principal),
):
    owner_id = get_user_id(principal)
    try:
        return run_evaluation(request.benchmark_id, owner_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Evaluation execution failed.")
