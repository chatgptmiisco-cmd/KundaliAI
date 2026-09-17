from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_birth_profile, require_tier
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.schemas.voice import (
    ExplainChartRequest,
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeResponse,
)
from app.services import user_service
from app.services.chart_service import get_chart
from app.services.interpretation.factory import get_interpreter
from app.services.voice.stt import get_stt_provider
from app.services.voice.tts import get_tts_provider

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe", response_model=TranscribeResponse)
@limiter.limit("10/minute")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: Literal["en", "hi", "hinglish"] = Form("en"),
    _user=Depends(require_tier("insight")),
):
    provider = get_stt_provider()
    try:
        text = await provider.transcribe(await audio.read(), language, audio.filename or "audio.m4a")
    except NotImplementedError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    return TranscribeResponse(text=text, language=language, provider=provider.name, stub=provider.name == "stub")


@router.post("/synthesize", response_model=SynthesizeResponse)
@limiter.limit("10/minute")
async def synthesize(
    request: Request, body: SynthesizeRequest, _user=Depends(require_tier("insight"))
):
    provider = get_tts_provider()
    result = await provider.synthesize(body.text, body.language)
    return SynthesizeResponse(audio_url=result.audio_url, provider=provider.name, stub=result.stub, note=result.note)


@router.post("/explain-chart", response_model=SynthesizeResponse)
@limiter.limit("10/minute")
async def explain_chart(
    request: Request,
    body: ExplainChartRequest,
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_tier("insight")),
):
    """Generates the explanation script via the LLM, then hands it to TTS —
    the two premium voice features (chart explanation + narration) combined
    into one call since the frontend only needs the final audio/text."""
    birth = user_service.decrypt_birth_data(profile)
    chart = await get_chart(db, profile, birth, body.chart_type)

    lagna_sign = chart.lagna_sign_name_hi if body.language == "hi" else chart.lagna_sign_name_en
    context = {
        "lagna_sign": lagna_sign,
        "planets": [
            {
                "planet": p.planet_name_hi if body.language == "hi" else p.planet_name_en,
                "sign": p.sign_name_hi if body.language == "hi" else p.sign_name_en,
                "house": p.house,
                "retrograde": p.retrograde,
            }
            for p in chart.planets
        ],
    }

    interpreter = get_interpreter()
    script = await interpreter.chart_explanation(context, body.chart_type, body.language, body.mode)

    tts_provider = get_tts_provider()
    result = await tts_provider.synthesize(script, body.language)
    return SynthesizeResponse(
        audio_url=result.audio_url, provider=tts_provider.name, stub=result.stub,
        note=script if result.stub else result.note,
    )
