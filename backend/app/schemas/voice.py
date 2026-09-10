from typing import Literal

from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    text: str
    language: str
    provider: str
    stub: bool


class SynthesizeRequest(BaseModel):
    text: str
    language: Literal["en", "hi"] = "en"


class SynthesizeResponse(BaseModel):
    audio_url: str | None
    provider: str
    stub: bool
    note: str


class ExplainChartRequest(BaseModel):
    chart_type: Literal["D1", "D9", "D10"]
    language: Literal["en", "hi"] = "en"
    mode: Literal["simple", "detailed"] = "simple"


class ChatMessageIn(BaseModel):
    message: str
    language: Literal["en", "hi"] = "en"
    # Which Rishi persona the user is talking to (see RISHIS in the frontend
    # and _RISHI_SPECIALTY in templates.py) — optional and unvalidated
    # against a fixed enum so an unrecognized/omitted id just falls back to
    # the old persona-agnostic universal router rather than erroring.
    rishi_id: str | None = None


class ChatMessageOut(BaseModel):
    reply: str
    language: str
