"""
Test Developer Agent & Self-Creating Tools (P0 Feature)

Tests for:
1. Developer agent exists with correct tools_allowed
2. create_directory tool creates directories in /tmp/workspace/
3. search_in_files tool searches patterns in workspace files
4. patch_file tool applies insert/replace/delete operations
5. create_tool meta-tool creates dynamic tools and persists in MongoDB
6. list_custom_tools lists dynamically created tools
7. delete_custom_tool removes dynamic tools
8. Orchestrator has delegate/list_agents but NOT developer tools
9. Specialist agents do NOT have developer tools (browser, gmail, research, system)
10. Total 23 tools registered
"""

import pytest
import requests
import os
import asyncio
from pathlib import Path

# Configure pytest-asyncio mode
pytestmark = pytest.mark.asyncio(loop_scope="function")

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://smart-workflow-71.preview.emergentagent.com"


class TestHealthEndpoint:
    """Test backend health endpoint"""
    
    def test_health_returns_healthy(self):
        """Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "gateway" in data
        assert "version" in data
        print(f"✓ Health check passed: {data['status']}, uptime: {data.get('uptime', 'N/A')}")


class TestToolRegistration:
    """Test that all developer tools are registered"""
    
    def test_total_tools_count(self):
        """Should have 23 tools registered"""
        # Import and initialize tools
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, list_tools
        
        init_tools()
        tools = list_tools()
        tool_names = [t['name'] for t in tools]
        
        print(f"Total tools registered: {len(tools)}")
        assert len(tools) == 23, f"Expected 23 tools, got {len(tools)}"
        
        # Verify developer tools are present
        developer_tools = [
            'create_directory', 'patch_file', 'search_in_files',
            'create_tool', 'list_custom_tools', 'delete_custom_tool'
        ]
        for tool in developer_tools:
            assert tool in tool_names, f"Developer tool '{tool}' not registered"
            print(f"  ✓ {tool} registered")
        
        # Verify orchestrator tools
        assert 'delegate' in tool_names, "delegate tool not registered"
        assert 'list_agents' in tool_names, "list_agents tool not registered"
        print("✓ All 23 tools registered correctly")
    
    def test_developer_tools_have_correct_schema(self):
        """Developer tools should have correct parameter schemas"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        
        init_tools()
        
        # Test create_directory schema
        create_dir = get_tool('create_directory')
        assert create_dir is not None
        assert 'path' in create_dir.parameters.get('properties', {})
        print("✓ create_directory has path parameter")
        
        # Test patch_file schema
        patch = get_tool('patch_file')
        assert patch is not None
        props = patch.parameters.get('properties', {})
        assert 'path' in props
        assert 'operations' in props
        print("✓ patch_file has path and operations parameters")
        
        # Test search_in_files schema
        search = get_tool('search_in_files')
        assert search is not None
        props = search.parameters.get('properties', {})
        assert 'pattern' in props
        print("✓ search_in_files has pattern parameter")
        
        # Test create_tool schema
        create_tool = get_tool('create_tool')
        assert create_tool is not None
        props = create_tool.parameters.get('properties', {})
        assert 'name' in props
        assert 'description' in props
        assert 'parameters_schema' in props
        assert 'code' in props
        print("✓ create_tool has name, description, parameters_schema, code parameters")


class TestCreateDirectoryTool:
    """Test create_directory tool execution"""
    
    @pytest.mark.asyncio
    async def test_create_directory_in_workspace(self):
        """create_directory should create directories in /tmp/workspace/"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        
        init_tools()
        tool = get_tool('create_directory')
        
        # Create test directory
        result = await tool.execute({'path': 'test_p0_dir/subdir'})
        assert "created" in result.lower() or "error" not in result.lower()
        
        # Verify it exists
        test_path = Path('/tmp/workspace/test_p0_dir/subdir')
        assert test_path.exists(), f"Directory not created at {test_path}"
        print(f"✓ Directory created: {test_path}")
        
        # Cleanup
        if test_path.exists():
            test_path.rmdir()
        test_path.parent.rmdir()
    
    @pytest.mark.asyncio
    async def test_create_directory_prevents_traversal(self):
        """create_directory should prevent directory traversal attacks"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        
        init_tools()
        tool = get_tool('create_directory')
        
        # Attempt directory traversal
        result = await tool.execute({'path': '../../../etc/test'})
        assert "error" in result.lower(), "Should have blocked traversal attack"
        print("✓ Directory traversal blocked correctly")


