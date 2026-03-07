from typing import Any

from pydantic import BaseModel, Field


class MemoryEventCreate(BaseModel):
    type: str = Field(..., pattern="^(page_visit|highlight|snippet)$")
    url: str
    timestamp: str
    title: str | None = None
    text: str | None = None
    metadata: dict[str, Any] | None = None


class MemoryEvent(BaseModel):
    id: int
    type: str
    url: str
    title: str | None
    text: str | None
    timestamp: str
    metadata: dict[str, Any] | None


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class QueryRequest(BaseModel):
    query: str
    limit: int = 5
    date: str | None = None  # optional YYYY-MM-DD to restrict to that day


class QueryResponse(BaseModel):
    answer: str


class TimelineDay(BaseModel):
    date: str
    events: list[MemoryEvent]
