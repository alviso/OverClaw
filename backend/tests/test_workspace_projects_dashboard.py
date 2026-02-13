"""
Test suite for workspace.projects RPC endpoint and Project Dashboard features
Tests the new Project Dashboard redesign including:
- workspace.projects returns list with all project metadata
- Live status cross-referencing with running processes
"""

import pytest
import os
import asyncio
import sys

# Add backend to path
sys.path.insert(0, '/app/backend')

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWorkspaceProjectsEndpoint:
    """Test workspace.projects RPC endpoint"""
    
    def test_workspace_projects_returns_list(self):
        """Test that workspace.projects returns projects list"""
        import asyncio
        from gateway.methods import handle_workspace_projects
        from unittest.mock import AsyncMock, MagicMock
        
        async def run_test():
            ctx = MagicMock()
            ctx.db = AsyncMock()
            result = await handle_workspace_projects({}, None, ctx)
            return result
        
        result = asyncio.run(run_test())
        
        assert "projects" in result, "Response should have 'projects' key"
        assert isinstance(result["projects"], list), "projects should be a list"
        print(f"Found {len(result['projects'])} projects")
    
    def test_workspace_projects_has_expected_fields(self):
        """Test that each project has all expected fields"""
        import asyncio
        from gateway.methods import handle_workspace_projects
        from unittest.mock import AsyncMock, MagicMock
        
        async def run_test():
            ctx = MagicMock()
            ctx.db = AsyncMock()
            result = await handle_workspace_projects({}, None, ctx)
            return result
        
        result = asyncio.run(run_test())
        
        expected_fields = [
            "name",
            "path",
            "project_type",
            "entry_point",
            "has_deps",
            "has_venv",
            "status",
            "process",
            "port",
            "last_modified",
            "file_count"
        ]
        
        for project in result["projects"]:
            for field in expected_fields:
                assert field in project, f"Project should have '{field}' field"
            print(f"Project {project['name']}: type={project['project_type']}, status={project['status']}")
    
    def test_workspace_projects_correct_project_types(self):
        """Test that project types are correctly detected"""
        import asyncio
        from gateway.methods import handle_workspace_projects
        from unittest.mock import AsyncMock, MagicMock
        
        async def run_test():
            ctx = MagicMock()
            ctx.db = AsyncMock()
            result = await handle_workspace_projects({}, None, ctx)
            return result
        
        result = asyncio.run(run_test())
        
        for project in result["projects"]:
            assert project["project_type"] in ["python", "node", None], \
                f"Project type should be 'python', 'node', or None, got {project['project_type']}"
            
            # For projects in our test workspace
            if project["name"] in ["demo-app", "todo-app"]:
                assert project["project_type"] == "python", \
                    f"{project['name']} should be detected as Python project"
    
    def test_workspace_projects_todo_app_has_venv(self):
        """Test that todo-app (with venv) is correctly detected"""
        import asyncio
        from gateway.methods import handle_workspace_projects
        from unittest.mock import AsyncMock, MagicMock
        
        async def run_test():
            ctx = MagicMock()
            ctx.db = AsyncMock()
            result = await handle_workspace_projects({}, None, ctx)
            return result
        
        result = asyncio.run(run_test())
        
        todo_app = next((p for p in result["projects"] if p["name"] == "todo-app"), None)
        assert todo_app is not None, "todo-app should exist"
        assert todo_app["has_venv"] == True, "todo-app should have venv"
        assert todo_app["has_deps"] == True, "todo-app should have deps (requirements.txt)"
        assert todo_app["entry_point"] == "app.py", "todo-app entry point should be app.py"
    
    def test_workspace_projects_demo_app_no_venv(self):
        """Test that demo-app (without venv) is correctly detected"""
        import asyncio
        from gateway.methods import handle_workspace_projects
        from unittest.mock import AsyncMock, MagicMock
        
        async def run_test():
            ctx = MagicMock()
            ctx.db = AsyncMock()
            result = await handle_workspace_projects({}, None, ctx)
            return result
        
        result = asyncio.run(run_test())
        
        demo_app = next((p for p in result["projects"] if p["name"] == "demo-app"), None)
        assert demo_app is not None, "demo-app should exist"
        assert demo_app["has_venv"] == False, "demo-app should NOT have venv"
        assert demo_app["entry_point"] == "app.py", "demo-app entry point should be app.py"


class TestWorkspaceRunProject:
    """Test workspace.run_project and workspace.stop_process"""
    
    def test_run_project_endpoint_exists(self):
        """Test that workspace.run_project method is registered"""
        from gateway.methods import get_method
        
        method = get_method("workspace.run_project")
        assert method is not None, "workspace.run_project should be registered"
    
    def test_stop_process_endpoint_exists(self):
        """Test that workspace.stop_process method is registered"""
        from gateway.methods import get_method
        
        method = get_method("workspace.stop_process")
        assert method is not None, "workspace.stop_process should be registered"
    
    def test_detect_project_endpoint_exists(self):
        """Test that workspace.detect_project method is registered"""
        from gateway.methods import get_method
        
        method = get_method("workspace.detect_project")
        assert method is not None, "workspace.detect_project should be registered"


class TestWorkspaceProjectsLiveStatus:
    """Test live status cross-referencing with running processes"""
    
    def test_project_status_stopped_when_no_process(self):
        """Test that projects show 'stopped' when no process running"""
        import asyncio
        from gateway.methods import handle_workspace_projects
        from unittest.mock import AsyncMock, MagicMock
        
        async def run_test():
            ctx = MagicMock()
            ctx.db = AsyncMock()
            result = await handle_workspace_projects({}, None, ctx)
            return result
        
        result = asyncio.run(run_test())
        
        for project in result["projects"]:
            # If no process is running
            if project["process"] is None:
                assert project["status"] == "stopped", \
                    f"Project without process should have status 'stopped', got '{project['status']}'"
                assert project["port"] is None, \
                    "Project without process should have port None"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