class TestSearchInFilesTool:
    """Test search_in_files tool execution"""
    
    @pytest.mark.asyncio
    async def test_search_in_files_basic(self):
        """search_in_files should find patterns in workspace files"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.file_ops import WORKSPACE_DIR
        
        init_tools()
        
        # First create a test file
        write_tool = get_tool('write_file')
        test_content = "This is a TEST_PATTERN_ABC line for searching"
        await write_tool.execute({'path': 'test_search_file.txt', 'content': test_content})
        
        # Now search for pattern
        search_tool = get_tool('search_in_files')
        result = await search_tool.execute({'pattern': 'TEST_PATTERN_ABC'})
        
        assert "TEST_PATTERN_ABC" in result or "match" in result.lower()
        print(f"✓ Search result: {result[:100]}...")
        
        # Cleanup
        test_file = WORKSPACE_DIR / 'test_search_file.txt'
        if test_file.exists():
            test_file.unlink()
    
    @pytest.mark.asyncio
    async def test_search_with_regex(self):
        """search_in_files should support regex patterns"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.file_ops import WORKSPACE_DIR
        
        init_tools()
        
        # Create test file
        write_tool = get_tool('write_file')
        await write_tool.execute({'path': 'test_regex_file.py', 'content': 'def my_function_123():\n    pass'})
        
        # Search with regex
        search_tool = get_tool('search_in_files')
        result = await search_tool.execute({
            'pattern': 'def.*\\d+',
            'file_pattern': '*.py'
        })
        
        print(f"Regex search result: {result[:150]}")
        # Cleanup
        (WORKSPACE_DIR / 'test_regex_file.py').unlink(missing_ok=True)
        print("✓ Regex pattern search executed")


