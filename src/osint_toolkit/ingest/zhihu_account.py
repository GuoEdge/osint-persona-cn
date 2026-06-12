"""知乎账号数据导入 / Zhihu account ingest."""

from __future__ import annotations

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.likes import save_endorsement
from osint_toolkit.storage.knowledge import log_event


async def ingest_votes(limit: int = 50) -> list[dict]:
    client = HttpClient()
    url = "https://www.zhihu.com/api/v4/members/me/vote_answers?offset=0&limit=20"
    results: list[dict] = []
    try:
        resp = await client.get(url)
        data = resp.json().get("data", [])
        for item in data[:limit]:
            answer = item.get("target", item)
            question = answer.get("question", {})
            url_ = f"https://www.zhihu.com/question/{question.get('id')}/answer/{answer.get('id')}"
            entry = {
                "source": "zhihu",
                "title": question.get("title", ""),
                "url": url_,
                "type": "answer_vote",
            }
            log_event("zhihu_vote", entry)
            save_endorsement(
                platform="zhihu",
                target_type="answer",
                url=url_,
                content=answer.get("excerpt", "") or "",
            )
            results.append(entry)
    except Exception:  # noqa: BLE001
        pass
    return results
