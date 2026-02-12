from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_authenticated_user_id
from app.models.ai_summary import AISummaryPrompt
from app.models.patient import Patient
from app.schemas.summary import BuildPromptRequest, PasteResponseRequest, PromptResponse
from app.services.ai.prompt_builder import build_prompt

router = APIRouter(prefix="/summary", tags=["summary"])


@router.post("/build-prompt", response_model=PromptResponse)
async def build_prompt_endpoint(
    body: BuildPromptRequest,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> PromptResponse:
    """Build a de-identified prompt. Returns the prompt, NOT an AI response."""
    # Verify patient belongs to user
    result = await db.execute(
        select(Patient).where(Patient.id == body.patient_id, Patient.user_id == user_id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        prompt_data = await build_prompt(
            db=db,
            user_id=user_id,
            patient_id=body.patient_id,
            summary_type=body.summary_type,
            category=body.category,
            date_from=body.date_from,
            date_to=body.date_to,
            record_ids=body.record_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Store the prompt
    prompt_record = AISummaryPrompt(
        id=uuid4(),
        user_id=user_id,
        patient_id=body.patient_id,
        summary_type=body.summary_type,
        scope_filter={
            "category": body.category,
            "date_from": body.date_from.isoformat() if body.date_from else None,
            "date_to": body.date_to.isoformat() if body.date_to else None,
        },
        system_prompt=prompt_data["system_prompt"],
        user_prompt=prompt_data["user_prompt"],
        target_model=prompt_data["target_model"],
        suggested_config=prompt_data["suggested_config"],
        record_count=prompt_data["record_count"],
        de_identification_log=prompt_data["de_identification_report"],
        generated_at=datetime.now(timezone.utc),
    )
    db.add(prompt_record)
    await db.commit()
    await db.refresh(prompt_record)

    return PromptResponse(
        id=prompt_record.id,
        summary_type=prompt_data["summary_type"],
        system_prompt=prompt_data["system_prompt"],
        user_prompt=prompt_data["user_prompt"],
        target_model=prompt_data["target_model"],
        suggested_config=prompt_data["suggested_config"],
        record_count=prompt_data["record_count"],
        de_identification_report=prompt_data["de_identification_report"],
        copyable_payload=prompt_data["copyable_payload"],
        generated_at=prompt_record.generated_at,
    )


@router.get("/prompts")
async def list_prompts(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List previously built prompts."""
    result = await db.execute(
        select(AISummaryPrompt)
        .where(AISummaryPrompt.user_id == user_id)
        .order_by(AISummaryPrompt.generated_at.desc())
    )
    prompts = result.scalars().all()
    return {
        "items": [
            {
                "id": str(p.id),
                "summary_type": p.summary_type,
                "record_count": p.record_count,
                "target_model": p.target_model,
                "has_response": p.response_text is not None,
                "generated_at": p.generated_at.isoformat() if p.generated_at else None,
            }
            for p in prompts
        ],
        "total": len(prompts),
    }


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: UUID,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get prompt detail for re-copying."""
    result = await db.execute(
        select(AISummaryPrompt).where(
            AISummaryPrompt.id == prompt_id,
            AISummaryPrompt.user_id == user_id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    copyable = f"System: {prompt.system_prompt}\n\nUser: {prompt.user_prompt}"

    return {
        "id": str(prompt.id),
        "summary_type": prompt.summary_type,
        "system_prompt": prompt.system_prompt,
        "user_prompt": prompt.user_prompt,
        "target_model": prompt.target_model,
        "suggested_config": prompt.suggested_config,
        "record_count": prompt.record_count,
        "de_identification_report": prompt.de_identification_log,
        "copyable_payload": copyable,
        "response_text": prompt.response_text,
        "generated_at": prompt.generated_at.isoformat() if prompt.generated_at else None,
    }


@router.post("/paste-response")
async def paste_response(
    body: PasteResponseRequest,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """User pastes AI response back for storage."""
    result = await db.execute(
        select(AISummaryPrompt).where(
            AISummaryPrompt.id == body.prompt_id,
            AISummaryPrompt.user_id == user_id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt.response_text = body.response_text
    prompt.response_pasted_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "stored", "prompt_id": str(prompt.id)}


@router.get("/responses")
async def list_responses(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List stored responses."""
    result = await db.execute(
        select(AISummaryPrompt)
        .where(
            AISummaryPrompt.user_id == user_id,
            AISummaryPrompt.response_text.isnot(None),
        )
        .order_by(AISummaryPrompt.response_pasted_at.desc())
    )
    prompts = result.scalars().all()
    return {
        "items": [
            {
                "id": str(p.id),
                "summary_type": p.summary_type,
                "record_count": p.record_count,
                "response_text": p.response_text[:200] if p.response_text else None,
                "response_pasted_at": p.response_pasted_at.isoformat()
                if p.response_pasted_at
                else None,
            }
            for p in prompts
        ],
        "total": len(prompts),
    }