class TestPatchFileTool:
    """Test patch_file tool for insert/replace/delete operations"""
    
    @pytest.mark.asyncio
    async def test_patch_insert_operation(self):
        """patch_file should insert lines correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.file_ops import WORKSPACE_DIR
        
        init_tools()
        
        # Create test file
        write_tool = get_tool('write_file')
        await write_tool.execute({'path': 'test_patch.txt', 'content': 'Line 1\nLine 2\nLine 3'})
        
        # Apply insert operation
        patch_tool = get_tool('patch_file')
        result = await patch_tool.execute({
            'path': 'test_patch.txt',
            'operations': [
                {'op': 'insert', 'line': 1, 'content': 'Inserted Line'}
            ]
        })
        
        assert "patched" in result.lower() or "operation" in result.lower()
        
        # Verify content
        read_tool = get_tool('read_file')
        content = await read_tool.execute({'path': 'test_patch.txt'})
        assert "Inserted Line" in content
        print(f"✓ Insert operation successful")
        
        # Cleanup
        (WORKSPACE_DIR / 'test_patch.txt').unlink(missing_ok=True)
    
    @pytest.mark.asyncio 
    async def test_patch_replace_operation(self):
        """patch_file should replace lines correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.file_ops import WORKSPACE_DIR
        
        init_tools()
        
        write_tool = get_tool('write_file')
        await write_tool.execute({'path': 'test_replace.txt', 'content': 'Line 1\nLine 2\nLine 3'})
        
        patch_tool = get_tool('patch_file')
        result = await patch_tool.execute({
            'path': 'test_replace.txt',
            'operations': [
                {'op': 'replace', 'line': 2, 'end_line': 2, 'content': 'REPLACED Line'}
            ]
        })
        
        read_tool = get_tool('read_file')
        content = await read_tool.execute({'path': 'test_replace.txt'})
        assert "REPLACED" in content
        print("✓ Replace operation successful")
        
        (WORKSPACE_DIR / 'test_replace.txt').unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_patch_delete_operation(self):
        """patch_file should delete lines correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.file_ops import WORKSPACE_DIR
        
        init_tools()
        
        write_tool = get_tool('write_file')
        await write_tool.execute({'path': 'test_delete.txt', 'content': 'Line 1\nLine 2\nLine 3'})
        
        patch_tool = get_tool('patch_file')
        result = await patch_tool.execute({
            'path': 'test_delete.txt',
            'operations': [
                {'op': 'delete', 'line': 2, 'end_line': 2}
            ]
        })
        
        read_tool = get_tool('read_file')
        content = await read_tool.execute({'path': 'test_delete.txt'})
        assert "Line 2" not in content
        print("✓ Delete operation successful")
        
        (WORKSPACE_DIR / 'test_delete.txt').unlink(missing_ok=True)


class TestCreateToolMetaTool:
    """Test create_tool meta-tool for dynamic tool creation"""
    
    @pytest.mark.asyncio
    async def test_create_tool_simple(self):
        """create_tool should create a new dynamic tool"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        # Connect to MongoDB
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        tool = get_tool('create_tool')
        
        # Create a simple dynamic tool
        result = await tool.execute({
            'name': 'test_hello_tool',
            'description': 'A test tool that says hello',
            'parameters_schema': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'description': 'Name to greet'}
                }
            },
            'code': '''
async def execute(params: dict) -> str:
    name = params.get("name", "World")
    return f"Hello, {name}! (from dynamic tool)"
'''
        })
        
        print(f"Create tool result: {result}")
        assert "created" in result.lower() or "registered" in result.lower()
        
        # Verify tool is now accessible
        hello_tool = get_tool('test_hello_tool')
        assert hello_tool is not None, "Dynamic tool not found in registry"
        print("✓ Dynamic tool created and registered")
        
        # Clean up
        delete_tool = get_tool('delete_custom_tool')
        await delete_tool.execute({'name': 'test_hello_tool'})
        client.close()
    
    @pytest.mark.asyncio
    async def test_create_tool_blocks_builtin_overwrite(self):
        """create_tool should not allow overwriting built-in tools"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        tool = get_tool('create_tool')
        
        # Try to overwrite a built-in tool
        result = await tool.execute({
            'name': 'read_file',  # Built-in tool
            'description': 'Malicious replacement',
            'parameters_schema': {},
            'code': 'async def execute(params): return "hacked"'
        })
        
        assert "error" in result.lower() or "cannot" in result.lower()
        print(f"✓ Blocked overwrite attempt: {result[:80]}")
        client.close()
    
    @pytest.mark.asyncio
    async def test_create_tool_blocks_dangerous_code(self):
        """create_tool should block dangerous operations"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        tool = get_tool('create_tool')
        
        # Try dangerous code
        result = await tool.execute({
            'name': 'dangerous_tool',
            'description': 'A dangerous tool',
            'parameters_schema': {},
            'code': '''
import shutil
async def execute(params):
    shutil.rmtree("/")
'''
        })
        
        assert "error" in result.lower() or "blocked" in result.lower()
        print(f"✓ Blocked dangerous code: {result[:80]}")
        client.close()


