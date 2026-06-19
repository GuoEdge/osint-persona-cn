"""Web API 模型 / Web API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from osint_toolkit.collectors.registry import DEFAULT_SEARCH_SOURCES


class SearchRequest(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SEARCH_SOURCES))
    limit: int = 10
    digest: bool = False
    trace: bool = False
    profile: str = "default"
    ai_instruct: str = ""
    no_ai: bool = False
    no_simulate: bool = False
    disabled_ai_steps: list[str] = Field(default_factory=list)
    deep_top: int = 0
    comment_mine_top: int | None = None
    include_slurs: bool | None = None
    mine_comments: bool = True
    serp_fallback_accepted: list[str] = Field(default_factory=list)
    comment_mine_sources: list[str] | None = None
    tree_id: str | None = None
    parent_node_id: str | None = None
    fork_from_run_id: str | None = None
    create_tree: bool = False
    source_overrides: dict[str, list[str]] | None = None


class SearchExpandRequest(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SEARCH_SOURCES))
    no_ai: bool = False
    include_slurs: bool | None = None
    profile: str = "default"
    source_overrides: dict[str, list[str]] | None = None


class SaveRequest(BaseModel):
    url: str
    with_comments: bool = False
    no_ai: bool = False


class SaveRunItemsRequest(BaseModel):
    item_ids: list[str] | None = None
    min_relevance: float = 0.25
    tags: list[str] | None = None


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
    tree_id: str | None = None
    parent_node_id: str | None = None
    history: list[dict[str, str]] = []


class ResearchTreeCreate(BaseModel):
    title: str
    query: str = ""


class ResearchNodeCreate(BaseModel):
    parent_id: str | None = None
    kind: str = "note"
    title: str = ""
    payload: str = ""
    run_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ResearchNodePatch(BaseModel):
    title: str | None = None
    payload: str | None = None
    meta: dict[str, Any] | None = None


class ResearchSuggestRequest(BaseModel):
    tree_id: str | None = None
    run_id: str | None = None
    node_id: str | None = None


class ResearchInsightRequest(BaseModel):
    tree_id: str
    run_id: str
    parent_node_id: str | None = None


class PersonaRollbackRequest(BaseModel):
    version: int


class RunsCleanupRequest(BaseModel):
    older_than_days: int = 30
    keep_latest: int = 20
    dry_run: bool = False
    statuses: list[str] = Field(
        default_factory=lambda: ["done", "error", "interrupted", "cancelled", "unknown"]
    )


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
    pending_queue: int = 0
    last_flush_error: str = ""


class BrowserSyncRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["bilibili", "zhihu"])
    mode: str = ""
    headless: bool | None = None


class SecretSaveRequest(BaseModel):
    value: str


class TunablePatchRequest(BaseModel):
    values: dict[str, Any]
