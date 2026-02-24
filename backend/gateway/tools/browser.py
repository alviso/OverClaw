"""
Browser Control Tool — Navigate, extract content, and screenshot web pages.
Uses Scrapling's StealthyFetcher for anti-bot bypass (Cloudflare, etc.)
and falls back to Fetcher for speed on simple sites.
"""
import logging
import asyncio
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.browser")


class BrowseTool(Tool):
    name = "browse_webpage"
    description = (
        "Navigate to a URL and extract the page content as text. "
        "Uses stealth mode to bypass Cloudflare and other anti-bot systems. "
        "Use this to read articles, documentation, financial data, or any web page. "
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
                "enum": ["text", "html"],
                "description": "What to extract: 'text' (default, visible text) or 'html' (raw HTML).",
                "default": "text",
            },
            "stealth": {
                "type": "boolean",
                "description": "Use stealth browser mode (slower but bypasses anti-bot). Default true.",
                "default": True,
            },
        },
        "required": ["url"],
    }

    async def execute(self, params: dict) -> str:
        url = params.get("url", "")
        extract = params.get("extract", "text")
        use_stealth = params.get("stealth", True)

        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        # Try stealth first, fall back to simple fetch
        if use_stealth:
            result = await self._fetch_stealth(url, extract)
        else:
            result = await self._fetch_simple(url, extract)

        # If stealth fails, try simple (or vice versa)
        if result.startswith("Error:") and use_stealth:
            logger.info(f"Stealth fetch failed for {url}, trying simple fetch")
            result = await self._fetch_simple(url, extract)
        elif result.startswith("Error:") and not use_stealth:
            logger.info(f"Simple fetch failed for {url}, trying stealth fetch")
            result = await self._fetch_stealth(url, extract)

        return result

    async def _fetch_stealth(self, url: str, extract: str) -> str:
        """Fetch with Scrapling StealthyFetcher — bypasses Cloudflare etc."""
        try:
            from scrapling.fetchers import StealthyFetcher

            page = await asyncio.to_thread(
                StealthyFetcher.fetch,
                url,
                headless=True,
                network_idle=True,
            )

            if extract == "html":
                html = page.body.html if hasattr(page, 'body') else str(page)
                return f"HTML content of {url} ({len(html)} chars):\n\n{html[:8000]}"

            # Extract text — try main content area first, fall back to body
            title = ""
            if hasattr(page, 'css'):
                title_els = page.css('title::text')
                if title_els:
                    title = title_els.get() or ""

            # Try to get main content text
            text = ""
            for selector in ['article', 'main', '[role="main"]', '.content', '#content']:
                try:
                    els = page.css(selector)
                    if els:
                        text = els[0].text.strip() if hasattr(els[0], 'text') else ""
                        if len(text) > 100:
                            break
                except Exception:
                    continue

            if not text or len(text) < 100:
                # Fall back to body text
                try:
                    text = page.body.text.strip() if hasattr(page, 'body') else page.text.strip()
                except Exception:
                    text = str(page)[:10000]

            text = text[:10000]
            return f"Page: {title}\nURL: {url}\n\n{text}"

        except Exception as e:
            logger.warning(f"Stealth fetch error for {url}: {e}")
            return f"Error: Stealth fetch failed for {url}: {str(e)[:200]}"

    async def _fetch_simple(self, url: str, extract: str) -> str:
        """Fetch with Scrapling Fetcher — fast, no browser overhead."""
        try:
            from scrapling.fetchers import Fetcher

            page = await asyncio.to_thread(
                Fetcher.get,
                url,
                stealthy_headers=True,
                follow_redirects=True,
            )

            if extract == "html":
                html = page.body.html if hasattr(page, 'body') else str(page)
                return f"HTML content of {url} ({len(html)} chars):\n\n{html[:8000]}"

            title = ""
            if hasattr(page, 'css'):
                title_els = page.css('title::text')
                if title_els:
                    title = title_els.get() or ""

            text = ""
            for selector in ['article', 'main', '[role="main"]', '.content', '#content']:
                try:
                    els = page.css(selector)
                    if els:
                        text = els[0].text.strip() if hasattr(els[0], 'text') else ""
                        if len(text) > 100:
                            break
                except Exception:
                    continue

            if not text or len(text) < 100:
                try:
                    text = page.body.text.strip() if hasattr(page, 'body') else page.text.strip()
                except Exception:
                    text = str(page)[:10000]

            text = text[:10000]
            return f"Page: {title}\nURL: {url}\n\n{text}"

        except Exception as e:
            logger.warning(f"Simple fetch error for {url}: {e}")
            return f"Error: Simple fetch failed for {url}: {str(e)[:200]}"


register_tool(BrowseTool())
