"""
Browser Control Tool — Navigate, extract content, and screenshot web pages.
Uses Playwright for headless Chromium automation.
"""
import logging
import base64
import asyncio
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.browser")

# Shared browser instance
_browser = None
_playwright = None


async def _get_browser():
    global _browser, _playwright
    if _browser and _browser.is_connected():
        return _browser
    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    logger.info("Browser launched")
    return _browser


class BrowseTool(Tool):
    name = "browse_webpage"
    description = (
        "Navigate to a URL and extract the page content as text. "
        "Use this to read articles, documentation, or any web page. "
        "Returns the visible text content of the page."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to navigate to (must start with http:// or https://)",
            },
            "extract": {
                "type": "string",
                "enum": ["text", "html", "screenshot"],
                "description": "What to extract: 'text' (default, visible text), 'html' (raw HTML), or 'screenshot' (base64 image description).",
                "default": "text",
            },
            "wait_seconds": {
                "type": "integer",
                "description": "Seconds to wait for page to load (default 3, max 15).",
                "default": 3,
            },
        },
        "required": ["url"],
    }

    async def execute(self, params: dict) -> str:
        url = params.get("url", "")
        extract = params.get("extract", "text")
        wait = min(params.get("wait_seconds", 3), 15)

        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        try:
            browser = await _get_browser()
            page = await browser.new_page()
            page.set_default_timeout(20000)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if wait > 0:
                    await asyncio.sleep(wait)

                if extract == "html":
                    content = await page.content()
                    return f"HTML content of {url} ({len(content)} chars):\n\n{content[:8000]}"

                elif extract == "screenshot":
                    screenshot_bytes = await page.screenshot(type="jpeg", quality=40)
                    b64 = base64.b64encode(screenshot_bytes).decode()
                    title = await page.title()
                    return f"Screenshot taken of '{title}' ({url}). Base64 JPEG ({len(b64)} chars). Page title: {title}"

                else:
                    title = await page.title()
                    text = await page.evaluate("""
                        () => {
                            const sel = document.querySelectorAll('article, main, [role="main"], .content, #content, body');
                            const el = sel[0] || document.body;
                            return el.innerText;
                        }
                    """)
                    text = text.strip()[:10000]
                    return f"Page: {title}\nURL: {url}\n\n{text}"

            finally:
                await page.close()

        except Exception as e:
            logger.exception(f"Browser error: {url}")
            return f"Browser error navigating to {url}: {str(e)}"


register_tool(BrowseTool())