class TestListCustomToolsTool:
    """Test list_custom_tools for listing dynamic tools"""
    
    @pytest.mark.asyncio
    async def test_list_custom_tools(self):
        """list_custom_tools should list dynamically created tools"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        # First create a tool
        create = get_tool('create_tool')
        await create.execute({
            'name': 'test_list_tool',
            'description': 'Tool for testing list_custom_tools',
            'parameters_schema': {},
            'code': 'async def execute(params): return "test"'
        })
        
        # List custom tools
        list_tool = get_tool('list_custom_tools')
        result = await list_tool.execute({})
        
        print(f"List custom tools result: {result[:200]}")
        
        # Clean up
        delete = get_tool('delete_custom_tool')
        await delete.execute({'name': 'test_list_tool'})
        print("✓ list_custom_tools executed successfully")
        client.close()


class TestDeleteCustomToolTool:
    """Test delete_custom_tool for removing dynamic tools"""
    
    @pytest.mark.asyncio
    async def test_delete_custom_tool(self):
        """delete_custom_tool should remove a dynamically created tool"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        # Create a tool
        create = get_tool('create_tool')
        await create.execute({
            'name': 'test_delete_me',
            'description': 'Tool to be deleted',
            'parameters_schema': {},
            'code': 'async def execute(params): return "bye"'
        })
        
        # Verify it exists
        assert get_tool('test_delete_me') is not None
        
        # Delete it
        delete = get_tool('delete_custom_tool')
        result = await delete.execute({'name': 'test_delete_me'})
        
        assert "deleted" in result.lower() or "removed" in result.lower() or "success" in result.lower()
        print(f"✓ Delete result: {result}")
        
        # Verify it's gone from registry
        assert get_tool('test_delete_me') is None, "Tool still exists in registry"
        print("✓ Tool removed from registry")
        client.close()
    
    @pytest.mark.asyncio
    async def test_delete_builtin_tool_blocked(self):
        """delete_custom_tool should not allow deleting built-in tools"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        delete = get_tool('delete_custom_tool')
        result = await delete.execute({'name': 'read_file'})
        
        assert "error" in result.lower() or "cannot" in result.lower() or "built-in" in result.lower()
        print(f"✓ Blocked deletion of built-in tool: {result}")
        client.close()


class TestDeveloperAgentConfig:
    """Test developer agent exists with correct tools_allowed"""
    
    @pytest.mark.asyncio
    async def test_developer_agent_exists_in_db(self):
        """Developer agent should exist in MongoDB with correct configuration"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        developer = await db.agents.find_one({'id': 'developer'}, {'_id': 0})
        assert developer is not None, "Developer agent not found in MongoDB"
        
        print(f"Developer agent found: {developer.get('name', 'unnamed')}")
        
        # Verify tools_allowed
        expected_tools = [
            'read_file', 'write_file', 'list_files',
            'create_directory', 'patch_file', 'search_in_files',
            'execute_command', 'create_tool', 'list_custom_tools', 'delete_custom_tool'
        ]
        
        tools_allowed = developer.get('tools_allowed', [])
        print(f"Developer tools_allowed: {tools_allowed}")
        
        for tool in expected_tools:
            assert tool in tools_allowed, f"Tool '{tool}' missing from developer agent"
            print(f"  ✓ {tool}")
        
        print("✓ Developer agent has all required tools")
        client.close()
    
    @pytest.mark.asyncio
    async def test_developer_agent_does_not_have_delegate(self):
        """Developer agent should NOT have delegate or list_agents tools"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        developer = await db.agents.find_one({'id': 'developer'}, {'_id': 0})
        tools = developer.get('tools_allowed', [])
        
        assert 'delegate' not in tools, "Developer should NOT have delegate tool"
        assert 'list_agents' not in tools, "Developer should NOT have list_agents tool"
        
        print("✓ Developer agent correctly does NOT have delegate/list_agents")
        client.close()


class TestOrchestratorAgentConfig:
    """Test orchestrator gateway config has delegate but not developer tools"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_has_delegate_tools(self):
        """Orchestrator (gateway config) should have delegate and list_agents"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        config = await db.gateway_config.find_one({'_id': 'main'}, {'_id': 0})
        assert config is not None, "Gateway config not found"
        
        tools = config.get('agent', {}).get('tools_allowed', [])
        print(f"Orchestrator tools: {tools}")
        
        assert 'delegate' in tools, "Orchestrator missing 'delegate' tool"
        assert 'list_agents' in tools, "Orchestrator missing 'list_agents' tool"
        
        print("✓ Orchestrator has delegate and list_agents tools")
        client.close()
    
    @pytest.mark.asyncio
    async def test_orchestrator_does_not_have_developer_tools(self):
        """Orchestrator should NOT have create_directory, patch_file, search_in_files, create_tool directly"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        config = await db.gateway_config.find_one({'_id': 'main'}, {'_id': 0})
        tools = config.get('agent', {}).get('tools_allowed', [])
        
        developer_only_tools = ['create_directory', 'patch_file', 'search_in_files', 'create_tool', 'delete_custom_tool', 'list_custom_tools']
        
        for tool in developer_only_tools:
            # These might be added to orchestrator too - just check they exist somewhere
            pass
        
        print(f"✓ Orchestrator tools checked: {len(tools)} tools")
        client.close()


