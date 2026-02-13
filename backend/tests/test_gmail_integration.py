"""
Gmail Integration & Browser-Use Tool Tests - Iteration 12
Tests for the two new features:
1. Gmail OAuth 2.0 integration endpoints
2. Browser-use library integration (tool registration)
"""
import pytest
import requests
import asyncio
import websockets
import json
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
GATEWAY_TOKEN = "dev-token-change-me"


class TestHealthAndBasics:
    """Basic health and endpoint tests"""
    
    def test_health_endpoint_returns_healthy(self):
        """Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "gateway" in data
        assert data["gateway"] == "OverClaw Gateway"
        print(f"Health check passed: {data['status']}")
    
    def test_root_endpoint_returns_gateway_info(self):
        """Root endpoint should return gateway info"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "methods" in data
        assert len(data["methods"]) > 30  # Should have many RPC methods
        print(f"Gateway info: {data['gateway']} v{data['version']}")


class TestGmailOAuthEndpoints:
    """Gmail OAuth 2.0 endpoint tests"""
    
    def test_gmail_status_disconnected(self):
        """Gmail status should return connected: false when not configured"""
        response = requests.get(f"{BASE_URL}/api/oauth/gmail/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] == False
        print("Gmail status: disconnected (expected)")
    
    def test_gmail_login_returns_400_without_credentials(self):
        """Gmail login should return 400 when Google credentials not configured"""
        # Use allow_redirects=False to catch the redirect/error response
        response = requests.get(f"{BASE_URL}/api/oauth/gmail/login", allow_redirects=False)
        # Should return 400 with error message about missing credentials
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "GOOGLE_CLIENT_ID" in data["error"] or "GOOGLE_CLIENT_SECRET" in data["error"]
        print(f"Gmail login error (expected): {data['error']}")
    
    def test_gmail_disconnect_no_connection(self):
        """Gmail disconnect should work even when not connected"""
        response = requests.post(f"{BASE_URL}/api/oauth/gmail/disconnect")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        # ok=False is expected when no connection exists
        assert data["message"] == "No Gmail connection found" or data["ok"] == True
        print(f"Gmail disconnect: {data['message']}")
    
    def test_gmail_status_with_user_id_param(self):
        """Gmail status should accept user_id parameter"""
        response = requests.get(f"{BASE_URL}/api/oauth/gmail/status?user_id=test_user")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        print(f"Gmail status for test_user: connected={data['connected']}")


class TestToolsRegistration:
    """Test that all 15 tools are registered including browser_use and gmail"""
    
    @pytest.fixture
    def ws_connection(self):
        """Fixture to provide WebSocket connection"""
        return None  # Will be used async
    
    def test_tools_list_via_http(self):
        """Test tools are available (via WebSocket RPC)"""
        # We'll use the synchronous approach to verify tools exist
        import asyncio
        
        async def get_tools():
            uri = f"wss://{BASE_URL.replace('https://', '').replace('http://', '')}/api/gateway"
            async with websockets.connect(uri) as ws:
                # Wait for welcome
                await ws.recv()
                
                # Authenticate
                auth_msg = {"jsonrpc": "2.0", "id": "auth-1", "method": "connect", "params": {"token": GATEWAY_TOKEN}}
                await ws.send(json.dumps(auth_msg))
                await ws.recv()
                
                # Get tools list
                tools_msg = {"jsonrpc": "2.0", "id": "tools-1", "method": "tools.list", "params": {}}
                await ws.send(json.dumps(tools_msg))
                tools_resp = await ws.recv()
                return json.loads(tools_resp)
        
        result = asyncio.get_event_loop().run_until_complete(get_tools())
        
        assert "result" in result
        assert "tools" in result["result"]
        tools = result["result"]["tools"]
        
        # Should have 15 tools
        assert len(tools) == 15, f"Expected 15 tools, got {len(tools)}"
        
        tool_names = [t["name"] for t in tools]
        
        # Check browser_use is registered
        assert "browser_use" in tool_names, "browser_use tool not found"
        
        # Check gmail is registered
        assert "gmail" in tool_names, "gmail tool not found"
        
        print(f"Tools registered: {len(tools)}")
        print(f"Tool names: {', '.join(tool_names)}")
    
    def test_browser_use_tool_has_correct_schema(self):
        """Verify browser_use tool has proper parameters"""
        import asyncio
        
        async def get_browser_use_tool():
            uri = f"wss://{BASE_URL.replace('https://', '').replace('http://', '')}/api/gateway"
            async with websockets.connect(uri) as ws:
                await ws.recv()  # welcome
                
                auth_msg = {"jsonrpc": "2.0", "id": "auth-1", "method": "connect", "params": {"token": GATEWAY_TOKEN}}
                await ws.send(json.dumps(auth_msg))
                await ws.recv()
                
                tools_msg = {"jsonrpc": "2.0", "id": "tools-1", "method": "tools.list", "params": {}}
                await ws.send(json.dumps(tools_msg))
                tools_resp = await ws.recv()
                return json.loads(tools_resp)
        
        result = asyncio.get_event_loop().run_until_complete(get_browser_use_tool())
        tools = result["result"]["tools"]
        
        browser_use_tool = next((t for t in tools if t["name"] == "browser_use"), None)
        assert browser_use_tool is not None
        
        # Check description mentions autonomous/browser-use
        desc = browser_use_tool["description"].lower()
        assert "autonomous" in desc or "browser" in desc, "browser_use should mention autonomous browser"
        
        # Check parameters include task
        params = browser_use_tool["parameters"]
        assert "properties" in params
        assert "task" in params["properties"], "browser_use should have 'task' parameter"
        assert "required" in params
        assert "task" in params["required"], "task should be required"
        
        print(f"browser_use description: {browser_use_tool['description'][:100]}...")
    
    def test_gmail_tool_has_correct_schema(self):
        """Verify gmail tool has proper parameters"""
        import asyncio
        
        async def get_gmail_tool():
            uri = f"wss://{BASE_URL.replace('https://', '').replace('http://', '')}/api/gateway"
            async with websockets.connect(uri) as ws:
                await ws.recv()  # welcome
                
                auth_msg = {"jsonrpc": "2.0", "id": "auth-1", "method": "connect", "params": {"token": GATEWAY_TOKEN}}
                await ws.send(json.dumps(auth_msg))
                await ws.recv()
                
                tools_msg = {"jsonrpc": "2.0", "id": "tools-1", "method": "tools.list", "params": {}}
                await ws.send(json.dumps(tools_msg))
                tools_resp = await ws.recv()
                return json.loads(tools_resp)
        
        result = asyncio.get_event_loop().run_until_complete(get_gmail_tool())
        tools = result["result"]["tools"]
        
        gmail_tool = next((t for t in tools if t["name"] == "gmail"), None)
        assert gmail_tool is not None
        
        # Check description mentions email/gmail
        desc = gmail_tool["description"].lower()
        assert "email" in desc or "gmail" in desc, "gmail tool should mention email/gmail"
        
        # Check parameters include action
        params = gmail_tool["parameters"]
        assert "properties" in params
        assert "action" in params["properties"], "gmail should have 'action' parameter"
        
        # Verify action enum values
        action_param = params["properties"]["action"]
        assert "enum" in action_param
        expected_actions = ["list", "search", "read", "send"]
        for action in expected_actions:
            assert action in action_param["enum"], f"gmail action should include '{action}'"
        
        print(f"gmail description: {gmail_tool['description'][:100]}...")
        print(f"gmail actions: {action_param['enum']}")


class TestWebSocketAuth:
    """Test WebSocket connection and authentication"""
    
    def test_websocket_auth_works(self):
        """Test WebSocket authentication with gateway token"""
        import asyncio
        
        async def test_auth():
            uri = f"wss://{BASE_URL.replace('https://', '').replace('http://', '')}/api/gateway"
            async with websockets.connect(uri) as ws:
                # Wait for welcome
                welcome = await ws.recv()
                welcome_data = json.loads(welcome)
                assert welcome_data["method"] == "gateway.welcome"
                
                # Authenticate
                auth_msg = {"jsonrpc": "2.0", "id": "auth-1", "method": "connect", "params": {"token": GATEWAY_TOKEN}}
                await ws.send(json.dumps(auth_msg))
                auth_resp = await ws.recv()
                auth_data = json.loads(auth_resp)
                
                assert "result" in auth_data
                assert auth_data["result"]["ok"] == True
                assert "client_id" in auth_data["result"]
                
                return auth_data["result"]
        
        result = asyncio.get_event_loop().run_until_complete(test_auth())
        print(f"WebSocket auth passed, client_id: {result['client_id']}")
    
    def test_websocket_auth_fails_with_bad_token(self):
        """Test WebSocket authentication fails with invalid token"""
        import asyncio
        
        async def test_bad_auth():
            uri = f"wss://{BASE_URL.replace('https://', '').replace('http://', '')}/api/gateway"
            async with websockets.connect(uri) as ws:
                await ws.recv()  # welcome
                
                # Authenticate with bad token
                auth_msg = {"jsonrpc": "2.0", "id": "auth-1", "method": "connect", "params": {"token": "wrong-token"}}
                await ws.send(json.dumps(auth_msg))
                auth_resp = await ws.recv()
                auth_data = json.loads(auth_resp)
                
                assert "error" in auth_data
                return auth_data
        
        result = asyncio.get_event_loop().run_until_complete(test_bad_auth())
        print(f"Bad token correctly rejected: {result['error']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
