"""
Gateway configuration schema and loader — Phase 5
Now supports multi-agent with routing.
"""
from pydantic import BaseModel, Field
from typing import Optional


class AgentConfig(BaseModel):
    model: str = "openai/gpt-4o"
    system_prompt: str = (
        "You are a helpful corporate assistant with full access to web browsing, "
        "file management, system tools, and more.\n\n"
        "## Browser Use\n"
        "You have an interactive browser (browser_use tool) that lets you navigate websites, "
        "click buttons, fill forms, and see what's on screen. Use it when asked to:\n"
        "- Check websites, dashboards, or email\n"
        "- Fill out forms or interact with web apps\n"
        "- Log into services (navigate to login page, type credentials, click sign in)\n"
        "- Monitor or inspect any web page visually\n\n"
        "Workflow: navigate to URL -> screenshot to see the page -> click/type to interact -> screenshot again to verify.\n"
        "Always take a screenshot after navigating or clicking so you know what the page looks like.\n\n"
        "## Other Tools\n"
        "- browse_webpage: Quick one-shot page scraping (text extraction, no interaction)\n"
        "- web_search: Search the internet for information\n"
        "- File tools: read_file, write_file, list_files for local file operations\n"
        "- execute_command: Run system commands\n"
        "- analyze_image: Analyze uploaded images with AI vision\n"
        "- parse_document: Extract text from PDFs, Word docs, etc.\n"
        "- memory_search: Search your long-term memory for past conversations\n"
    )
    max_context_messages: int = 50
    tools_allowed: list[str] = Field(default_factory=lambda: [
        "web_search", "read_file", "write_file", "list_files", "execute_command",
        "memory_search", "browse_webpage", "system_info", "http_request",
        "analyze_image", "transcribe_audio", "parse_document", "monitor_url",
        "browser_use", "delegate", "list_agents",
    ])


class AgentDefinition(BaseModel):
    """A named agent with its own personality, model, and tool policy."""
    id: str = "default"
    name: str = "Default Agent"
    description: str = "General-purpose assistant"
    model: str = "openai/gpt-4o"
    system_prompt: str = "You are a helpful corporate assistant."
    max_context_messages: int = 50
    tools_allowed: list[str] = Field(default_factory=lambda: [
        "web_search", "read_file", "write_file", "list_files", "execute_command",
        "memory_search", "browse_webpage", "system_info", "http_request",
        "analyze_image", "transcribe_audio", "parse_document", "monitor_url",
        "browser_use", "delegate", "list_agents",
    ])
    enabled: bool = True


class RouteRule(BaseModel):
    """Maps a pattern to an agent_id."""
    pattern: str  # e.g. "slack:C012345:*" or "slack:*:*" or "webchat:*"
    agent_id: str


class GatewayConfig(BaseModel):
    port: int = 8001
    bind: str = "0.0.0.0"
    auth_mode: str = "token"


class ChannelSlackConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""


class ChannelsConfig(BaseModel):
    slack: ChannelSlackConfig = ChannelSlackConfig()


class ToolConfig(BaseModel):
    enabled: bool = True


class ToolsConfig(BaseModel):
    web_search: ToolConfig = ToolConfig(enabled=True)
    execute_command: ToolConfig = ToolConfig(enabled=False)
    read_file: ToolConfig = ToolConfig(enabled=True)


class AssistantConfig(BaseModel):
    """Root configuration schema."""
    agent: AgentConfig = AgentConfig()
    gateway: GatewayConfig = GatewayConfig()
    channels: ChannelsConfig = ChannelsConfig()
    tools: ToolsConfig = ToolsConfig()
    routing: list[RouteRule] = Field(default_factory=list)


DEFAULT_CONFIG = AssistantConfig()


def validate_config(raw: dict) -> AssistantConfig:
    return AssistantConfig(**raw)


def config_to_display(config: AssistantConfig) -> dict:
    d = config.model_dump()
    if d.get("channels", {}).get("slack", {}).get("bot_token"):
        d["channels"]["slack"]["bot_token"] = "****" + d["channels"]["slack"]["bot_token"][-4:]
    if d.get("channels", {}).get("slack", {}).get("app_token"):
        d["channels"]["slack"]["app_token"] = "****" + d["channels"]["slack"]["app_token"][-4:]
    return d
