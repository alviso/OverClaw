"""
Monitor URL Tool — Screenshot a URL and analyze it with vision, with state diffing.
Combines browse_webpage screenshot + analyze_image in one step.
Tracks previous state in MongoDB to detect changes.
"""
import os
import json
import asyncio
import hashlib
import logging
import base64
from datetime import datetime, timezone

from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.monitor")

_db = None


def set_monitor_db(db):
    global _db
    _db = db


class MonitorUrlTool(Tool):
    name = "monitor_url"
    description = (
        "Take a screenshot of a URL and analyze it with AI vision to detect changes. "
        "Compares the current state with the previous check and reports differences. "
        "Use this for monitoring dashboards, pages, or any visual interface for changes. "
        "Returns analysis of current state and whether anything changed since last check."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to monitor (must start with http:// or https://).",
            },
            "focus": {
                "type": "string",
                "description": "What to look for specifically (e.g., 'new message notification badges', 'error alerts', 'status changes').",
                "default": "any visible changes or notifications",
            },
            "monitor_id": {
                "type": "string",
                "description": "Unique identifier for this monitor (used to track state between checks). Defaults to URL hash.",
            },
        },
        "required": ["url"],
    }

    async def execute(self, params: dict) -> str:
        url = params.get("url", "")
        focus = params.get("focus", "any visible changes or notifications")
        monitor_id = params.get("monitor_id") or hashlib.md5(url.encode()).hexdigest()[:12]

        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        try:
            # Step 1: Take screenshot
            screenshot_b64, page_title = await self._take_screenshot(url)
            if not screenshot_b64:
                return f"Error: Could not take screenshot of {url}"

            # Step 2: Get previous state from DB
            prev_state = await self._get_previous_state(monitor_id)

            # Step 3: Analyze with vision
            analysis = await self._analyze_screenshot(screenshot_b64, url, focus, prev_state)

            # Step 4: Store current state
            current_hash = hashlib.md5(screenshot_b64.encode()).hexdigest()
            await self._store_state(monitor_id, url, current_hash, analysis, page_title)

            # Step 5: Build response with change detection
            changed = prev_state is not None and prev_state.get("screenshot_hash") != current_hash
            change_status = "CHANGE DETECTED" if changed else ("No change detected" if prev_state else "First check (baseline established)")

            result = f"## Monitor: {page_title or url}\n"
            result += f"**Status:** {change_status}\n"
            result += f"**URL:** {url}\n"
            result += f"**Focus:** {focus}\n"
            result += f"**Check time:** {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n\n"
            result += f"**Analysis:**\n{analysis}\n"

            if prev_state:
                result += f"\n**Previous check:** {prev_state.get('checked_at', 'unknown')}"
                if prev_state.get("analysis"):
                    result += f"\n**Previous analysis:** {prev_state['analysis'][:300]}..."

            logger.info(f"Monitor {monitor_id}: {url} -> changed={changed}")
            return result

        except Exception as e:
            logger.exception(f"Monitor error: {url}")
            return f"Monitor error for {url}: {str(e)}"

    async def _take_screenshot(self, url: str) -> tuple:
        """Take a screenshot using Playwright."""
        try:
            from gateway.tools.browser import _get_browser
            browser = await _get_browser()
            page = await browser.new_page()
            page.set_default_timeout(20000)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                title = await page.title()
                screenshot = await page.screenshot(type="jpeg", quality=50)
                b64 = base64.b64encode(screenshot).decode()
                return b64, title
            finally:
                await page.close()
        except Exception as e:
            logger.warning(f"Screenshot failed for {url}: {e}")
            return None, None

    async def _analyze_screenshot(self, b64: str, url: str, focus: str, prev_state: dict = None) -> str:
        """Analyze screenshot with GPT-4o vision."""
        from openai import AsyncOpenAI

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "Vision analysis unavailable (no API key)"

        prompt = f"You are monitoring the webpage at {url}.\n"
        prompt += f"Focus specifically on: {focus}\n\n"
        if prev_state and prev_state.get("analysis"):
            prompt += f"Previous analysis was: {prev_state['analysis'][:500]}\n"
            prompt += "Compare with what you see now and report any CHANGES. "
            prompt += "If something new appeared or changed, start your response with 'CHANGE DETECTED:'. "
            prompt += "If nothing changed, start with 'No changes:'\n"
        else:
            prompt += "This is the first check. Describe what you see, especially anything related to the focus area. "
            prompt += "This will serve as the baseline for future comparisons.\n"

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            max_tokens=800,
        )
        return response.choices[0].message.content or "No analysis"

    async def _get_previous_state(self, monitor_id: str) -> dict | None:
        if _db is None:
            return None
        return await _db.monitor_states.find_one({"monitor_id": monitor_id}, {"_id": 0})

    async def _store_state(self, monitor_id: str, url: str, screenshot_hash: str, analysis: str, title: str):
        if _db is None:
            return
        await _db.monitor_states.replace_one(
            {"monitor_id": monitor_id},
            {
                "monitor_id": monitor_id,
                "url": url,
                "title": title or "",
                "screenshot_hash": screenshot_hash,
                "analysis": analysis[:1000],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
            upsert=True,
        )


register_tool(MonitorUrlTool())
