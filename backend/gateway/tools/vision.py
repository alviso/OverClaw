"""
Image Understanding Tool — Analyze images using GPT-4o vision.
Accepts file paths or URLs to images.
"""
import os
import base64
import logging
import mimetypes
from openai import AsyncOpenAI
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.vision")

UPLOAD_DIR = "/tmp/gateway_uploads"


class VisionTool(Tool):
    name = "analyze_image"
    description = (
        "Analyze an image using AI vision. Describe what's in it, read text (OCR), "
        "interpret diagrams, analyze screenshots, or answer questions about the image. "
        "Accepts a file path to an uploaded image or a public image URL."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_source": {
                "type": "string",
                "description": "Path to an uploaded image file (e.g., /tmp/gateway_uploads/photo.png) or a public image URL (https://...).",
            },
            "question": {
                "type": "string",
                "description": "What do you want to know about the image? (e.g., 'Describe this screenshot', 'What error is shown?', 'Read the text in this image')",
                "default": "Describe this image in detail.",
            },
        },
        "required": ["image_source"],
    }

    async def execute(self, params: dict) -> str:
        source = params.get("image_source", "")
        question = params.get("question", "Describe this image in detail.")

        if not source:
            return "Error: image_source is required"

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "Error: OPENAI_API_KEY not configured"

        try:
            # Build the image content part
            if source.startswith(("http://", "https://")):
                image_content = {"type": "image_url", "image_url": {"url": source}}
            else:
                # Local file
                if not os.path.exists(source):
                    return f"Error: File not found: {source}"

                mime_type = mimetypes.guess_type(source)[0] or "image/png"
                with open(source, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{data}"},
                }

            client = AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            image_content,
                        ],
                    }
                ],
                max_tokens=1500,
            )

            result = response.choices[0].message.content or "No analysis returned."
            logger.info(f"Vision analysis complete: {source[:60]} -> {len(result)} chars")
            return result

        except Exception as e:
            logger.exception(f"Vision error: {source}")
            return f"Image analysis failed: {str(e)}"


register_tool(VisionTool())
