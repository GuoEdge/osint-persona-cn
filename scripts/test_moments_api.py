"""测试 HttpClient 能否直接调 /api/v3/moments/{token}/activities。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.http.client import HttpClient


async def main() -> None:
    c = HttpClient()
    token = "sankichu"

    # 测试 1: 基础调用
    url = f"https://www.zhihu.com/api/v3/moments/{token}/activities?limit=5&desktop=true&ws_qiangzhisafe=0"
    resp = await c.get(url, headers={"Referer": f"https://www.zhihu.com/people/{token}/activities"})
    print(f"status={resp.status_code}")
    d = resp.json()
    data = d.get("data") or []
    print(f"items={len(data)}")

    if data:
        for i, item in enumerate(data[:3]):
            verb = item.get("verb")
            created = item.get("created_time")
            target = item.get("target") or {}
            question = target.get("question") or {}
            title = question.get("title") or target.get("title") or ""
            tid = target.get("id")
            print(f"  [{i}] verb={verb} time={created} target_id={tid} title={title[:60]}")

        paging = d.get("paging") or {}
        print(f"\npaging keys: {list(paging.keys())}")
        print(f"is_end: {paging.get('is_end')}")
        print(f"next: {str(paging.get('next', ''))[:120]}")

        # 测试 2: 翻页
        next_url = paging.get("next")
        if next_url:
            print(f"\n=== 翻页测试 ===")
            resp2 = await c.get(next_url, headers={"Referer": f"https://www.zhihu.com/people/{token}/activities"})
            d2 = resp2.json()
            data2 = d2.get("data") or []
            print(f"page 2: status={resp2.status_code} items={len(data2)}")
            if data2:
                item = data2[0]
                print(f"  first verb: {item.get('verb')} time: {item.get('created_time')}")

        # 测试 3: 带 offset 参数（时间戳游标）
        print(f"\n=== offset 翻页测试 ===")
        first_created = data[0].get("created_time")
        offset_url = f"https://www.zhihu.com/api/v3/moments/{token}/activities?offset={first_created}&page_num=1"
        resp3 = await c.get(offset_url, headers={"Referer": f"https://www.zhihu.com/people/{token}/activities"})
        d3 = resp3.json()
        data3 = d3.get("data") or []
        print(f"offset page: status={resp3.status_code} items={len(data3)}")
    else:
        print("无数据！检查 body:")
        print(d)


if __name__ == "__main__":
    asyncio.run(main())
