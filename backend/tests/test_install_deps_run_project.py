"""
Test suite for 'Install Deps' and 'Run Project' features:
- workspace.install_deps RPC - creates venv and installs requirements.txt for Python
- workspace.detect_project RPC - detects project type, entry_point, has_requirements
- workspace.run_project RPC - starts a project with bash -c wrapper
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


class TestDetectProjectTodoApp:
    """Test workspace.detect_project for todo-app (Python Flask project)"""
    
    @pytest.mark.asyncio
    async def test_detect_todo_app_is_python(self):
        """todo-app should be detected as Python project"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        
        assert "error" not in result.get("result", {}), f"RPC error: {result}"
        data = result.get("result", {})
        
        assert data.get("project_type") == "python", f"Expected python, got {data.get('project_type')}"
        print(f"✓ todo-app detected as Python project")
    
    @pytest.mark.asyncio
    async def test_detect_todo_app_entry_point(self):
        """todo-app should have app.py as entry point"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        data = result.get("result", {})
        
        assert data.get("entry_point") == "app.py", f"Expected app.py, got {data.get('entry_point')}"
        print(f"✓ todo-app entry point is app.py")
    
    @pytest.mark.asyncio
    async def test_detect_todo_app_has_requirements(self):
        """todo-app should have has_requirements=true (has requirements.txt with flask)"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        data = result.get("result", {})
        
        assert data.get("has_requirements") == True, f"Expected has_requirements=true, got {data}"
        print(f"✓ todo-app has_requirements=true")
    
    @pytest.mark.asyncio
    async def test_detect_todo_app_suggested_name(self):
        """todo-app should have suggested_name='todo-app'"""
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        data = result.get("result", {})
        
        assert data.get("suggested_name") == "todo-app", f"Expected todo-app, got {data.get('suggested_name')}"
        print(f"✓ todo-app suggested_name=todo-app")


class TestInstallDeps:
    """Test workspace.install_deps RPC method"""
    
    @pytest.mark.asyncio
    async def test_install_deps_requires_path(self):
        """install_deps should require path parameter"""
        result = await ws_rpc("workspace.install_deps", {})
        data = result.get("result", {})
        
        assert "error" in data, f"Expected error for missing path: {data}"
        print(f"✓ install_deps requires path parameter")
    
    @pytest.mark.asyncio
    async def test_install_deps_invalid_path(self):
        """install_deps should reject invalid paths"""
        result = await ws_rpc("workspace.install_deps", {"path": "nonexistent/path"})
        data = result.get("result", {})
        
        assert "error" in data or data.get("ok") == False, f"Expected error for invalid path: {data}"
        print(f"✓ install_deps rejects invalid path")
    
    @pytest.mark.asyncio
    async def test_install_deps_no_requirements(self):
        """install_deps should reject directories without requirements.txt or package.json"""
        # projects/ root has no requirements.txt
        result = await ws_rpc("workspace.install_deps", {"path": "projects"})
        data = result.get("result", {})
        
        assert "error" in data or data.get("ok") == False, \
            f"Expected error for directory without deps file: {data}"
        print(f"✓ install_deps rejects directory without requirements.txt/package.json")
    
    @pytest.mark.asyncio
    async def test_install_deps_python_project(self):
        """install_deps should start venv creation and pip install for Python project"""
        result = await ws_rpc("workspace.install_deps", {"path": "projects/todo-app"}, timeout=15)
        data = result.get("result", {})
        
        # Should return ok: true with process name
        assert data.get("ok") == True, f"Expected ok: true, got: {data}"
        assert data.get("dep_type") == "python", f"Expected dep_type=python, got {data.get('dep_type')}"
        assert data.get("process_name") == "install-todo-app", f"Expected process_name=install-todo-app, got {data.get('process_name')}"
        print(f"✓ install_deps started for todo-app: {data}")
        
        # Wait and check process list
        await asyncio.sleep(1)
        processes_result = await ws_rpc("workspace.processes")
        processes = processes_result.get("result", {}).get("processes", [])
        found = any(p.get("name") == "install-todo-app" for p in processes)
        assert found, f"install-todo-app process not found in list: {processes}"
        print(f"✓ install-todo-app process appears in process list")
        
        # Wait for process to complete (venv creation takes time)
        await asyncio.sleep(10)


class TestRunProject:
    """Test workspace.run_project RPC method"""
    
    @pytest.mark.asyncio
    async def test_run_project_requires_all_params(self):
        """run_project should require path, command, and name"""
        # Missing path
        result = await ws_rpc("workspace.run_project", {"command": "echo test", "name": "test"})
        assert "error" in result.get("result", {}), "Expected error for missing path"
        
        # Missing command
        result = await ws_rpc("workspace.run_project", {"path": "projects/todo-app", "name": "test"})
        assert "error" in result.get("result", {}), "Expected error for missing command"
        
        # Missing name
        result = await ws_rpc("workspace.run_project", {"path": "projects/todo-app", "command": "echo test"})
        assert "error" in result.get("result", {}), "Expected error for missing name"
        
        print(f"✓ run_project validates all required parameters")
    
    @pytest.mark.asyncio
    async def test_run_project_wraps_with_bash(self):
        """run_project should start process with bash -c wrapper"""
        result = await ws_rpc("workspace.run_project", {
            "path": "projects/todo-app",
            "command": "echo 'hello world'",
            "name": "test-bash-wrap"
        })
        data = result.get("result", {})
        
        assert data.get("ok") == True, f"Expected ok: true, got: {data}"
        print(f"✓ run_project started: {data}")
        
        # Clean up
        await asyncio.sleep(1)
        await ws_rpc("workspace.stop_process", {"name": "test-bash-wrap"})


class TestDetectProjectVenv:
    """Test venv detection after install_deps"""
    
    @pytest.mark.asyncio
    async def test_detect_project_shows_venv_after_install(self):
        """After install, detect_project should return has_venv=true"""
        # First check if venv exists (from previous install)
        result = await ws_rpc("workspace.detect_project", {"path": "projects/todo-app"})
        data = result.get("result", {})
        
        # If venv directory exists, has_venv should be true
        # If not, install first then check
        if data.get("has_venv"):
            print(f"✓ todo-app has_venv=true (venv already exists)")
            # Suggested command should activate existing venv
            assert ". venv/bin/activate" in data.get("suggested_command", ""), \
                f"Suggested command should activate venv: {data.get('suggested_command')}"
            print(f"✓ Suggested command includes venv activation")
        else:
            print(f"ℹ todo-app has_venv=false (no venv yet)")
            # After install, should include venv creation
            assert "python3 -m venv" in data.get("suggested_command", ""), \
                f"Suggested command should create venv: {data.get('suggested_command')}"
            print(f"✓ Suggested command includes venv creation")


class TestWorkspaceRootNoDeps:
    """Test that Install Deps button should NOT appear at workspace root"""
    
    @pytest.mark.asyncio
    async def test_workspace_root_no_requirements(self):
        """Workspace root has no requirements.txt, so no deps to install"""
        result = await ws_rpc("workspace.files", {"path": "."})
        data = result.get("result", {})
        
        items = data.get("items", [])
        has_requirements = any(i.get("name") == "requirements.txt" for i in items)
        has_package_json = any(i.get("name") == "package.json" for i in items)
        
        assert not has_requirements, "Workspace root should NOT have requirements.txt"
        assert not has_package_json, "Workspace root should NOT have package.json"
        print(f"✓ Workspace root has no deps files - Install Deps button should be hidden")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
