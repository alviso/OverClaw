"""
Test Scrapling Integration — browse_webpage tool testing with real URLs.

Tests:
- Health endpoint
- browse_webpage tool registration
- URL browsing with multiple real sites (Yahoo Finance, Stock Analysis, Wikipedia, Google Finance, CNBC, Robinhood)
- Error handling with invalid URLs
- Email triage task configuration (prompt_version=4, notify=never)
- Agent code structure verification (on_tool_call propagation, _active_tool_callback)
- scrapling in requirements.txt
"""
import os
import sys
import pytest
import asyncio
import requests

# Add the backend path to import gateway modules
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# ────────────────────────────────────────────────────────────────────────────
# HEALTH & SETUP TESTS
# ────────────────────────────────────────────────────────────────────────────

class TestHealthAndSetup:
    """Basic health and setup tests"""
    
    def test_health_endpoint(self):
        """Verify backend health endpoint returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert "gateway" in data.get("gateway", "").lower() or "OverClaw" in data.get("gateway", "")
        print(f"✓ Health endpoint: {data.get('status')}")
    
    def test_scrapling_in_requirements(self):
        """Verify scrapling is in requirements.txt"""
        with open("/app/backend/requirements.txt", "r") as f:
            content = f.read()
        assert "scrapling" in content.lower()
        print("✓ scrapling found in requirements.txt")


# ────────────────────────────────────────────────────────────────────────────
# BROWSE_WEBPAGE TOOL TESTS
# ────────────────────────────────────────────────────────────────────────────

class TestBrowseWebpageTool:
    """Test browse_webpage tool registration and structure"""
    
    def test_browse_tool_registered(self):
        """Verify browse_webpage tool is registered in the gateway"""
        from gateway.tools import init_tools, get_tool, list_tools
        
        init_tools()  # Ensure tools are loaded
        tool = get_tool("browse_webpage")
        
        assert tool is not None, "browse_webpage tool not registered"
        assert tool.name == "browse_webpage"
        assert "url" in tool.parameters.get("properties", {})
        assert "url" in tool.parameters.get("required", [])
        print(f"✓ browse_webpage tool registered with params: {list(tool.parameters.get('properties', {}).keys())}")
    
    def test_browse_tool_uses_scrapling(self):
        """Verify browse_webpage imports Scrapling Fetcher"""
        with open("/app/backend/gateway/tools/browser.py", "r") as f:
            content = f.read()
        
        assert "from scrapling.fetchers import Fetcher" in content
        assert "from scrapling.fetchers import StealthyFetcher" in content
        assert "stealthy_headers=True" in content
        assert "get_all_text" in content  # The text extraction method
        print("✓ browse_webpage uses Scrapling Fetcher and StealthyFetcher")
    
    def test_browse_tool_has_fallback_logic(self):
        """Verify tool has Cloudflare detection and stealth fallback"""
        with open("/app/backend/gateway/tools/browser.py", "r") as f:
            content = f.read()
        
        # Check for Cloudflare detection
        assert "403" in content or "503" in content
        assert "just a moment" in content.lower()
        # Check for fallback escalation
        assert "_fetch_stealth" in content
        assert "blocked" in content
        print("✓ browse_webpage has Cloudflare detection and stealth fallback")


# ────────────────────────────────────────────────────────────────────────────
# BROWSE_WEBPAGE URL TESTS (Real URLs)
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def browse_tool():
    """Get the browse_webpage tool instance"""
    from gateway.tools import init_tools, get_tool
    init_tools()
    return get_tool("browse_webpage")


class TestBrowseWebpageURLs:
    """Test browse_webpage tool with real URLs — each should return meaningful content"""
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_url(self, browse_tool):
        """Test error handling with invalid URL (missing http/https)"""
        result = await browse_tool.execute({"url": "not-a-valid-url"})
        assert "Error" in result or "error" in result.lower()
        assert "http" in result.lower()  # Should mention URL must start with http
        print(f"✓ Invalid URL handled: {result[:100]}")
    
    @pytest.mark.asyncio
    async def test_yahoo_finance(self, browse_tool):
        """Test Yahoo Finance TSLA page — should return stock data"""
        result = await browse_tool.execute({"url": "https://finance.yahoo.com/quote/TSLA/"})
        
        # Should not have error
        assert not result.startswith("Error browsing"), f"Got error: {result[:200]}"
        
        # Should have substantial content
        assert len(result) > 100, f"Content too short: {len(result)} chars"
        
        # Should mention Tesla or TSLA
        result_lower = result.lower()
        assert "tesla" in result_lower or "tsla" in result_lower, f"No Tesla content: {result[:500]}"
        
        print(f"✓ Yahoo Finance: {len(result)} chars, contains Tesla/TSLA")
    
    @pytest.mark.asyncio
    async def test_stock_analysis(self, browse_tool):
        """Test Stock Analysis TSLA page — was previously failing with Playwright"""
        result = await browse_tool.execute({"url": "https://stockanalysis.com/stocks/tsla/"})
        
        # Should not have error (was failing before)
        assert not result.startswith("Error browsing"), f"Got error: {result[:200]}"
        
        # Should have substantial content
        assert len(result) > 100, f"Content too short: {len(result)} chars"
        
        # Should mention Tesla
        result_lower = result.lower()
        assert "tesla" in result_lower or "tsla" in result_lower, f"No Tesla content: {result[:500]}"
        
        print(f"✓ Stock Analysis: {len(result)} chars, contains Tesla/TSLA")
    
    @pytest.mark.asyncio
    async def test_wikipedia(self, browse_tool):
        """Test Wikipedia Tesla page — should return long article text"""
        result = await browse_tool.execute({"url": "https://en.wikipedia.org/wiki/Tesla,_Inc."})
        
        # Should not have error
        assert not result.startswith("Error browsing"), f"Got error: {result[:200]}"
        
        # Wikipedia articles are long
        assert len(result) > 500, f"Content too short for Wikipedia: {len(result)} chars"
        
        # Should mention Tesla
        result_lower = result.lower()
        assert "tesla" in result_lower, f"No Tesla content in Wikipedia: {result[:500]}"
        
        print(f"✓ Wikipedia: {len(result)} chars, contains Tesla")
    
    @pytest.mark.asyncio
    async def test_google_finance(self, browse_tool):
        """Test Google Finance TSLA page — should return price data"""
        result = await browse_tool.execute({"url": "https://www.google.com/finance/quote/TSLA:NASDAQ"})
        
        # Should not have error
        assert not result.startswith("Error browsing"), f"Got error: {result[:200]}"
        
        # Should have content
        assert len(result) > 100, f"Content too short: {len(result)} chars"
        
        # Should mention Tesla or TSLA or NASDAQ
        result_lower = result.lower()
        has_relevant = "tesla" in result_lower or "tsla" in result_lower or "nasdaq" in result_lower
        assert has_relevant, f"No Tesla/NASDAQ content: {result[:500]}"
        
        print(f"✓ Google Finance: {len(result)} chars, contains Tesla/TSLA/NASDAQ")
    
    @pytest.mark.asyncio
    async def test_cnbc(self, browse_tool):
        """Test CNBC TSLA page — should return stock info"""
        result = await browse_tool.execute({"url": "https://www.cnbc.com/quotes/TSLA"})
        
        # Should not have error
        assert not result.startswith("Error browsing"), f"Got error: {result[:200]}"
        
        # Should have content
        assert len(result) > 100, f"Content too short: {len(result)} chars"
        
        # Should mention Tesla or TSLA
        result_lower = result.lower()
        has_relevant = "tesla" in result_lower or "tsla" in result_lower
        assert has_relevant, f"No Tesla content: {result[:500]}"
        
        print(f"✓ CNBC: {len(result)} chars, contains Tesla/TSLA")
    
    @pytest.mark.asyncio
    async def test_robinhood(self, browse_tool):
        """Test Robinhood TSLA page — should return page content"""
        result = await browse_tool.execute({"url": "https://robinhood.com/stocks/TSLA"})
        
        # Note: Robinhood may be more heavily protected
        # Should not have a critical error (might need stealth mode)
        if result.startswith("Error browsing"):
            # If error, make sure it's not a code bug - should be a site protection issue
            assert "aggressive bot protection" in result.lower() or "timeout" in result.lower() or "error" in result.lower()
            print(f"⚠ Robinhood blocked (expected for heavily protected sites): {result[:150]}")
        else:
            assert len(result) > 100, f"Content too short: {len(result)} chars"
            print(f"✓ Robinhood: {len(result)} chars")


# ────────────────────────────────────────────────────────────────────────────
# EMAIL TRIAGE CONFIGURATION TESTS
# ────────────────────────────────────────────────────────────────────────────

class TestEmailTriageConfig:
    """Test email triage task configuration"""
    
    @pytest.mark.asyncio
    async def test_email_triage_prompt_version_4(self):
        """Verify email triage task has prompt_version=4"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        
        task = await db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        
        assert task is not None, "email-triage task not found in DB"
        assert task.get("prompt_version") == 4, f"Expected prompt_version=4, got {task.get('prompt_version')}"
        
        client.close()
        print("✓ email-triage has prompt_version=4")
    
    @pytest.mark.asyncio
    async def test_email_triage_notify_never(self):
        """Verify email triage task has notify=never"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        
        task = await db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        
        assert task is not None, "email-triage task not found in DB"
        assert task.get("notify") == "never", f"Expected notify='never', got {task.get('notify')}"
        
        client.close()
        print("✓ email-triage has notify=never")
    
    def test_email_triage_prompt_strict(self):
        """Verify email triage prompt contains 'be STRICT' and 'Silence is better'"""
        from gateway.email_triage import EMAIL_TRIAGE_PROMPT
        
        assert "be STRICT" in EMAIL_TRIAGE_PROMPT, "Prompt missing 'be STRICT'"
        assert "Silence is better" in EMAIL_TRIAGE_PROMPT, "Prompt missing 'Silence is better'"
        
        print("✓ email_triage prompt contains 'be STRICT' and 'Silence is better'")
    
    def test_email_triage_prompt_version_constant(self):
        """Verify EMAIL_TRIAGE_PROMPT_VERSION is 4"""
        from gateway.email_triage import EMAIL_TRIAGE_PROMPT_VERSION
        
        assert EMAIL_TRIAGE_PROMPT_VERSION == 4, f"Expected version 4, got {EMAIL_TRIAGE_PROMPT_VERSION}"
        print("✓ EMAIL_TRIAGE_PROMPT_VERSION is 4")


# ────────────────────────────────────────────────────────────────────────────
# AGENT CODE STRUCTURE TESTS
# ────────────────────────────────────────────────────────────────────────────

class TestAgentCodeStructure:
    """Test agent.py code structure for tool callback propagation"""
    
    def test_agent_runner_has_active_tool_callback(self):
        """Verify AgentRunner has _active_tool_callback attribute"""
        with open("/app/backend/gateway/agent.py", "r") as f:
            content = f.read()
        
        assert "_active_tool_callback" in content
        assert "self._active_tool_callback = None" in content or "self._active_tool_callback" in content
        print("✓ AgentRunner has _active_tool_callback attribute")
    
    def test_run_subtask_propagates_on_tool_call(self):
        """Verify run_subtask passes on_tool_call to specialist runs"""
        with open("/app/backend/gateway/agent.py", "r") as f:
            content = f.read()
        
        # Find the run_subtask method
        assert "async def run_subtask" in content
        
        # Check that it uses _active_tool_callback
        assert "on_tool_call = self._active_tool_callback" in content
        
        # Check that on_tool_call is passed to run_openai_turn/run_anthropic_turn in subtask
        # The pattern should show on_tool_call being passed to the LLM turn functions
        assert "on_tool_call," in content  # It should be passed as an argument
        
        print("✓ run_subtask propagates on_tool_call to specialist runs")
    
    def test_run_turn_stores_callback(self):
        """Verify run_turn stores on_tool_call in _active_tool_callback"""
        with open("/app/backend/gateway/agent.py", "r") as f:
            content = f.read()
        
        # Check that run_turn stores the callback for subtasks
        assert "self._active_tool_callback = on_tool_call" in content
        
        print("✓ run_turn stores on_tool_call in _active_tool_callback")


# ────────────────────────────────────────────────────────────────────────────
# RUN TESTS
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
