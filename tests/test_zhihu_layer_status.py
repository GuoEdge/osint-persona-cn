"""Zhihu layer status and ingest orchestration tests."""

from osint_toolkit.ingest.zhihu_account import zhihu_layer_status
from osint_toolkit.persona.behavior_signals import score_event


def test_zhihu_layer_status_skip_deprecated_apis():
    status = zhihu_layer_status(
        vote_count=0,
        browse_count=0,
        activity_count=0,
        vote_endpoint=None,
        browse_endpoint=None,
        activity_endpoint=None,
    )
    assert status["votes"]["status"] == "skip"
    assert status["votes"]["layer"] == "extension_post"
    assert status["browse"]["status"] == "empty"
    assert status["browse"]["layer"] == "edge"
    assert status["activity"]["status"] == "skip"
    assert status["activity"]["layer"] == "skip"


def test_zhihu_layer_status_synthetic_activity_ok():
    status = zhihu_layer_status(
        vote_count=0,
        browse_count=2,
        activity_count=0,
        vote_endpoint=None,
        browse_endpoint=None,
        activity_endpoint=None,
        synthetic_count=5,
    )
    assert status["activity"]["status"] == "ok"
    assert status["activity"]["layer"] == "moments_api"


def test_browser_visit_zhihu_content_scores_higher():
    score = score_event(
        "browser_visit",
        {"url": "https://www.zhihu.com/question/1/answer/2", "via": "edge_history"},
    )
    generic = score_event("browser_visit", {"url": "https://example.com/page"})
    assert score > generic
