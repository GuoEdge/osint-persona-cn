"""Pipeline integration tests — verify critical behaviors that previously lacked coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import search as search_mod


# ── Comment mining: quota pre-filter by type ──

@pytest.mark.asyncio
async def test_comment_mine_type_filter_fills_quota(monkeypatch):
    """Quota slots wasted by wrong-type items are filled by next valid candidate."""
    items = []
    for i in range(10):
        item = IntelItem(
            source="bilibili",
            type="video" if i >= 2 else "bili_user",
            url=f"https://bilibili.com/video/BV{i:08d}",
            title=f"Video {i}",
            content="test",
        )
        item.signals.relevance = 1.0 - i * 0.05
        item.personal["matched_queries"] = ["test"]
        items.append(item)

    fake_bili = AsyncMock()
    fake_bili.fetch_comments = AsyncMock(return_value=[{"content": "ok"}])
    monkeypatch.setattr(search_mod, "BilibiliCollector", lambda: fake_bili)
    monkeypatch.setattr(search_mod, "summarize_comments", AsyncMock(return_value="summary"))
    monkeypatch.setattr(search_mod, "get_search_config", lambda: {})
    monkeypatch.setattr(search_mod, "is_step_enabled", lambda *a, **k: True)

    mined = await search_mod._mine_comments(
        items,
        top=5,
        no_ai=False,
    )
    comment_counts = [e["comment_count"] for e in mined]
    assert len(mined) == 5
    assert sum(1 for c in comment_counts if c > 0) == 5


@pytest.mark.asyncio
async def test_comment_mine_skips_zhihu_if_not_answer(monkeypatch):
    """Zhihu items not of type answer/article/question are bypassed."""
    items = []
    for i in range(8):
        item = IntelItem(
            source="zhihu",
            type="answer" if i % 2 == 0 else "pin",
            url=f"https://zhihu.com/item/{i}",
            title=f"Item {i}",
            content="test",
        )
        item.signals.relevance = 0.9
        item.personal["matched_queries"] = ["test"]
        items.append(item)

    fake_zhihu = AsyncMock()
    fake_zhihu.fetch_comments = AsyncMock(return_value=[{"content": "ok"}])
    monkeypatch.setattr(search_mod, "ZhihuCollector", lambda: fake_zhihu)
    monkeypatch.setattr(search_mod, "heuristic_zhihu_deep_plan", lambda item, cfg: {"fetch_comments": True})
    monkeypatch.setattr(search_mod, "merge_comment_lists", lambda a, b: a + b)
    monkeypatch.setattr(search_mod, "summarize_comments", AsyncMock(return_value="summary"))

    mined = await search_mod._mine_comments(
        items,
        top=8,
        no_ai=False,
        comment_mine_sources=["zhihu"],
    )
    assert len(mined) == 4


# ── _record_step progress_detail passthrough ──

def test_record_step_passes_progress_detail(tmp_path, monkeypatch):
    """_record_step must pass progress_detail to update_progress without default override."""
    captured: list[str] = []

    def fake_update(run_id, name, *, detail="", **kw):
        if detail:
            captured.append(detail)

    class FakeRunner:
        def begin_step(self, name, *, input_summary="", ai_invoked=False):
            path = tmp_path / f"_step_{name}.json"
            path.write_text("{}", encoding="utf-8")
            return path

        def _append_trace(self, result):
            pass

    async def run():
        await search_mod._record_step(
            FakeRunner(),
            "collect_all",
            pass_through(),
            run_id="test-run",
            progress_detail="多源采集（共 12 项）…",
        )

    async def pass_through():
        return "done"

    monkeypatch.setattr(search_mod, "update_progress", fake_update)
    monkeypatch.setattr(search_mod, "check_cancelled", lambda rid: None)

    import asyncio
    asyncio.run(run())
    assert len(captured) >= 1
    assert captured[0] == "多源采集（共 12 项）…"


# ── Subtitle wrong-track detection (Chinese keywords) ──

def test_subtitle_wrong_track_chinese_keywords_match():
    from osint_toolkit.ingest.bilibili_sdk import _subtitle_likely_wrong_track, _title_keywords

    title = "Kimi K2.6 代码能力已经可以和GPT 5.4 掰掰手腕了吗？"
    keywords = _title_keywords(title)
    assert len(keywords) > 2
    assert "Kimi" in keywords

    good_subtitle = "Kimi K2.6 的代码能力确实很强，我们对比了多个模型 GLM GPT 浪浪妈雷达图"
    assert _subtitle_likely_wrong_track(good_subtitle, title) is False

    bad_subtitle = (
        "主驾调到23度了 打开左前方窗户 打开座椅通风 关闭窗户 导航到西湖 去第几个 第一个 "
        "规划好了 前方红绿灯请直行 300米处有限速 50拍照 当前车速51 即将超车 随后200米右转 "
        "请注意 接管200米后 在道路尽头右转 领航即将退出 右转随后立即右转 领航开始了 500米后 "
        "有长实线请驶入 即将变道 600米后向右前方下高架 向右前方下高架 开始泊车了 注意周围安全 "
        "System check Ok proceed to test 过往的记忆已经随时间散去只剩散落一地的曾经飘落的枫叶"
        + "想思我的思念变成温暖我的冬天这世界反复颠倒我把我珍藏的枫叶却留着熟悉的味道"
        + " ".join(["passage track filter gate brake"] * 8)
    )
    assert _subtitle_likely_wrong_track(bad_subtitle, title) is True


def test_subtitle_wrong_track_pure_chinese_title():
    from osint_toolkit.ingest.bilibili_sdk import _subtitle_likely_wrong_track

    title = "Kimi人工智能AI大模型实战教程"
    good_sub = "大家好今天我们来学习Kimi大模型的实战应用包括文本生成代码辅助等方面"
    assert _subtitle_likely_wrong_track(good_sub, title) is False

    bad_sub = (
        "Got me miss understood But at least I look this is good 11岁 你们不要骗我 "
        "数学作业 物理和科学了吧 怎么办啊 你欺负我不成的话 你欺负我不成之 你看我今天能不能帮到你 "
        "你还不准备 马上要开始了 你说写啥呀 你看我作业 我不想写 马上开学了 作业一大堆写不完 "
        "小外甥自己在那 我帮不了你 你写作业 你就会黑白谁不会啊 我的姑奶奶别哭了 我的姑奶奶 你写作业呀 "
        "别人家写作业写呀 那个什么 逗你玩的 我的天呀"
        + " ".join(["random gabble nonsense filler"] * 10)
    )
    assert _subtitle_likely_wrong_track(bad_sub, title) is True


def test_subtitle_wrong_track_short_text_skipped():
    from osint_toolkit.ingest.bilibili_sdk import _subtitle_likely_wrong_track

    title = "测试视频标题"
    assert _subtitle_likely_wrong_track("短文本", title) is False  # < 200 chars


# ── B站 auth reset on new instance ──

def test_bilibili_auth_flag_resets_on_new_instance():
    from osint_toolkit.collectors.bilibili import BilibiliCollector

    BilibiliCollector._auth_failed = True
    BilibiliCollector._auth_warning_shown = True

    collector = BilibiliCollector()
    assert collector._auth_failed is False
    assert collector._auth_warning_shown is False


# ── B站 auth error code detection ──

def test_bilibili_check_reply_auth_codes():
    from osint_toolkit.collectors.bilibili import BilibiliCollector

    BilibiliCollector._auth_failed = False
    BilibiliCollector._auth_warning_shown = False

    BilibiliCollector._check_reply_auth(-403, "访问权限不足")
    assert BilibiliCollector._auth_failed is True

    BilibiliCollector._auth_failed = False
    BilibiliCollector._check_reply_auth(-101, "账号未登录")
    assert BilibiliCollector._auth_failed is True

    BilibiliCollector._auth_failed = False
    BilibiliCollector._check_reply_auth(-404, "not found")
    assert BilibiliCollector._auth_failed is False
