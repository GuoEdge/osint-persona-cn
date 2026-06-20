"""用 Playwright 打开知乎 activities 页面，拦截所有 XHR，找点赞/动态相关 API。

Persistent 模式：使用 Edge 用户数据目录（需关闭 Edge）。
CDP 模式：附着已开调试端口的 Edge（需先开 --remote-debugging-port=9222）。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


async def main() -> None:
    from playwright.async_api import async_playwright

    from osint_toolkit.ingest.browser_sync import edge_user_data_dir, edge_profile_locked
    from osint_toolkit.auth.cookie_sync import cookies_for_playwright

    token = "sankichu"
    target_url = f"https://www.zhihu.com/people/{token}/activities"

    captured_xhrs: list[dict] = []

    async def on_response(response):
        url = response.url or ""
        if "/api/v4/" not in url and "/api/v3/" not in url:
            return
        try:
            body = None
            try:
                body = await response.json()
            except Exception:
                pass
            data_count = -1
            if isinstance(body, dict):
                d = body.get("data")
                if isinstance(d, list):
                    data_count = len(d)
                elif isinstance(d, dict):
                    data_count = 1
            captured_xhrs.append({
                "url": url[:200],
                "status": response.status,
                "method": response.request.method,
                "data_count": data_count,
                "body_keys": list(body.keys())[:8] if isinstance(body, dict) else [],
            })
            print(f"  [{response.request.method}] {response.status} data={data_count} {url[:120]}")
            if data_count and data_count > 0 and isinstance(body, dict):
                data = body.get("data")
                if isinstance(data, list) and data:
                    first = data[0] if isinstance(data[0], dict) else {}
                    print(f"    first item keys: {list(first.keys())[:10]}")
                    verb = first.get("verb") or first.get("type") or ""
                    if verb:
                        print(f"    verb/type: {verb}")
        except Exception as exc:
            print(f"  [ERR] {url[:80]}: {exc}")

    async with async_playwright() as pw:
        # 优先 CDP 模式，其次 persistent，最后 cookies（headless）
        mode = "cdp"
        browser = None
        context = None
        try:
            browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            print("CDP 模式连接成功")
        except Exception:
            if not edge_profile_locked():
                udd = edge_user_data_dir()
                if udd:
                    try:
                        mode = "persistent"
                        print(f"Persistent 模式: {udd}")
                        context = await pw.chromium.launch_persistent_context(
                            str(udd),
                            channel="msedge",
                            headless=False,
                            viewport={"width": 1280, "height": 900},
                        )
                        pw_cookies = cookies_for_playwright()
                        if pw_cookies:
                            await context.add_cookies(pw_cookies)
                    except Exception as exc:
                        print(f"persistent 失败: {exc}")
                        context = None
            if context is None:
                mode = "cookies"
                print("Cookies 模式 (headless)")
                browser = await pw.chromium.launch(channel="msedge", headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
                )
                pw_cookies = cookies_for_playwright()
                if pw_cookies:
                    await context.add_cookies(pw_cookies)
                else:
                    print("警告: 无 Cookie 文件")

        try:
            page = context.pages[0] if context.pages else await context.new_page()
            page.on("response", on_response)

            print(f"\n=== 打开 {target_url} ===")
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print(f"goto error: {exc}")

            await asyncio.sleep(5)

            # 检查是否被风控
            title = await page.title()
            print(f"  title: {title}")

            # 尝试滚动
            print("\n=== 滚动触发更多 XHR ===")
            for i in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            # 也试试切换到其它 Tab
            for tab_path in [f"/people/{token}/answers", f"/people/{token}/collections"]:
                tab_url = f"https://www.zhihu.com{tab_path}"
                print(f"\n=== 打开 {tab_url} ===")
                page.remove_listener("response", on_response)
                page.on("response", on_response)
                try:
                    await page.goto(tab_url, wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3)
                    for i in range(3):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2)
                except Exception as exc:
                    print(f"  error: {exc}")

        finally:
            if mode == "persistent" and context:
                await context.close()
            elif mode == "cookies":
                if context:
                    await context.close()
                if browser:
                    await browser.close()

    # 汇总
    print(f"\n=== 汇总: 共拦截 {len(captured_xhrs)} 个 API XHR ===")
    vote_related = [x for x in captured_xhrs if any(w in x["url"].lower() for w in ("vote", "voted", "like", "activ"))]
    print(f"点赞/动态相关: {len(vote_related)}")
    for x in vote_related:
        print(f"  [{x['method']}] {x['status']} data={x['data_count']} {x['url']}")
        if x["data_count"] > 0:
            print(f"    keys: {x['body_keys']}")

    # 保存完整结果
    out = Path.home() / ".osint" / "zhihu_playwright_xhr_probe.json"
    out.write_text(json.dumps(captured_xhrs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整结果: {out}")


if __name__ == "__main__":
    asyncio.run(main())
