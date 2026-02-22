"""
Agent Runtime — Phase 2
LLM provider abstraction with native tool/function calling.
Uses OpenAI and Anthropic SDKs directly for tool-calling support.
Inspired by OpenClaw's pi-embedded-runner.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from gateway.config_schema import AssistantConfig
from gateway.tools import get_tool, get_tools_for_openai, get_tools_for_anthropic

logger = logging.getLogger("gateway.agent")

MAX_TOOL_ITERATIONS = 25  # Browser interactions can chain many steps


async def _safe_extract_memories(db, session_id, agent_id, user_text, response_text):
    """Fire-and-forget wrapper for memory extraction."""
    try:
        from gateway.memory import extract_and_store_memories
        await extract_and_store_memories(db, session_id, agent_id, user_text, response_text)
    except Exception as e:
        logger.warning(f"Memory extraction failed: {e}")


async def _safe_extract_profile(db, user_text):
    """Fire-and-forget wrapper for user profile extraction."""
    try:
        from gateway.user_profile import extract_profile_facts
        await extract_profile_facts(db, user_text)
    except Exception as e:
        logger.debug(f"Profile extraction failed: {e}")


async def _safe_extract_relationships(db, user_text):
    """Fire-and-forget wrapper for relationship extraction."""
    try:
        from gateway.relationship_memory import extract_relationships
        await extract_relationships(db, user_text)
    except Exception as e:
        logger.debug(f"Relationship extraction failed: {e}")


# ── Provider mapping ─────────────────────────────────────────────────────
PROVIDER_MAP = {
    "openai/gpt-4o": ("openai", "gpt-4o", "OPENAI_API_KEY"),
    "openai/gpt-4.1-mini": ("openai", "gpt-4.1-mini", "OPENAI_API_KEY"),
    "openai/gpt-4.1": ("openai", "gpt-4.1", "OPENAI_API_KEY"),
    "anthropic/claude-sonnet": ("anthropic", "claude-sonnet-4-5-20250929", "ANTHROPIC_API_KEY"),
    "anthropic/claude-haiku": ("anthropic", "claude-haiku-4-5-20251001", "ANTHROPIC_API_KEY"),
    "anthropic/claude-4-sonnet": ("anthropic", "claude-4-sonnet-20250514", "ANTHROPIC_API_KEY"),
}

DEFAULT_MODEL = "openai/gpt-4o"


def resolve_model(model_str: str) -> tuple:
    if model_str in PROVIDER_MAP:
        return PROVIDER_MAP[model_str]
    if "/" in model_str:
        parts = model_str.split("/", 1)
        provider = parts[0].lower()
        model_id = parts[1]
        if provider == "openai":
            return ("openai", model_id, "OPENAI_API_KEY")
        elif provider == "anthropic":
            return ("anthropic", model_id, "ANTHROPIC_API_KEY")
    logger.warning(f"Unknown model '{model_str}', falling back to {DEFAULT_MODEL}")
    return PROVIDER_MAP[DEFAULT_MODEL]


def get_api_key(env_key: str) -> str:
    key = os.environ.get(env_key, "")
    if not key:
        raise ValueError(f"API key not found: {env_key}. Set it in .env")
    return key


# ── Session Manager ──────────────────────────────────────────────────────
class SessionManager:
    def __init__(self, db):
        self.db = db

    async def get_or_create_session(self, session_id: str, agent_id: str = "default") -> dict:
        session = await self.db.sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not session:
            session = {
                "session_id": session_id,
                "agent_id": agent_id,
                "channel": "webchat",
                "status": "idle",
                "messages": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_active": datetime.now(timezone.utc).isoformat(),
            }
            await self.db.sessions.insert_one({**session})
        return session

    async def get_history(self, session_id: str, limit: int = 50) -> list:
        messages = await self.db.chat_messages.find(
            {"session_id": session_id}, {"_id": 0}
        ).sort("timestamp", 1).to_list(limit)
        return messages

    async def add_message(self, session_id: str, role: str, content: str, tool_calls: list = None):
        msg = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls
        await self.db.chat_messages.insert_one(msg)
        await self.db.sessions.update_one(
            {"session_id": session_id},
            {
                "$set": {"last_active": datetime.now(timezone.utc).isoformat(), "status": "idle"},
                "$inc": {"messages": 1},
            }
        )

    async def set_status(self, session_id: str, status: str):
        await self.db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"status": status}}
        )

    async def clear_session(self, session_id: str):
        await self.db.chat_messages.delete_many({"session_id": session_id})
        await self.db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"messages": 0, "status": "idle"}}
        )


# ── Tool Executor ────────────────────────────────────────────────────────
async def execute_tool_call(name: str, arguments: dict) -> str:
    tool = get_tool(name)
    if not tool:
        return f"Error: Unknown tool '{name}'"
    try:
        result = await tool.execute(arguments)
        return result
    except Exception as e:
        logger.exception(f"Tool execution failed: {name}")
        return f"Error executing {name}: {str(e)}"


# ── OpenAI Agent Loop ────────────────────────────────────────────────────
async def run_openai_turn(
    api_key: str,
    model_id: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    on_tool_call: Optional[callable] = None,
) -> tuple[str, list[dict]]:
    """Run an OpenAI turn with tool-calling loop. Returns (response_text, tool_calls_made)."""
    client = AsyncOpenAI(api_key=api_key)
    tool_calls_made = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        kwargs = {
            "model": model_id,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            # Execute tool calls
            messages.append(choice.message.model_dump())

            for tc in choice.message.tool_calls:
                func_name = tc.function.name
                try:
                    func_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                logger.info(f"Tool call: {func_name}({json.dumps(func_args)[:100]})")

                if on_tool_call:
                    await on_tool_call(func_name, func_args, "executing")

                result = await execute_tool_call(func_name, func_args)
                tool_calls_made.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result[:500],
                })

                if on_tool_call:
                    await on_tool_call(func_name, func_args, "done")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            # Text response — done
            text = choice.message.content or ""
            return text, tool_calls_made

    return "I've reached the maximum number of tool calls. Please try a simpler request.", tool_calls_made


# ── Anthropic Agent Loop ─────────────────────────────────────────────────
async def run_anthropic_turn(
    api_key: str,
    model_id: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    on_tool_call: Optional[callable] = None,
) -> tuple[str, list[dict]]:
    """Run an Anthropic turn with tool-calling loop."""
    client = AsyncAnthropic(api_key=api_key)
    tool_calls_made = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        kwargs = {
            "model": model_id,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.messages.create(**kwargs)

        # Check if there are tool calls
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if tool_use_blocks and response.stop_reason == "tool_use":
            # Build assistant message with all content blocks
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call
            tool_results = []
            for block in tool_use_blocks:
                func_name = block.name
                func_args = block.input or {}

                logger.info(f"Tool call: {func_name}({json.dumps(func_args)[:100]})")

                if on_tool_call:
                    await on_tool_call(func_name, func_args, "executing")

                result = await execute_tool_call(func_name, func_args)
                tool_calls_made.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result[:500],
                })

                if on_tool_call:
                    await on_tool_call(func_name, func_args, "done")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            # Text response — done
            text = " ".join(b.text for b in text_blocks) if text_blocks else ""
            return text, tool_calls_made

    return "I've reached the maximum number of tool calls.", tool_calls_made


# ── Agent Runner ─────────────────────────────────────────────────────────
class AgentRunner:
    def __init__(self, db, config: AssistantConfig):
        self.session_mgr = SessionManager(db)
        self.config = config
        self.db = db

    async def get_agent_config(self, agent_id: str) -> dict:
        """Get agent definition from DB, or fall back to default config."""
        if agent_id and agent_id != "default":
            agent_doc = await self.db.agents.find_one({"id": agent_id}, {"_id": 0})
            if agent_doc:
                return agent_doc
        # Fall back to global config
        return {
            "id": "default",
            "name": "Default Agent",
            "model": self.config.agent.model,
            "system_prompt": self.config.agent.system_prompt,
            "max_context_messages": self.config.agent.max_context_messages,
            "tools_allowed": self.config.agent.tools_allowed,
        }

    async def run_turn(
        self,
        session_id: str,
        user_text: str,
        on_tool_call: Optional[callable] = None,
        agent_id: str = None,
    ) -> tuple[str, list[dict]]:
        """
        Run an agent turn with tool calling.
        Resolves agent_id via routing if not provided.
        Returns (response_text, tool_calls_list).
        """
        from gateway.routing import resolve_agent_id
        from gateway.skills import SkillManager
        from gateway.memory import build_memory_context, extract_and_store_memories
        from gateway.tools.browser_use import set_browser_session_id

        # Set browser session context for interactive browsing
        set_browser_session_id(session_id)

        # Resolve agent
        if not agent_id:
            agent_id = resolve_agent_id(session_id, self.config.routing)
        agent_def = await self.get_agent_config(agent_id)

        model_str = agent_def.get("model", self.config.agent.model)
        base_prompt = agent_def.get("system_prompt", self.config.agent.system_prompt)
        max_ctx = agent_def.get("max_context_messages", self.config.agent.max_context_messages)
        tools_allowed = agent_def.get("tools_allowed")

        # Diagnostic logging — helps trace Slack vs webchat quality issues
        has_delegate = "delegate" in (tools_allowed or [])
        has_web_search = "web_search" in (tools_allowed or [])
        prompt_preview = base_prompt[:80].replace("\n", " ") if base_prompt else "(none)"
        logger.info(
            f"Agent resolved: session={session_id} agent={agent_id} model={model_str} "
            f"tools={len(tools_allowed or [])} delegate={has_delegate} web_search={has_web_search} "
            f"prompt={prompt_preview}..."
        )

        # Inject skills into system prompt
        skill_mgr = SkillManager(self.db)
        skills_prompt = await skill_mgr.build_skills_prompt(agent_id)
        system_prompt = base_prompt + (skills_prompt or "")

        # Inject current time so the agent can reason about time
        from datetime import datetime, timezone as tz
        import zoneinfo
        # Try to use user's timezone from profile
        user_tz_name = None
        try:
            profile = await self.db.user_profiles.find_one({"profile_id": "default"}, {"facts.timezone": 1})
            tz_val = (profile or {}).get("facts", {}).get("timezone", {})
            if isinstance(tz_val, dict):
                tz_val = tz_val.get("value", "")
            if tz_val:
                # Map common names to IANA
                tz_map = {
                    "pacific": "US/Pacific", "pacific time": "US/Pacific", "pst": "US/Pacific", "pdt": "US/Pacific",
                    "eastern": "US/Eastern", "eastern time": "US/Eastern", "est": "US/Eastern", "edt": "US/Eastern",
                    "central": "US/Central", "central time": "US/Central", "cst": "US/Central", "cdt": "US/Central",
                    "mountain": "US/Mountain", "mountain time": "US/Mountain", "mst": "US/Mountain",
                    "cet": "Europe/Berlin", "cest": "Europe/Berlin",
                }
                user_tz_name = tz_map.get(tz_val.lower(), tz_val)
        except Exception:
            pass

        if user_tz_name:
            try:
                user_tz = zoneinfo.ZoneInfo(user_tz_name)
                now_local = datetime.now(user_tz)
                system_prompt += f"\n\n## Current Time\nIt is currently {now_local.strftime('%A, %B %d, %Y at %I:%M %p')} {user_tz_name}."
            except Exception:
                now_utc = datetime.now(tz.utc)
                system_prompt += f"\n\n## Current Time\nIt is currently {now_utc.strftime('%A, %B %d, %Y at %I:%M %p')} UTC."
        else:
            now_utc = datetime.now(tz.utc)
            system_prompt += f"\n\n## Current Time\nIt is currently {now_utc.strftime('%A, %B %d, %Y at %I:%M %p')} UTC."

        # Inject relevant memories into system prompt
        memory_context = await build_memory_context(self.db, user_text, agent_id, max_results=3)
        if memory_context:
            system_prompt += memory_context

        # Inject user profile into system prompt
        from gateway.user_profile import build_profile_context
        profile_context = await build_profile_context(self.db)
        if profile_context:
            system_prompt += profile_context

        # Inject discovered relationships into system prompt
        from gateway.relationship_memory import build_relationships_context
        relationships_context = await build_relationships_context(self.db)
        if relationships_context:
            system_prompt += relationships_context

        provider, model_id, env_key = resolve_model(model_str)
        api_key = get_api_key(env_key)

        await self.session_mgr.get_or_create_session(session_id, agent_id=agent_id)
        # Ensure agent_id is always up-to-date on the session
        await self.db.sessions.update_one(
            {"session_id": session_id}, {"$set": {"agent_id": agent_id}}
        )
        await self.session_mgr.set_status(session_id, "active")
        await self.session_mgr.add_message(session_id, "user", user_text)

        history = await self.session_mgr.get_history(session_id, limit=max_ctx)

        # Build messages for the LLM — include tool call context
        llm_messages = []
        for msg in history[:-1]:
            if msg["role"] == "user":
                llm_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                content = msg.get("content") or ""
                # Re-inject tool call summaries so the LLM remembers what it did
                tool_calls_data = msg.get("tool_calls")
                if tool_calls_data:
                    tool_lines = []
                    for tc in tool_calls_data:
                        tool_name = tc.get("tool", "unknown")
                        tool_args = json.dumps(tc.get("args", {}))[:150]
                        tool_result = tc.get("result", "")[:300]
                        tool_lines.append(f"- {tool_name}({tool_args}) → {tool_result}")
                    tool_summary = "\n[Tools used:\n" + "\n".join(tool_lines) + "\n]"
                    content = (content + "\n" + tool_summary) if content else tool_summary
                if content:
                    llm_messages.append({"role": "assistant", "content": content})
        llm_messages.append({"role": "user", "content": user_text})

        # Filter tools by agent's allowlist
        def filter_tools(tools_list):
            if not tools_allowed:
                return tools_list
            allowed_set = set(tools_allowed)
            return [t for t in tools_list if t.get("name", t.get("function", {}).get("name", "")) in allowed_set]

        logger.info(f"Agent turn: session={session_id} agent={agent_id} model={provider}/{model_id} history={len(llm_messages)} msgs")

        try:
            if provider == "openai":
                tools = filter_tools(get_tools_for_openai())
                response_text, tool_calls = await run_openai_turn(
                    api_key, model_id, system_prompt,
                    llm_messages, tools, on_tool_call,
                )
            elif provider == "anthropic":
                tools = filter_tools(get_tools_for_anthropic())
                response_text, tool_calls = await run_anthropic_turn(
                    api_key, model_id, system_prompt,
                    llm_messages, tools, on_tool_call,
                )
            else:
                raise ValueError(f"Unsupported provider: {provider}")

            await self.session_mgr.add_message(
                session_id, "assistant", response_text, tool_calls=tool_calls or None
            )
            await self.session_mgr.set_status(session_id, "idle")

            # Extract and store memories (fire-and-forget, truly non-blocking)
            asyncio.create_task(
                _safe_extract_memories(self.db, session_id, agent_id, user_text, response_text)
            )

            # Extract user profile facts (fire-and-forget)
            asyncio.create_task(
                _safe_extract_profile(self.db, user_text)
            )

            # Extract relationship mentions (fire-and-forget)
            asyncio.create_task(
                _safe_extract_relationships(self.db, user_text)
            )

            logger.info(f"Agent turn complete: session={session_id} agent={agent_id} tools={len(tool_calls)} response_len={len(response_text)}")
            return response_text, tool_calls

        except Exception:
            await self.session_mgr.set_status(session_id, "error")
            logger.exception(f"Agent turn error: session={session_id}")
            raise


    async def run_subtask(self, agent_id: str, task: str) -> str:
        """
        Run a specialist agent on a scoped subtask (no session history).
        Used by the orchestrator's delegate tool.
        Returns the specialist's response text.
        """
        agent_def = await self.get_agent_config(agent_id)
        if not agent_def or agent_def.get("id") == "default":
            # Check DB directly
            agent_doc = await self.db.agents.find_one({"id": agent_id}, {"_id": 0})
            if not agent_doc:
                return f"Error: agent '{agent_id}' not found"
            agent_def = agent_doc

        model_str = agent_def.get("model", self.config.agent.model)
        system_prompt = agent_def.get("system_prompt", "You are a helpful assistant.")
        tools_allowed = agent_def.get("tools_allowed", [])

        # Ensure specialist cannot delegate (prevent recursion)
        tools_allowed = [t for t in tools_allowed if t not in ("delegate", "list_agents")]

        provider, model_id, env_key = resolve_model(model_str)
        api_key = get_api_key(env_key)

        # Single-turn: just the task as the user message
        llm_messages = [{"role": "user", "content": task}]

        # Filter tools
        def filter_tools(tools_list):
            allowed_set = set(tools_allowed)
            return [t for t in tools_list if t.get("name", t.get("function", {}).get("name", "")) in allowed_set]

        logger.info(f"Subtask: agent={agent_id} model={provider}/{model_id} task={task[:80]}...")

        try:
            if provider == "openai":
                tools = filter_tools(get_tools_for_openai())
                response_text, tool_calls = await run_openai_turn(
                    api_key, model_id, system_prompt, llm_messages, tools,
                )
            elif provider == "anthropic":
                tools = filter_tools(get_tools_for_anthropic())
                response_text, tool_calls = await run_anthropic_turn(
                    api_key, model_id, system_prompt, llm_messages, tools,
                )
            else:
                return f"Error: unsupported provider '{provider}'"

            logger.info(f"Subtask complete: agent={agent_id} tools={len(tool_calls)} response_len={len(response_text)}")
            return response_text

        except Exception as e:
            logger.exception(f"Subtask error: agent={agent_id}")
            return f"Error: {str(e)}"
