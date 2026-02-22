"""
Test Suite: Slack/Webchat Quality Parity Fix
============================================
This iteration tests the fix for Slack vs webchat response quality discrepancy.

Key changes being validated:
1. web_search REMOVED from orchestrator tools (forces delegation to research specialist)
2. Versioned prompt mechanism (prompt_version field)
3. !debug Slack command for diagnostics
4. Agent resolution logging in run_turn

The root cause was: orchestrator had web_search in tools_allowed, so it would do
shallow searches directly instead of delegating to the research specialist which
does multi-step, deep web research.
"""

import pytest
import os
import re
import asyncio
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/app/backend/.env")

# Get the base URL from env - must use the full URL
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://smart-workflow-71.preview.emergentagent.com").rstrip("/")

# MongoDB connection for direct DB checks
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


# =============================================================================
# Section 1: Health Check
# =============================================================================

class TestHealthEndpoint:
    """Verify backend is healthy before running other tests."""
    
    def test_health_endpoint_returns_healthy(self):
        """Health endpoint should return 200 with healthy status."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected 'healthy', got {data.get('status')}"
        print(f"✓ Health check passed: {data}")


# =============================================================================
# Section 2: Orchestrator Tools Configuration (MongoDB)
# =============================================================================

class TestOrchestratorToolsConfig:
    """
    Verify the orchestrator (gateway_config) has correct tools configuration.
    Critical: web_search should NOT be in orchestrator tools.
    """
    
    def test_gateway_config_does_not_have_web_search(self):
        """
        The orchestrator MUST NOT have web_search in tools_allowed.
        This is the key fix: orchestrator should delegate to research specialist.
        """
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None, "gateway_config not found in MongoDB"
        
        agent_config = config.get("agent", {})
        tools_allowed = agent_config.get("tools_allowed", [])
        
        assert "web_search" not in tools_allowed, \
            f"CRITICAL: web_search should NOT be in orchestrator tools! Found: {tools_allowed}"
        print(f"✓ Orchestrator does NOT have web_search (correct)")
    
    def test_gateway_config_has_delegate_tool(self):
        """Orchestrator MUST have 'delegate' tool to delegate to specialists."""
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None, "gateway_config not found in MongoDB"
        
        agent_config = config.get("agent", {})
        tools_allowed = agent_config.get("tools_allowed", [])
        
        assert "delegate" in tools_allowed, \
            f"CRITICAL: delegate missing from orchestrator tools! Found: {tools_allowed}"
        print(f"✓ Orchestrator has 'delegate' tool")
    
    def test_gateway_config_has_list_agents_tool(self):
        """Orchestrator MUST have 'list_agents' tool to see available specialists."""
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None, "gateway_config not found in MongoDB"
        
        agent_config = config.get("agent", {})
        tools_allowed = agent_config.get("tools_allowed", [])
        
        assert "list_agents" in tools_allowed, \
            f"CRITICAL: list_agents missing from orchestrator tools! Found: {tools_allowed}"
        print(f"✓ Orchestrator has 'list_agents' tool")
    
    def test_gateway_config_has_prompt_version_3(self):
        """Orchestrator should have prompt_version = 3 (latest)."""
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None, "gateway_config not found in MongoDB"
        
        agent_config = config.get("agent", {})
        prompt_version = agent_config.get("prompt_version")
        
        assert prompt_version == 3, \
            f"Expected prompt_version=3, got {prompt_version}"
        print(f"✓ Orchestrator prompt_version = {prompt_version}")
    
    def test_orchestrator_prompt_starts_with_overclaw(self):
        """The orchestrator system prompt should start with 'You are OverClaw'."""
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None, "gateway_config not found in MongoDB"
        
        agent_config = config.get("agent", {})
        system_prompt = agent_config.get("system_prompt", "")
        
        assert system_prompt.startswith("You are OverClaw"), \
            f"Prompt should start with 'You are OverClaw', got: {system_prompt[:50]}..."
        print(f"✓ Orchestrator prompt starts correctly: '{system_prompt[:40]}...'")


# =============================================================================
# Section 3: Research Specialist Configuration
# =============================================================================

class TestResearchSpecialistConfig:
    """
    Verify the research specialist agent has web_search in its tools.
    This is where research should happen - via delegation.
    """
    
    def test_research_specialist_has_web_search(self):
        """The research specialist MUST have web_search to do deep research."""
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            agent = await db.agents.find_one({"id": "research"})
            client.close()
            return agent
        
        agent = asyncio.get_event_loop().run_until_complete(run())
        assert agent is not None, "Research specialist not found in MongoDB"
        
        tools_allowed = agent.get("tools_allowed", [])
        
        assert "web_search" in tools_allowed, \
            f"CRITICAL: Research specialist is missing web_search! Found: {tools_allowed}"
        print(f"✓ Research specialist has web_search: {tools_allowed}")
    
    def test_research_specialist_has_browse_webpage(self):
        """Research specialist should also have browse_webpage for deep research."""
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            agent = await db.agents.find_one({"id": "research"})
            client.close()
            return agent
        
        agent = asyncio.get_event_loop().run_until_complete(run())
        assert agent is not None, "Research specialist not found in MongoDB"
        
        tools_allowed = agent.get("tools_allowed", [])
        
        assert "browse_webpage" in tools_allowed, \
            f"Research specialist missing browse_webpage: {tools_allowed}"
        print(f"✓ Research specialist has browse_webpage")


# =============================================================================
# Section 4: Server.py Code Validation
# =============================================================================

class TestServerCodeValidation:
    """
    Validate server.py code has correct ORCHESTRATOR_TOOLS list
    and uses set comparison for tools patching.
    """
    
    def test_orchestrator_tools_list_no_web_search(self):
        """
        ORCHESTRATOR_TOOLS list in server.py should NOT contain web_search.
        This is the declarative source of truth.
        """
        # Read server.py and extract ORCHESTRATOR_TOOLS list
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Find the ORCHESTRATOR_TOOLS list definition
        # It's a multi-line list, so we need to find start and end
        match = re.search(r'ORCHESTRATOR_TOOLS\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match is not None, "Could not find ORCHESTRATOR_TOOLS definition in server.py"
        
        tools_str = match.group(1)
        
        # Parse the tool names from the string
        tool_names = re.findall(r'"([^"]+)"', tools_str)
        
        assert "web_search" not in tool_names, \
            f"CRITICAL: web_search found in ORCHESTRATOR_TOOLS! Tools: {tool_names}"
        
        # Also verify delegate and list_agents are present
        assert "delegate" in tool_names, f"delegate missing from ORCHESTRATOR_TOOLS: {tool_names}"
        assert "list_agents" in tool_names, f"list_agents missing from ORCHESTRATOR_TOOLS: {tool_names}"
        
        print(f"✓ ORCHESTRATOR_TOOLS in server.py is correct ({len(tool_names)} tools, no web_search)")
    
    def test_server_uses_set_comparison_for_tools_patching(self):
        """
        The startup code should use set comparison (not additive $addToSet)
        to ensure stale tools like web_search are REMOVED.
        """
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Check for the set comparison pattern
        assert "set(stored_tools) != set(ORCHESTRATOR_TOOLS)" in content, \
            "Server should use set comparison for tools patching"
        
        # Check it sets the exact list (not $addToSet)
        assert '"$set": {"agent.tools_allowed": ORCHESTRATOR_TOOLS}' in content, \
            "Server should $set the exact ORCHESTRATOR_TOOLS list"
        
        print("✓ Server uses set comparison (declarative tools patching)")
    
    def test_server_has_versioned_prompt_mechanism(self):
        """
        Server should have ORCHESTRATOR_PROMPT_VERSION constant and
        version comparison logic for prompt updates.
        """
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Check for version constant
        match = re.search(r'ORCHESTRATOR_PROMPT_VERSION\s*=\s*(\d+)', content)
        assert match is not None, "ORCHESTRATOR_PROMPT_VERSION constant not found"
        version = int(match.group(1))
        assert version == 3, f"Expected version 3, got {version}"
        
        # Check for version comparison logic
        assert "stored_version < ORCHESTRATOR_PROMPT_VERSION" in content, \
            "Version comparison logic not found"
        
        # Check that it updates prompt_version in DB
        assert '"agent.prompt_version": ORCHESTRATOR_PROMPT_VERSION' in content, \
            "Prompt version update not found"
        
        print(f"✓ Versioned prompt mechanism verified (version={version})")


# =============================================================================
# Section 5: Agent.py Diagnostic Logging
# =============================================================================

class TestAgentDiagnosticLogging:
    """
    Verify agent.py run_turn has diagnostic logging for debugging
    Slack vs webchat quality issues.
    """
    
    def test_agent_has_diagnostic_logging_variables(self):
        """
        run_turn should have has_delegate and has_web_search diagnostic variables.
        """
        agent_path = "/app/backend/gateway/agent.py"
        with open(agent_path, "r") as f:
            content = f.read()
        
        # Check for diagnostic logging variables
        assert "has_delegate" in content, "Missing has_delegate diagnostic variable"
        assert "has_web_search" in content, "Missing has_web_search diagnostic variable"
        
        print("✓ Agent has has_delegate and has_web_search variables")
    
    def test_agent_logs_delegate_and_web_search_status(self):
        """
        The diagnostic log should include delegate and web_search status.
        """
        agent_path = "/app/backend/gateway/agent.py"
        with open(agent_path, "r") as f:
            content = f.read()
        
        # Check the log includes delegate and web_search flags
        # The actual log format is: delegate={has_delegate} web_search={has_web_search}
        assert "delegate={has_delegate}" in content, "Log missing delegate status"
        assert "web_search={has_web_search}" in content, "Log missing web_search status"
        
        print("✓ Agent logs delegate and web_search status in diagnostic log")


# =============================================================================
# Section 6: Slack !debug Command
# =============================================================================

class TestSlackDebugCommand:
    """
    Verify the !debug command exists in slack_channel.py for diagnostics.
    """
    
    def test_slack_channel_has_debug_command(self):
        """The slack_channel.py should have a !debug command handler."""
        slack_path = "/app/backend/gateway/channels/slack_channel.py"
        with open(slack_path, "r") as f:
            content = f.read()
        
        # Check for !debug command handling
        assert '!debug' in content, "!debug command not found in slack_channel.py"
        assert 'elif cmd == "!debug"' in content, "!debug handler not found"
        
        print("✓ !debug command exists in slack_channel.py")
    
    def test_slack_debug_command_shows_agent_config(self):
        """!debug should show agent config (prompt, tools, model, delegate status)."""
        slack_path = "/app/backend/gateway/channels/slack_channel.py"
        with open(slack_path, "r") as f:
            content = f.read()
        
        # Find the debug command section
        debug_start = content.find('elif cmd == "!debug"')
        assert debug_start > 0, "!debug handler not found"
        
        # Get the section until the next elif/else
        debug_section = content[debug_start:debug_start + 2000]
        
        # Check it shows useful diagnostic info
        assert "tools_allowed" in debug_section or "tools" in debug_section, \
            "!debug should show tools_allowed"
        assert "model" in debug_section, "!debug should show model"
        assert "prompt_version" in debug_section, "!debug should show prompt_version"
        assert "has_delegate" in debug_section, "!debug should show delegate status"
        assert "has_web_search" in debug_section, "!debug should show web_search status"
        
        print("✓ !debug command shows agent config diagnostics")
    
    def test_slack_help_command_mentions_debug(self):
        """!help should mention !debug command."""
        slack_path = "/app/backend/gateway/channels/slack_channel.py"
        with open(slack_path, "r") as f:
            content = f.read()
        
        # Find COMMANDS_HELP string
        assert "!debug" in content, "!debug not mentioned in help"
        
        # Check it's in the help text (COMMANDS_HELP)
        help_match = re.search(r'COMMANDS_HELP\s*=\s*\([^)]+\)', content, re.DOTALL)
        if help_match:
            help_text = help_match.group(0)
            assert "!debug" in help_text, "!debug not in COMMANDS_HELP string"
        
        print("✓ !help mentions !debug command")


# =============================================================================
# Section 7: Agents Config Validation
# =============================================================================

class TestAgentsConfigValidation:
    """
    Validate agents_config.py has correct ORCHESTRATOR_PROMPT
    and SPECIALIST_AGENTS definitions.
    """
    
    def test_orchestrator_prompt_starts_correctly(self):
        """ORCHESTRATOR_PROMPT should start with 'You are OverClaw'."""
        import sys
        sys.path.insert(0, "/app/backend")
        from gateway.agents_config import ORCHESTRATOR_PROMPT
        
        assert ORCHESTRATOR_PROMPT.startswith("You are OverClaw"), \
            f"ORCHESTRATOR_PROMPT should start with 'You are OverClaw', got: {ORCHESTRATOR_PROMPT[:50]}..."
        
        print(f"✓ ORCHESTRATOR_PROMPT starts correctly")
    
    def test_specialist_agents_includes_research(self):
        """SPECIALIST_AGENTS should include research agent with web_search."""
        import sys
        sys.path.insert(0, "/app/backend")
        from gateway.agents_config import SPECIALIST_AGENTS
        
        research_agent = None
        for agent in SPECIALIST_AGENTS:
            if agent.get("id") == "research":
                research_agent = agent
                break
        
        assert research_agent is not None, "Research agent not found in SPECIALIST_AGENTS"
        
        tools = research_agent.get("tools_allowed", [])
        assert "web_search" in tools, f"Research agent missing web_search: {tools}"
        
        print(f"✓ Research specialist has web_search in SPECIALIST_AGENTS: {tools}")


# =============================================================================
# Section 8: End-to-End Config Consistency
# =============================================================================

class TestE2EConfigConsistency:
    """
    End-to-end verification that code, config file, and MongoDB are all consistent.
    """
    
    def test_orchestrator_tools_consistency(self):
        """
        Verify ORCHESTRATOR_TOOLS in code matches what's in MongoDB.
        This ensures the startup patching worked correctly.
        """
        # Get tools from server.py
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        match = re.search(r'ORCHESTRATOR_TOOLS\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match is not None
        tools_str = match.group(1)
        code_tools = set(re.findall(r'"([^"]+)"', tools_str))
        
        # Get tools from MongoDB
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None
        db_tools = set(config.get("agent", {}).get("tools_allowed", []))
        
        # Compare
        assert code_tools == db_tools, \
            f"Tools mismatch!\nCode: {sorted(code_tools)}\nDB: {sorted(db_tools)}"
        
        print(f"✓ Orchestrator tools consistent between code and DB ({len(db_tools)} tools)")
    
    def test_no_web_search_anywhere_in_orchestrator_path(self):
        """
        Triple-check: web_search should not be in orchestrator config anywhere.
        """
        # Check MongoDB gateway_config
        async def run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            config = await db.gateway_config.find_one({"_id": "main"})
            client.close()
            return config
        
        config = asyncio.get_event_loop().run_until_complete(run())
        assert config is not None
        db_tools = config.get("agent", {}).get("tools_allowed", [])
        assert "web_search" not in db_tools, f"web_search in gateway_config: {db_tools}"
        
        # Check server.py ORCHESTRATOR_TOOLS
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        match = re.search(r'ORCHESTRATOR_TOOLS\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match is not None
        tools_str = match.group(1)
        code_tools = re.findall(r'"([^"]+)"', tools_str)
        assert "web_search" not in code_tools, f"web_search in ORCHESTRATOR_TOOLS: {code_tools}"
        
        print("✓ web_search is NOT in orchestrator config (MongoDB + code verified)")


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
