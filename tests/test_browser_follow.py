import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from core.browser_follow import BrowserFollowers
from core.checker import TikTokChecker


def profile(name="sample", count=0):
    return '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">' + json.dumps({
        "__DEFAULT_SCOPE__": {"webapp.user-detail": {"statusCode": 0,
        "userInfo": {"user": {"uniqueId": name}, "stats": {"followerCount": count}}}}}) + '</script>'


def fake_browser(contents, status=200):
    page = SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=status)),
                           content=AsyncMock(side_effect=contents))
    context = SimpleNamespace(route=AsyncMock(), new_page=AsyncMock(return_value=page), close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
    return browser, context, page


def run_read(contents, status=200):
    async def run():
        checker = BrowserFollowers()
        checker._slots = asyncio.Semaphore(1)
        browser, context, page = fake_browser(contents, status)
        checker._get_browser = AsyncMock(return_value=browser)
        result = await checker._read("sample", 1, None)
        context.close.assert_awaited_once()
        return result, page, context
    return asyncio.run(run())


def test_js_hydration_followers_zero_succeeds_without_video():
    result, page, context = run_read(["<html>Loading</html>", profile()])
    assert result["status"] == "LIVE" and result["followers"] == 0
    assert result["videos"] == [] and result["total_sample_views"] == 0
    assert page.goto.await_count == 1
    assert page.goto.call_args.args[0] == "https://www.tiktok.com/@sample"


@pytest.mark.parametrize("body", [profile("other", 123), profile(count=None),
    '<script>{"slardarClient":"SlardarWAF"}</script>'])
def test_no_false_success_or_false_dead_for_missing_followers(body):
    # A persistent page must wait for hydration until the bounded deadline.
    async def run():
        checker = BrowserFollowers()
        checker._slots = asyncio.Semaphore(1)
        browser, context, page = fake_browser([])
        page.content = AsyncMock(return_value=body)
        checker._get_browser = AsyncMock(return_value=browser)
        result = await checker._read("sample", .05, None)
        assert result["status"] == "TIMEOUT" and "followers" not in result
        context.close.assert_awaited_once()
    asyncio.run(run())


@pytest.mark.parametrize("status", [403, 404, 429, 503])
def test_http_errors_preserved_not_concluded_dead(status):
    result, page, _ = run_read([], status)
    assert result["status"] == "HTTP_ERROR" and result["status_code"] == status
    page.content.assert_not_awaited()


def test_navigation_failure_closes_context():
    async def run():
        checker = BrowserFollowers()
        checker._slots = asyncio.Semaphore(1)
        browser, context, page = fake_browser([])
        page.goto.side_effect = RuntimeError("connection closed")
        checker._get_browser = AsyncMock(return_value=browser)
        assert (await checker._read("sample", 1, None))["status"] == "EXCEPTION"
        context.close.assert_awaited_once()
    asyncio.run(run())


def test_tab_limit_and_context_isolation_for_batch():
    async def run():
        checker = BrowserFollowers()
        checker._slots = asyncio.Semaphore(3)
        active = peak = 0
        contexts = []
        async def create(**options):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            page = SimpleNamespace(content=AsyncMock(return_value=profile()))
            async def goto(*args, **kwargs):
                await asyncio.sleep(.01)
                return SimpleNamespace(status=200)
            page.goto = goto
            async def close():
                nonlocal active
                active -= 1
            context = SimpleNamespace(route=AsyncMock(), new_page=AsyncMock(return_value=page), close=AsyncMock(side_effect=close))
            contexts.append(context)
            return context
        checker._get_browser = AsyncMock(return_value=SimpleNamespace(new_context=create))
        results = await asyncio.gather(*(checker._read("sample", 2, None) for _ in range(50)))
        assert all(r["status"] == "LIVE" for r in results)
        assert peak == 3 and active == 0 and len(contexts) == 50
    asyncio.run(run())


def test_wrapper_cleans_input_and_uses_only_browser():
    checker = TikTokChecker()
    checker._browser = Mock()
    checker._browser.check.return_value = {"status": "LIVE", "followers": 10}
    assert checker.check("https://www.tiktok.com/@sample?lang=en")["followers"] == 10
    checker._browser.check.assert_called_once_with("sample", timeout=12, proxy=None)
    assert checker.check(" ")["status"] == "INVALID_INPUT"
    checker.close()
    checker._browser.close.assert_called_once()


def test_sync_worker_bridge_shares_one_loop_and_stops():
    from concurrent.futures import ThreadPoolExecutor
    checker = BrowserFollowers()
    loops = set()
    async def read(username, timeout, proxy):
        loops.add(id(asyncio.get_running_loop()))
        await asyncio.sleep(.001)
        return {"status": "LIVE", "followers": 0}
    checker._read = read
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(checker.check, [f"user{i}" for i in range(20)]))
        assert len(loops) == 1 and all(r["status"] == "LIVE" for r in results)
    finally:
        checker.close()
        checker._thread.join(2)
    assert not checker._thread.is_alive()
