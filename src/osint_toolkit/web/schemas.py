"""Web API 模型 / Web API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=lambda: ["zhihu", "bilibili", "web"])
    limit: int = 10
    digest: bool = False
    trace: bool = True
    profile: str = "default"
    ai_instruct: str = ""
    no_ai: bool = False
    no_simulate: bool = False
    disabled_ai_steps: list[str] = Field(default_factory=list)
    deep_top: int = 0
    comment_mine_top: int | None = None
    include_slurs: bool | None = None
    mine_comments: bool = True


class SearchExpandRequest(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=lambda: ["zhihu", "bilibili", "web"])
    no_ai: bool = False
    include_slurs: bool | None = None


class SaveRequest(BaseModel):
    url: str
    with_comments: bool = False
    no_ai: bool = False


class FeedbackRequest(BaseModel):
    target_id: str
    rating: str
    reason: str = ""
    run_id: str | None = None
    step: str | None = None
    target_type: str = "item"
    sim_verdict: str = ""


class AskRequest(BaseModel):
    question: str
    run_id: str | None = None


class PersonaRollbackRequest(BaseModel):
    version: int


class IngestBrowserRequest(BaseModel):
    since_days: int = 90


class IngestAicuJsonRequest(BaseModel):
    pages: list[dict[str, Any]] = Field(default_factory=list)
    replies: list[dict[str, Any]] = Field(default_factory=list)
    payload: Any = None


class SyncCookiesRequest(BaseModel):
    browser: str | None = None
    domains: list[str] = Field(default_factory=list)


class ImportCookiesRequest(BaseModel):
    browser: str = "extension"
    domains: dict[str, str] = Field(default_factory=dict)


class DirectivesUpdate(BaseModel):
    data: dict[str, Any]


class PromptUpdate(BaseModel):
    text: str


class ExtensionEventItem(BaseModel):
    kind: str = ""
    type: str = ""
    url: str = ""
    title: str = ""
    duration_ms: int = 0
    platform: str = ""
    body: dict[str, Any] | list[Any] | None = None
    event_type: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ExtensionEventsRequest(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)
    version: str = ""


class ExtensionPingRequest(BaseModel):
    version: str = ""
    enabled: bool = True


class BrowserSyncRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["bilibili", "zhihu"])
    mode: str = ""
    headless: bool | None = None
