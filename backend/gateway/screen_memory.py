"""
Screen Memory — Stores screen capture context as searchable memories.
Uses the agent's own response when available (richer), falls back to
GPT-4o-mini vision analysis for captures without agent context.
"""
import os
import logging
import base64
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger("gateway.screen_memory")

ANALYSIS_PROMPT = """Extract ALL key information from this screen capture for future reference.

You MUST include:
1. Application name and specific page/view/tab shown
2. ALL visible text labels, headings, column headers, menu items, and navigation breadcrumbs
3. ALL specific data: names, numbers, dates, statuses, IDs, amounts, percentages
4. Report names, document titles, project names, task names — anything with a specific name
5. What the user appears to be working on and any notable details

Be thorough — extract every piece of identifiable information. This will be stored as searchable context.
Write in plain text, not bullet points. Include as many specific terms and names as possible."""


async def _analyze_image(db, file_path: str) -> str:
    """Use GPT-4o-mini vision to analyze a screen capture."""
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "jpeg"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        secrets = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0})
        if secrets:
            api_key = secrets.get("openai_api_key", "")

    if not api_key:
        return ""

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": ANALYSIS_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            ],
        }],
        max_tokens=600,
    )
    return response.choices[0].message.content.strip()


async def analyze_and_store_screen(
    db, file_path: str, session_id: str,
    user_message: str = "", agent_response: str = "",
):
    """Store screen capture context as a searchable memory."""
    try:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%B %d, %Y at %I:%M %p UTC")

        # Prefer the agent's own response — it's usually richer and more accurate
        if agent_response and len(agent_response) > 50:
            analysis = agent_response
        else:
            # Fall back to vision analysis
            analysis = await _analyze_image(db, file_path)
            if not analysis:
                return

        content = f"[Screen capture — {timestamp}]\n"
        if user_message:
            content += f"User asked: {user_message[:300]}\n"
        content += f"Screen content: {analysis}"

        from gateway.memory import MemoryManager
        mgr = MemoryManager(db)
        await mgr.store_memory(
            content=content,
            session_id=session_id,
            agent_id="default",
            source="screen_capture",
            metadata={
                "type": "screen_capture",
                "timestamp": now.isoformat(),
                "file_path": file_path,
            },
        )
        logger.info(f"Screen memory stored: {analysis[:80]}...")

    except Exception as e:
        logger.warning(f"Screen analysis failed: {e}")


def schedule_screen_analysis(
    db, file_path: str, session_id: str,
    user_message: str = "", agent_response: str = "",
):
    """Fire-and-forget background task for screen analysis."""
    asyncio.create_task(
        analyze_and_store_screen(db, file_path, session_id, user_message, agent_response)
    )
