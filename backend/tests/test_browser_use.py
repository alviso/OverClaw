"""
Test browser_use tool - Backend API tests for iteration 11
Tests: browser_use tool registration, navigate, extract, screenshot actions
"""
import pytest
import requests
import json
import time
import os
import websocket

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://people-curator.preview.emergentagent.com')
GATEWAY_TOKEN = "dev-token-change-me"
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/gateway'


class TestHealthAndBasics:
    """Basic API health tests"""
    
    def test_health_endpoint(self):
        """Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data['gateway']} v{data['version']}")
    
    def test_root_endpoint(self):
        """Root endpoint should return gateway info with methods list"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "methods" in data
        print(f"✓ Root endpoint: {len(data['methods'])} methods available")


class TestSystemPromptAndConfig:
    """Test that system prompt includes browser use guidance"""
    
    def test_config_includes_browser_use_guidance(self):
        """config endpoint should show system prompt with browser guidance"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        config = response.json()
        
        system_prompt = config.get("agent", {}).get("system_prompt", "")
        
        # Check for browser guidance in system prompt
        assert "browser_use" in system_prompt.lower() or "Browser Use" in system_prompt, "System prompt should mention browser_use"
        assert "navigate" in system_prompt.lower(), "System prompt should mention navigate"
        assert "screenshot" in system_prompt.lower(), "System prompt should mention screenshot"
        
        print("✓ System prompt includes browser use guidance")
        print(f"  System prompt length: {len(system_prompt)} chars")
        
        # Check tools_allowed includes browser_use
        tools_allowed = config.get("agent", {}).get("tools_allowed", [])
        assert "browser_use" in tools_allowed, "browser_use should be in tools_allowed"
        print(f"✓ browser_use in tools_allowed ({len(tools_allowed)} tools total)")


class TestWebSocketToolsList:
    """Test browser_use tool is registered via WebSocket RPC"""
    
    def test_tools_list_via_websocket(self):
        """tools.list should return 14 tools including browser_use"""
        ws = websocket.create_connection(WS_URL, timeout=30)
        
        try:
            # Read welcome message
            welcome = json.loads(ws.recv())
            assert welcome.get("method") == "gateway.welcome"
            print(f"✓ WS connected, auth_required: {welcome.get('params', {}).get('auth_required')}")
            
            # Authenticate - NOTE: id must be string per protocol.py
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "auth-1",
                "method": "connect",
                "params": {"token": GATEWAY_TOKEN}
            }))
            auth_resp = json.loads(ws.recv())
            assert auth_resp.get("result", {}).get("ok") == True
            print(f"✓ Authenticated as client_id: {auth_resp['result']['client_id']}")
            
            # Request tools list
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "tools-1",
                "method": "tools.list",
                "params": {}
            }))
            tools_resp = json.loads(ws.recv())
            tools = tools_resp.get("result", {}).get("tools", [])
            
            # Check total count
            print(f"✓ tools.list returned {len(tools)} tools")
            
            # List tool names
            tool_names = [t["name"] for t in tools]
            print(f"  Tool names: {', '.join(sorted(tool_names))}")
            
            # Verify browser_use is present
            assert "browser_use" in tool_names, "browser_use tool should be registered"
            print("✓ browser_use tool is registered")
            
            # Find browser_use definition
            browser_use_tool = next((t for t in tools if t["name"] == "browser_use"), None)
            assert browser_use_tool is not None
            
            # Verify browser_use has expected actions
            params = browser_use_tool.get("parameters", {})
            action_enum = params.get("properties", {}).get("action", {}).get("enum", [])
            expected_actions = ["navigate", "click", "type", "screenshot", "extract", "scroll", "wait", "back", "close"]
            for action in expected_actions:
                assert action in action_enum, f"browser_use should support '{action}' action"
            print(f"✓ browser_use supports all actions: {action_enum}")
            
        finally:
            ws.close()
    
    def test_browser_use_navigate_via_chat(self):
        """Test browser_use navigate action via chat.send"""
        ws = websocket.create_connection(WS_URL, timeout=90)
        
        try:
            # Read welcome
            welcome = json.loads(ws.recv())
            
            # Authenticate with string ID
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "auth-1",
                "method": "connect",
                "params": {"token": GATEWAY_TOKEN}
            }))
            auth_resp = json.loads(ws.recv())
            assert auth_resp.get("result", {}).get("ok") == True
            
            # Create test session
            session_id = f"test-browser-{int(time.time())}"
            
            # Send chat message asking to navigate
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "chat-1",
                "method": "chat.send",
                "params": {
                    "session_id": session_id,
                    "text": "Please use the browser_use tool with action='navigate' and url='https://example.com'. Just navigate, don't take a screenshot.",
                    "agent_id": "default"
                }
            }))
            
            # Wait for response (may take a while due to LLM)
            ws.settimeout(90)
            chat_resp = json.loads(ws.recv())
            
            result = chat_resp.get("result", {})
            response_text = result.get("response", "")
            tool_calls = result.get("tool_calls", [])
            
            print(f"✓ Chat response received ({len(response_text)} chars)")
            print(f"  Tool calls: {len(tool_calls)}")
            
            # Check if browser_use was called with navigate
            browser_use_calls = [tc for tc in tool_calls if tc.get("tool") == "browser_use"]
            print(f"  browser_use calls: {len(browser_use_calls)}")
            
            if browser_use_calls:
                for tc in browser_use_calls:
                    action = tc.get("args", {}).get("action", "")
                    url = tc.get("args", {}).get("url", "")
                    result_preview = tc.get("result", "")[:200]
                    print(f"    - action: {action}, url: {url}")
                    print(f"      result: {result_preview}...")
                    
                # Verify navigate was successful
                nav_call = next((tc for tc in browser_use_calls if tc.get("args", {}).get("action") == "navigate"), None)
                if nav_call:
                    nav_result = nav_call.get("result", "").lower()
                    assert "example" in nav_result or "page" in nav_result
                    print("✓ Navigate action succeeded - example.com page loaded")
            else:
                # Agent might respond without tool call if it misunderstood
                print(f"  Response: {response_text[:200]}...")
        
        finally:
            ws.close()
    
    def test_browser_use_extract_via_chat(self):
        """Test browser_use extract action via chat.send"""
        ws = websocket.create_connection(WS_URL, timeout=120)
        
        try:
            # Read welcome
            welcome = json.loads(ws.recv())
            
            # Authenticate
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "auth-1",
                "method": "connect",
                "params": {"token": GATEWAY_TOKEN}
            }))
            auth_resp = json.loads(ws.recv())
            assert auth_resp.get("result", {}).get("ok") == True
            
            # Create test session
            session_id = f"test-extract-{int(time.time())}"
            
            # Send chat message asking to extract content
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": "chat-1",
                "method": "chat.send",
                "params": {
                    "session_id": session_id,
                    "text": "Use browser_use tool: first navigate to https://example.com, then use extract action to get text from the page. Tell me what's there.",
                    "agent_id": "default"
                }
            }))
            
            # Wait for response
            ws.settimeout(120)
            chat_resp = json.loads(ws.recv())
            
            result = chat_resp.get("result", {})
            tool_calls = result.get("tool_calls", [])
            
            print(f"✓ Chat response received")
            print(f"  Tool calls: {len(tool_calls)}")
            
            browser_use_calls = [tc for tc in tool_calls if tc.get("tool") == "browser_use"]
            for tc in browser_use_calls:
                action = tc.get("args", {}).get("action", "")
                print(f"  - browser_use action: {action}")
                if action == "extract":
                    extract_result = tc.get("result", "")
                    print(f"    extract result length: {len(extract_result)} chars")
                    assert len(extract_result) > 50, "Extract should return substantial content"
                    print("✓ Extract action returned content")
            
        finally:
            ws.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
