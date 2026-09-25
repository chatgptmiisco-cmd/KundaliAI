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


class ChatHistoryMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    text: str
    created_at: str  # ISO 8601 — the frontend only ever needs to sort/display it


class ChatHistoryOut(BaseModel):
    messages: list[ChatHistoryMessageOut]


class ChatMessageIn(BaseModel):
    message: str
    language: Literal["en", "hi", "hinglish"] = "en"
    # Which Rishi persona the user is talking to (see RISHIS in the frontend
    # and _RISHI_SPECIALTY in templates.py) — optional and unvalidated
    # against a fixed enum so an unrecognized/omitted id just falls back to
    # the old persona-agnostic universal router rather than erroring.
    rishi_id: str | None = None
    engine_only: bool = False


class ChatMessageOut(BaseModel):
    reply: str
    language: str
    # Which of the 5 specialist Rishis classically owns this message's real
    # topic (see templates.detect_answering_rishi) — independent of which
    # persona the user is actually chatting with, so the generalist "vyasa"
    # persona's replies can still be attributed to a real specialist (e.g.
    # "via Bhrigu"). None when the message didn't match a known category.
    answered_by_rishi_id: str | None = None
    response_source: Literal["native", "native_styled"] = "native"
    question_type: Literal["information", "prediction", "decision", "problem", "confirmation", "clarification"] = "information"
