"""
Workspace Explorer RPC Methods Testing via WebSocket

Tests for:
- workspace.files - Directory listing and file content
- workspace.processes - Process list
- workspace.tools - Custom tools list
- workspace.tool_delete - Delete custom tools
- workspace.process_output - Process output
"""
import pytest
import json
import asyncio
import os
import websockets

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/gateway'
GATEWAY_TOKEN = 'dev-token-change-me'


async def make_rpc_call(method, params=None, timeout=15):
    """Connect, authenticate, make RPC call, return result"""
    async with websockets.connect(WS_URL) as ws:
        # First receive the welcome message
        welcome = await asyncio.wait_for(ws.recv(), timeout=10)
        welcome_data = json.loads(welcome)
        print(f"Welcome message: {welcome_data.get('method', 'unknown')}")
        
        # Authenticate using "connect" method (not auth.token)
        auth_msg = {
            "jsonrpc": "2.0",
            "id": "auth-1",
            "method": "connect",
            "params": {"token": GATEWAY_TOKEN, "client_type": "test"}
        }
        await ws.send(json.dumps(auth_msg))
        response = await asyncio.wait_for(ws.recv(), timeout=10)
        auth_result = json.loads(response)
        
        if auth_result.get("error") or not auth_result.get("result", {}).get("ok"):
            raise Exception(f"Auth failed: {auth_result}")
        
        print(f"Authenticated as client: {auth_result.get('result', {}).get('client_id')}")
        
        # Make RPC call
        msg = {
            "jsonrpc": "2.0",
            "id": f"test-{method}",
            "method": method,
            "params": params or {}
        }
        await ws.send(json.dumps(msg))
        response = await asyncio.wait_for(ws.recv(), timeout=timeout)
        return json.loads(response)


class TestWorkspaceExplorerRPC:
    """Test workspace explorer RPC methods via WebSocket"""

    def test_workspace_files_root_directory(self):
        """Test workspace.files returns root directory listing"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.files", {"path": "."})
        )
        
        assert "result" in result, f"Expected result in response: {result}"
        data = result["result"]
        
        # Check response structure
        assert data.get("type") == "directory", f"Expected directory type: {data}"
        assert "items" in data, f"Expected items in response: {data}"
        assert "current_path" in data, f"Expected current_path in response: {data}"
        
        # Should have at least custom_tools and projects directories
        item_names = [item["name"] for item in data["items"]]
        assert "custom_tools" in item_names or "projects" in item_names, f"Expected workspace dirs: {item_names}"
        print(f"✓ workspace.files root returned {len(data['items'])} items: {item_names}")

    def test_workspace_files_navigate_to_projects(self):
        """Test navigating into projects directory"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.files", {"path": "projects"})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert data.get("type") == "directory", f"Expected directory type: {data}"
        # Projects should have README.md and src folder
        item_names = [item["name"] for item in data.get("items", [])]
        assert "README.md" in item_names, f"Expected README.md in projects: {item_names}"
        assert "src" in item_names, f"Expected src in projects: {item_names}"
        print(f"✓ workspace.files projects returned {len(data['items'])} items: {item_names}")

    def test_workspace_files_read_file_content(self):
        """Test reading file content"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.files", {"path": "projects/README.md"})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert data.get("type") == "file", f"Expected file type: {data}"
        assert "content" in data, f"Expected content in file response: {data}"
        assert "name" in data, f"Expected name in file response: {data}"
        assert data["name"] == "README.md", f"Expected README.md: {data}"
        assert "size" in data, f"Expected size in file response: {data}"
        print(f"✓ workspace.files read file content: {len(data['content'])} chars")

    def test_workspace_files_path_not_found(self):
        """Test workspace.files handles non-existent paths"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.files", {"path": "nonexistent_dir"})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        # Should return error for non-existent path
        assert "error" in data or data.get("items") == [], f"Expected error or empty items for nonexistent path: {data}"
        print(f"✓ workspace.files handles nonexistent path correctly")

    def test_workspace_files_security_path_traversal(self):
        """Test workspace.files blocks path traversal attempts"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.files", {"path": "../../../etc"})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        # Should return error for path outside workspace
        assert "error" in data, f"Expected error for path traversal: {data}"
        print(f"✓ workspace.files blocks path traversal: {data.get('error')}")

    def test_workspace_processes_list(self):
        """Test workspace.processes returns process list"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.processes")
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert "processes" in data, f"Expected processes key: {data}"
        assert "count" in data, f"Expected count key: {data}"
        assert isinstance(data["processes"], list), f"Expected processes to be list: {data}"
        assert data["count"] == len(data["processes"]), f"Count mismatch: {data}"
        print(f"✓ workspace.processes returned {data['count']} processes")

    def test_workspace_tools_list(self):
        """Test workspace.tools returns custom tools list"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.tools")
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert "tools" in data, f"Expected tools key: {data}"
        assert "count" in data, f"Expected count key: {data}"
        assert isinstance(data["tools"], list), f"Expected tools to be list: {data}"
        assert data["count"] == len(data["tools"]), f"Count mismatch: {data}"
        print(f"✓ workspace.tools returned {data['count']} custom tools")

    def test_workspace_process_output_missing_pid(self):
        """Test workspace.process_output requires pid"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.process_output", {})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert "error" in data, f"Expected error for missing pid: {data}"
        assert "pid" in data["error"].lower(), f"Expected pid in error message: {data}"
        print(f"✓ workspace.process_output requires pid: {data.get('error')}")

    def test_workspace_process_output_nonexistent_pid(self):
        """Test workspace.process_output handles nonexistent pid"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.process_output", {"pid": "999999"})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert "error" in data, f"Expected error for nonexistent pid: {data}"
        print(f"✓ workspace.process_output handles nonexistent pid: {data.get('error')}")

    def test_workspace_tool_delete_missing_name(self):
        """Test workspace.tool_delete requires name"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.tool_delete", {})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert "error" in data, f"Expected error for missing name: {data}"
        print(f"✓ workspace.tool_delete requires name: {data.get('error')}")

    def test_workspace_tool_delete_nonexistent_tool(self):
        """Test workspace.tool_delete handles nonexistent tool"""
        result = asyncio.get_event_loop().run_until_complete(
            make_rpc_call("workspace.tool_delete", {"name": "nonexistent_tool_xyz"})
        )
        
        assert "result" in result, f"Expected result: {result}"
        data = result["result"]
        
        assert "error" in data, f"Expected error for nonexistent tool: {data}"
        print(f"✓ workspace.tool_delete handles nonexistent tool: {data.get('error')}")


