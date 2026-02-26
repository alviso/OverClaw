"""
Browser Control Tool — Navigate, extract content from web pages.
Uses Scrapling for fast HTTP fetching with stealth headers and
StealthyFetcher as fallback for Cloudflare-protected sites.
"""
import logging
import asyncio
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.browser")


class BrowseTool(Tool):
    name = "browse_webpage"
    description = (
        "Navigate to a URL and extract the page content as text. "
        "Uses stealth headers to bypass basic bot detection. "
        "For Cloudflare-protected sites, automatically escalates to a stealth browser. "
        "Returns the visible text content of the page."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to navigate to (must start with http:// or https://)",
            },
        },
        "required": ["url"],
    }

    async def execute(self, params: dict) -> str:
        url = params.get("url", "")
        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        # Try fast fetcher first, escalate to stealth if blocked
        result = await self._fetch_fast(url)
        if result.get("blocked"):
            logger.info(f"Fast fetch blocked for {url}, escalating to stealth browser")
            result = await self._fetch_stealth(url)

        if result.get("error"):
            return f"Error browsing {url}: {result['error']}"

        return result["content"]

    async def _fetch_fast(self, url: str) -> dict:
        """Fast HTTP fetch with stealth headers — works for most sites."""
        try:
            from scrapling.fetchers import Fetcher

            page = await asyncio.to_thread(
                Fetcher.get,
                url,
                stealthy_headers=True,
                follow_redirects=True,
                timeout=20,
            )

            status = page.status
            title = page.css('title::text').get() or ""

            # Detect Cloudflare / bot blocks
            if status in (403, 503) or "just a moment" in title.lower():
                return {"blocked": True}

            text = self._extract_text(page, url, title)

            # If we got almost no text, the page might need JS rendering
            if len(text.strip()) < 100 and status == 200:
                return {"blocked": True}

            return {"content": text, "blocked": False}

        except Exception as e:
            logger.warning(f"Fast fetch error for {url}: {e}")
            return {"error": str(e)[:200], "blocked": False}

    async def _fetch_stealth(self, url: str) -> dict:
        """Stealth browser fetch — handles Cloudflare and JS-heavy sites."""
        try:
            from scrapling.fetchers import StealthyFetcher

            page = await asyncio.to_thread(
                StealthyFetcher.fetch,
                url,
                headless=True,
                network_idle=True,
                solve_cloudflare=True,
            )

            title = page.css('title::text').get() or ""

            # Still blocked after stealth?
            if "just a moment" in title.lower():
                return {"error": f"Site {url} has aggressive bot protection that could not be bypassed"}

            text = self._extract_text(page, url, title)
            return {"content": text, "blocked": False}

        except Exception as e:
            logger.warning(f"Stealth fetch error for {url}: {e}")
            return {"error": str(e)[:200], "blocked": False}

    def _extract_text(self, page, url: str, title: str) -> str:
        """Extract readable text from a Scrapling response/selector."""
        # Try main content areas first for cleaner text
        for selector in ['article', 'main', '[role="main"]', '.content', '#content', '#main-content']:
            try:
                els = page.css(selector)
                if els:
                    text = els[0].get_all_text().strip()
                    if len(text) > 200:
                        return f"Page: {title}\nURL: {url}\n\n{text[:10000]}"
            except Exception:
                continue

        # Fall back to full page text
        try:
            text = page.get_all_text().strip()
        except Exception:
            text = "(could not extract text)"

        return f"Page: {title}\nURL: {url}\n\n{text[:10000]}"


register_tool(BrowseTool())
