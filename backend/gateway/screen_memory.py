"""
Screen Memory — Stores screen capture context as searchable memories.
Uses the agent's own response when available (richer), falls back to
GPT-4o-mini vision analysis for captures without agent context.
Integrates Tesseract OCR for pixel-perfect text extraction.
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


def extract_text_ocr(file_path: str) -> str:
    """Extract text from an image using Tesseract OCR with preprocessing.
    Upscales the image 2x for better accuracy on screen-resolution text.
    Returns the raw extracted text, or empty string on failure."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        # Convert to grayscale
        img = img.convert("L")
        # Upscale 2x — Tesseract works best at ~300 DPI; screen captures are ~96 DPI
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")
        cleaned = text.strip()
        if cleaned:
            logger.info(f"OCR extracted {len(cleaned)} chars from {file_path}")
        return cleaned
    except Exception as e:
        logger.warning(f"Tesseract OCR failed for {file_path}: {e}")
        return ""


async def _analyze_image(db, file_path: str) -> str:
    """Use GPT-4o-mini vision to analyze a screen capture, augmented with OCR text."""
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

    # Run OCR in a thread to avoid blocking the event loop
    ocr_text = await asyncio.to_thread(extract_text_ocr, file_path)

    prompt = ANALYSIS_PROMPT
    if ocr_text:
        prompt += (
            "\n\n## OCR-Extracted Text (pixel-perfect, use as ground truth for names/emails/IDs):\n"
            f"```\n{ocr_text[:3000]}\n```"
        )

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
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
    """Store screen capture context as a searchable memory, distilled via Haiku."""
    try:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%B %d, %Y at %I:%M %p UTC")

        # Extract OCR text for accurate storage (run in thread to avoid blocking)
        ocr_text = await asyncio.to_thread(extract_text_ocr, file_path)

        # Prefer the agent's own response — it's usually richer and more accurate
        if agent_response and len(agent_response) > 50:
            analysis = agent_response
        else:
            # Fall back to vision analysis (already includes OCR internally)
            analysis = await _analyze_image(db, file_path)
            if not analysis:
                return

        # Build raw content for distillation
        raw_content = f"[Screen capture — {timestamp}]\n"
        if user_message:
            raw_content += f"User asked: {user_message[:300]}\n"
        raw_content += f"Screen content: {analysis}"
        if ocr_text:
            raw_content += f"\nOCR text: {ocr_text[:1500]}"

        # Distill through Haiku — only store extracted facts
        from gateway.fact_extraction import FactExtractor
        from gateway.memory import MemoryManager

        extractor = FactExtractor()
        mgr = MemoryManager(db)
        facts = await extractor.extract_facts(raw_content)

        if facts:
            for fact in facts:
                existing = await mgr.search_memory(fact["text"], agent_id="default", top_k=1, threshold=0.92)
                if existing:
                    continue
                await mgr.store_memory(
                    content=fact["text"],
                    session_id=session_id,
                    agent_id="default",
                    source="screen_capture",
                    metadata={
                        "type": fact["type"],
                        "extracted_from": "screen_capture",
                        "timestamp": now.isoformat(),
                    },
                )
            logger.info(f"Screen capture distilled into {len(facts)} facts")
        else:
            # Fallback: store a brief summary if Haiku found nothing extractable
            brief = f"Screen capture ({timestamp}): {analysis[:200]}"
            await mgr.store_memory(
                content=brief,
                session_id=session_id,
                agent_id="default",
                source="screen_capture",
                metadata={"type": "summary", "extracted_from": "screen_capture", "timestamp": now.isoformat()},
            )
            logger.info("Screen capture stored as brief summary")

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