class TestHealthEndpoint:
    """Test backend health endpoint"""

    def test_health_endpoint(self):
        """Test /api/health endpoint returns healthy status"""
        import requests
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        
        assert data.get("status") == "healthy", f"Expected healthy status: {data}"
        assert "version" in data, f"Expected version in response: {data}"
        assert "uptime" in data, f"Expected uptime in response: {data}"
        print(f"✓ Health endpoint: status={data['status']}, version={data['version']}, uptime={data['uptime']}")


class TestSlackHealthCheckLoop:
    """Verify Slack health check loop implementation exists"""

    def test_slack_health_check_method_exists(self):
        """Verify _health_check_loop method exists in slack_channel.py"""
        # Read the slack channel file
        with open('/app/backend/gateway/channels/slack_channel.py', 'r') as f:
            content = f.read()
        
        # Check for _health_check_loop method
        assert "async def _health_check_loop" in content, "Missing _health_check_loop method"
        assert "_run_handler" in content, "Missing _run_handler method"
        assert "consecutive_failures" in content, "Missing consecutive_failures tracking"
        assert "auth_test" in content, "Missing auth_test call in health check"
        print("✓ Slack _health_check_loop method exists with proper implementation")

    def test_slack_run_handler_reconnect_logic(self):
        """Verify _run_handler has reconnection logic"""
        with open('/app/backend/gateway/channels/slack_channel.py', 'r') as f:
            content = f.read()
        
        assert "max_retries" in content, "Missing max_retries in _run_handler"
        assert "reconnecting" in content.lower() or "reconnect" in content.lower(), "Missing reconnect logic"
        assert "asyncio.wait" in content, "Missing asyncio.wait for concurrent tasks"
        print("✓ Slack _run_handler has proper reconnection logic")
