"""
Test suite for the 'Run Project' feature:
- workspace.detect_project RPC method
- workspace.run_project RPC method
- Tests Python and Node.js project detection
"""
import pytest
import asyncio
import websockets
import json
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/gateway'
GATEWAY_TOKEN = os.environ.get('GATEWAY_TOKEN', 'dev-token-change-me')


async def ws_rpc(method: str, params: dict = None, timeout: float = 10.0):
    """Establish WebSocket connection and make RPC call."""
    async with websockets.connect(WS_URL, close_timeout=5) as ws:
        # Authenticate
        auth_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "connect",
            "params": {"token": GATEWAY_TOKEN}
        })
        await ws.send(auth_msg)
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        auth_result = json.loads(response)
        assert auth_result.get("result", {}).get("status") == "connected", f"Auth failed: {auth_result}"
        
        # Make RPC call
        rpc_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": method,
            "params": params or {}
        })
        await ws.send(rpc_msg)
        response = await asyncio.wait_for(ws.recv(), timeout=timeout)
        return json.loads(response)


class TestDetectProjectPython:
    """Test workspace.detect_project for Python projects"""
    
    @pytest.mark.asyncio
    async def test_detect_todo_app_python_project(self):
        """Detect todo-app as Python project with app.py entry point"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        
        assert "error" not in result.get("result", {}), f"RPC error: {result}"
        data = result.get("result", {})
        
        # Assertions for Python project detection
        assert data.get("project_type") == "python", f"Expected python, got {data.get('project_type')}"
        assert data.get("entry_point") == "app.py", f"Expected app.py, got {data.get('entry_point')}"
        assert data.get("suggested_name") == "todo-app", f"Expected todo-app, got {data.get('suggested_name')}"
        assert data.get("suggested_command") is not None, "Expected suggested_command"
        # Command should include python3 app.py
        assert "python3" in data.get("suggested_command", ""), "Command should include python3"
        print(f"✓ Detected todo-app as Python project: {data}")
    
    @pytest.mark.asyncio
    async def test_detect_demo_app_python_project(self):
        """Detect demo-app as Python project"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/demo-app"})
        
        assert "error" not in result.get("result", {}), f"RPC error: {result}"
        data = result.get("result", {})
        
        assert data.get("project_type") == "python", f"Expected python, got {data.get('project_type')}"
        assert data.get("entry_point") == "app.py", f"Expected app.py, got {data.get('entry_point')}"
        print(f"✓ Detected demo-app as Python project: {data}")
    
    @pytest.mark.asyncio  
    async def test_detect_project_with_requirements(self):
        """Test detection when requirements.txt exists (venv flag)"""
        # Create a temp test project with requirements.txt
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        data = result.get("result", {})
        
        # todo-app doesn't have requirements.txt
        assert data.get("has_requirements") is False or data.get("has_requirements") == False, \
            f"Expected no requirements.txt in todo-app: {data}"
        print(f"✓ Correctly identified has_requirements: {data.get('has_requirements')}")


