"""Interpretation layer interface.

Business logic (what astrology data to gather, caching, quota checks) lives
in the service layer, not here — this module's only job is "given structured
chart/dasha/transit context, produce simple-language text in the requested
language". Swapping providers (Claude → GPT → something else) means writing
one new class against this interface; nothing else changes.
"""
from abc import ABC, abstractmethod
from typing import Any, Literal

Language = Literal["en", "hi", "hinglish"]
Mode = Literal["simple", "detailed"]


class Interpreter(ABC):
    @abstractmethod
    async def daily_horoscope(
        self, context: dict[str, Any], language: Language, mode: Mode
    ) -> dict[str, Any]:
        """Returns {tone, focus_areas: list[str], tip, summary_text}."""

    @abstractmethod
    async def period_analysis(
        self, context: dict[str, Any], language: Language, mode: Mode
    ) -> dict[str, Any]:
        """Returns {rating: int 1-10, theme, risks: list[str], opportunities: list[str], summary}."""

    @abstractmethod
    async def chart_explanation(
        self, context: dict[str, Any], chart_type: str, language: Language, mode: Mode
    ) -> str:
        """Returns a short spoken-style explanation script for `chart_type`."""

    @abstractmethod
    async def chart_summary(
        self, context: dict[str, Any], chart_type: str, language: Language, mode: Mode
    ) -> dict[str, Any]:
        """Returns {summary: str, key_points: list[str]} — the short written
        (not spoken) description shown alongside a chart's placements."""

    @abstractmethod
    async def manglik_explanation(
        self, context: dict[str, Any], language: Language, mode: Mode
    ) -> dict[str, Any]:
        """Returns {summary, details: list[str], cancellations: list[str],
        relationship_note}. `context` already carries the computed
        is_manglik/mars_house_from_lagna/mars_house_from_moon facts — this
        only turns them into calm, plain-language prose, never inventing or
        contradicting the given facts."""

    @abstractmethod
    async def complete_kundali(
        self, context: dict[str, Any], language: Language, mode: Mode
    ) -> dict[str, Any]:
        """Returns {sections: {personality_nature, career_money,
        relationships_marriage, health_temperament, strengths_challenges,
        timing_overview}: each {summary, key_points}, brutal_truth,
        core_strength, core_challenge}."""

    @abstractmethod
    async def chat_reply(
        self, history: list[dict[str, str]], context: dict[str, Any], language: Language
    ) -> str:
        """Returns the assistant's next reply given prior turns + chart context."""
