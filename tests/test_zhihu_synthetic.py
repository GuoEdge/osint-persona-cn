"""Zhihu synthetic activity tests."""

from osint_toolkit.ingest.zhihu_synthetic import build_synthetic_activities


def test_build_synthetic_activities_merges_types():
    votes = [{"url": "https://www.zhihu.com/question/1/answer/1", "title": "A", "created_time": 100}]
    favorites = [{"url": "https://zhuanlan.zhihu.com/p/2", "title": "B"}]
    answers = [{"url": "https://www.zhihu.com/question/3/answer/3", "title": "C", "created_time": 200}]
    out = build_synthetic_activities(votes=votes, favorites=favorites, answers=answers, limit=10)
    assert len(out) == 3
    kinds = {e["event_kind"] for e in out}
    assert "answer_vote" in kinds
    assert "activity_favorite" in kinds
    assert "create_answer" in kinds
    assert out[0]["via"] == "synthetic_timeline"


def test_build_synthetic_dedupes_same_url():
    vote = {"url": "https://www.zhihu.com/question/1/answer/1", "title": "A"}
    out = build_synthetic_activities(votes=[vote, vote], limit=10)
    assert len(out) == 1