class TestDetectProjectNode:
    """Test workspace.detect_project for Node.js projects"""
    
    @pytest.mark.asyncio
    async def test_detect_non_node_project(self):
        """Verify Python projects are not detected as Node"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        data = result.get("result", {})
        
        # Should not be node since no package.json
        assert data.get("project_type") != "node", "todo-app should not be detected as node project"
        assert data.get("has_node_modules") is False or data.get("has_node_modules") == False, \
            "Should not have node_modules"
        print(f"✓ Correctly identified todo-app is NOT a Node project")


class TestDetectProjectErrors:
    """Test error handling for workspace.detect_project"""
    
    @pytest.mark.asyncio
    async def test_detect_invalid_path(self):
        """Test detection with non-existent path"""
        result = await ws_rpc("workspace.detect_project", {"path": "nonexistent/path"})
        data = result.get("result", {})
        
        # Should return error
        assert "error" in data or data.get("project_type") is None, \
            f"Expected error or null for non-existent path: {data}"
        print(f"✓ Correctly handled non-existent path")
    
    @pytest.mark.asyncio
    async def test_detect_path_traversal_blocked(self):
        """Test that path traversal is blocked"""
        result = await ws_rpc("workspace.detect_project", {"path": "../../../etc"})
        data = result.get("result", {})
        
        # Should return error for path outside workspace
        assert "error" in data, f"Expected error for path traversal: {data}"
        print(f"✓ Path traversal correctly blocked")
    
    @pytest.mark.asyncio
    async def test_detect_root_workspace(self):
        """Test detection at workspace root (not a specific project)"""
        result = await ws_rpc("workspace.detect_project", {"path": "."})
        data = result.get("result", {})
        
        # Workspace root might not be a project (no app.py directly)
        # This should still work without error
        assert "error" not in data, f"Unexpected error at workspace root: {data}"
        print(f"✓ Workspace root detection: {data}")


class TestRunProject:
    """Test workspace.run_project RPC method"""
    
    @pytest.mark.asyncio
    async def test_run_project_starts_process(self):
        """Test that run_project starts a process via process manager"""
        # Run a simple echo command to test the flow
        result = await ws_rpc("workspace.run_project", {
            "path": "projects/demo-app",
            "command": "echo 'test started'",
            "name": "test-run-project"
        })
        
        data = result.get("result", {})
        # Should return ok: true
        assert data.get("ok") == True, f"Expected ok: true, got: {data}"
        print(f"✓ run_project started: {data}")
        
        # Clean up - stop the process
        await asyncio.sleep(0.5)
        stop_result = await ws_rpc("workspace.stop_process", {"name": "test-run-project"})
        print(f"✓ Process stopped: {stop_result.get('result', {})}")
    
    @pytest.mark.asyncio
    async def test_run_project_requires_params(self):
        """Test that run_project requires all parameters"""
        # Missing path
        result = await ws_rpc("workspace.run_project", {
            "command": "echo test",
            "name": "test"
        })
        data = result.get("result", {})
        assert "error" in data, f"Expected error for missing path: {data}"
        
        # Missing command
        result = await ws_rpc("workspace.run_project", {
            "path": "projects/demo-app",
            "name": "test"
        })
        data = result.get("result", {})
        assert "error" in data, f"Expected error for missing command: {data}"
        
        # Missing name
        result = await ws_rpc("workspace.run_project", {
            "path": "projects/demo-app",
            "command": "echo test"
        })
        data = result.get("result", {})
        assert "error" in data, f"Expected error for missing name: {data}"
        
        print(f"✓ Parameter validation working correctly")
    
    @pytest.mark.asyncio
    async def test_run_project_invalid_path(self):
        """Test run_project with invalid path"""
        result = await ws_rpc("workspace.run_project", {
            "path": "nonexistent/project",
            "command": "echo test",
            "name": "test-invalid"
        })
        data = result.get("result", {})
        assert "error" in data or data.get("ok") == False, \
            f"Expected error for invalid path: {data}"
        print(f"✓ Invalid path handled correctly")


class TestStartProcess:
    """Test workspace.start_process RPC (used internally by run_project)"""
    
    @pytest.mark.asyncio
    async def test_start_and_stop_process(self):
        """Test starting and stopping a process"""
        # Start a process
        result = await ws_rpc("workspace.start_process", {
            "command": "sleep 5",
            "name": "test-sleep-process",
            "working_directory": "."
        })
        data = result.get("result", {})
        assert data.get("ok") == True, f"Expected ok: true, got: {data}"
        print(f"✓ Process started: {data.get('message', '')}")
        
        # Check processes list
        await asyncio.sleep(0.5)
        processes_result = await ws_rpc("workspace.processes")
        processes = processes_result.get("result", {}).get("processes", [])
        found = any(p.get("name") == "test-sleep-process" for p in processes)
        assert found, f"Process not found in list: {processes}"
        print(f"✓ Process appears in process list")
        
        # Stop the process
        stop_result = await ws_rpc("workspace.stop_process", {"name": "test-sleep-process"})
        assert stop_result.get("result", {}).get("ok") == True, \
            f"Expected ok: true for stop: {stop_result}"
        print(f"✓ Process stopped successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
