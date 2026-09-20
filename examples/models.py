"""Pydantic output models used by example agents."""

from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    """Structured code-review result."""

    accepted: bool
    score: float = Field(ge=0, le=1)
    findings: list[str]


class ReviewFinding(BaseModel):
    """One finding tied to a source location."""

    path: str
    line: int = Field(ge=1)
    message: str


class NestedReviewResult(BaseModel):
    """Review result with typed, nested findings."""

    accepted: bool
    findings: list[ReviewFinding]