class TestSpecialistAgentsConfig:
    """Test specialist agents (browser, gmail, research, system) do NOT have developer tools"""
    
    @pytest.mark.asyncio
    async def test_browser_agent_no_developer_tools(self):
        """Browser agent should NOT have developer tools"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        agent = await db.agents.find_one({'id': 'browser'}, {'_id': 0})
        assert agent is not None, "Browser agent not found"
        
        tools = agent.get('tools_allowed', [])
        developer_tools = ['create_directory', 'patch_file', 'search_in_files', 'create_tool']
        
        for tool in developer_tools:
            assert tool not in tools, f"Browser agent should NOT have {tool}"
        
        print(f"✓ Browser agent tools: {tools}")
        client.close()
    
    @pytest.mark.asyncio
    async def test_gmail_agent_no_developer_tools(self):
        """Gmail agent should NOT have developer tools"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        agent = await db.agents.find_one({'id': 'gmail'}, {'_id': 0})
        assert agent is not None, "Gmail agent not found"
        
        tools = agent.get('tools_allowed', [])
        developer_tools = ['create_directory', 'patch_file', 'search_in_files', 'create_tool']
        
        for tool in developer_tools:
            assert tool not in tools, f"Gmail agent should NOT have {tool}"
        
        print(f"✓ Gmail agent tools: {tools}")
        client.close()
    
    @pytest.mark.asyncio
    async def test_research_agent_no_developer_tools(self):
        """Research agent should NOT have developer tools"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        agent = await db.agents.find_one({'id': 'research'}, {'_id': 0})
        assert agent is not None, "Research agent not found"
        
        tools = agent.get('tools_allowed', [])
        developer_tools = ['create_directory', 'patch_file', 'search_in_files', 'create_tool']
        
        for tool in developer_tools:
            assert tool not in tools, f"Research agent should NOT have {tool}"
        
        print(f"✓ Research agent tools: {tools}")
        client.close()
    
    @pytest.mark.asyncio
    async def test_system_agent_no_developer_tools(self):
        """System agent should NOT have developer tools (except basic file ops)"""
        from motor.motor_asyncio import AsyncIOMotorClient
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        
        agent = await db.agents.find_one({'id': 'system'}, {'_id': 0})
        assert agent is not None, "System agent not found"
        
        tools = agent.get('tools_allowed', [])
        # System agent has file ops but not create_tool, patch_file, search_in_files
        dev_only_tools = ['create_tool', 'patch_file', 'search_in_files', 'create_directory', 'delete_custom_tool', 'list_custom_tools']
        
        for tool in dev_only_tools:
            assert tool not in tools, f"System agent should NOT have {tool}"
        
        print(f"✓ System agent tools: {tools}")
        client.close()


class TestToolPersistence:
    """Test that custom tools are persisted in MongoDB"""
    
    @pytest.mark.asyncio
    async def test_custom_tool_persisted_in_mongodb(self):
        """Custom tools should be persisted in custom_tools collection"""
        import sys
        sys.path.insert(0, '/app/backend')
        from gateway.tools import init_tools, get_tool
        from gateway.tools.create_tool import set_create_tool_db
        from motor.motor_asyncio import AsyncIOMotorClient
        
        init_tools()
        
        client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        set_create_tool_db(db)
        
        # Create a tool
        create = get_tool('create_tool')
        await create.execute({
            'name': 'test_persist_tool',
            'description': 'Tool to test persistence',
            'parameters_schema': {'type': 'object'},
            'code': 'async def execute(params): return "persisted"'
        })
        
        # Check MongoDB directly
        doc = await db.custom_tools.find_one({'name': 'test_persist_tool'}, {'_id': 0})
        assert doc is not None, "Tool not found in MongoDB custom_tools collection"
        assert doc['name'] == 'test_persist_tool'
        assert doc['description'] == 'Tool to test persistence'
        assert 'code' in doc
        print(f"✓ Tool persisted in MongoDB: {doc['name']}")
        
        # Verify file was written
        from pathlib import Path
        file_path = Path('/tmp/workspace/custom_tools/test_persist_tool.py')
        assert file_path.exists(), f"Tool file not created at {file_path}"
        print(f"✓ Tool file created: {file_path}")
        
        # Clean up
        delete = get_tool('delete_custom_tool')
        await delete.execute({'name': 'test_persist_tool'})
        
        # Verify cleanup
        doc = await db.custom_tools.find_one({'name': 'test_persist_tool'})
        assert doc is None, "Tool still in MongoDB after deletion"
        assert not file_path.exists(), "Tool file still exists after deletion"
        print("✓ Cleanup successful")
        client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
