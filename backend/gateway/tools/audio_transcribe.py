"""
Audio Transcription Tool — Transcribe audio files using OpenAI Whisper.
"""
import os
import logging
from openai import AsyncOpenAI
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.audio_transcribe")

SUPPORTED_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB (Whisper API limit)


class AudioTranscribeTool(Tool):
    name = "transcribe_audio"
    description = (
        "Transcribe an audio file to text using OpenAI Whisper. "
        "Supports mp3, mp4, wav, webm, ogg, flac, and other common audio formats. "
        "Use this to transcribe meeting recordings, voice notes, or any audio. "
        "Provide the path to an uploaded audio file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the uploaded audio file (e.g., /tmp/gateway_uploads/recording.mp3).",
            },
            "language": {
                "type": "string",
                "description": "Optional language hint (ISO 639-1 code, e.g., 'en', 'es', 'fr'). Improves accuracy.",
            },
        },
        "required": ["file_path"],
    }

    async def execute(self, params: dict) -> str:
        file_path = params.get("file_path", "")
        language = params.get("language")

        if not file_path:
            return "Error: file_path is required"

        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_FORMATS:
            return f"Error: Unsupported audio format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"

        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            return f"Error: File too large ({file_size / 1e6:.1f} MB). Maximum is 25 MB."

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "Error: OPENAI_API_KEY not configured"

        try:
            client = AsyncOpenAI(api_key=api_key)

            with open(file_path, "rb") as audio_file:
                kwargs = {"model": "whisper-1", "file": audio_file}
                if language:
                    kwargs["language"] = language

                transcript = await client.audio.transcriptions.create(**kwargs)

            text = transcript.text
            logger.info(f"Transcription complete: {file_path} -> {len(text)} chars")
            return f"## Transcription\n\n**File:** {os.path.basename(file_path)}\n**Length:** {len(text)} characters\n\n{text}"

        except Exception as e:
            logger.exception(f"Transcription error: {file_path}")
            return f"Transcription failed: {str(e)}"


register_tool(AudioTranscribeTool())
