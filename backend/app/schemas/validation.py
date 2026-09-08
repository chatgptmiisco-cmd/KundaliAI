from pydantic import BaseModel


class ValidationQuestion(BaseModel):
    period_start: str
    period_end: str
    lord: str
    house: int
    statement: str


class ValidationQuestionsResponse(BaseModel):
    language: str
    questions: list[ValidationQuestion]
