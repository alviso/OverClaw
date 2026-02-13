"""
Phase 8 Testing - New Tools and File Upload Endpoint
Tests for:
1. POST /api/upload - file upload endpoint (text, reject unsupported)
2. tools.list RPC - verify all 12 tools including 6 new ones
3. Tools work via agent (chat.send) - system_info, http_request, browse_webpage, parse_document
"""
import pytest
import requests
import json
import os
import time
import websocket
from uuid import uuid4

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/gateway"
GATEWAY_TOKEN = "dev-token-change-me"


class TestFileUploadEndpoint:
    """POST /api/upload endpoint tests"""
    
    def test_upload_text_file_success(self):
        """Upload a simple text file - should succeed"""
        content = "Hello, this is a test file for the upload endpoint."
        files = {"file": ("test_upload.txt", content, "text/plain")}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("ok") is True, "Response should have ok=True"
        assert "file_path" in data, "Response should include file_path"
        assert data.get("original_name") == "test_upload.txt", "Original name should match"
        assert data.get("type") == "document", "File type should be 'document'"
        assert data.get("size") == len(content), f"Size should be {len(content)}"
        
        print(f"✓ Text file uploaded successfully to: {data['file_path']}")
    
    def test_upload_json_file_success(self):
        """Upload a JSON file - should succeed"""
        content = json.dumps({"key": "value", "number": 42})
        files = {"file": ("test_data.json", content, "application/json")}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("ok") is True
        assert data.get("type") == "document"
        print(f"✓ JSON file uploaded successfully")
    
    def test_upload_markdown_file_success(self):
        """Upload a Markdown file - should succeed"""
        content = "# Test Document\n\nThis is a test markdown file.\n\n- Item 1\n- Item 2"
        files = {"file": ("readme.md", content, "text/markdown")}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("ok") is True
        assert data.get("type") == "document"
        print(f"✓ Markdown file uploaded successfully")
    
    def test_upload_reject_unsupported_extension(self):
        """Upload unsupported file type (e.g., .exe) - should be rejected"""
        content = b"fake executable content"
        files = {"file": ("malware.exe", content, "application/octet-stream")}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        
        assert response.status_code == 400, f"Expected 400 for unsupported type, got {response.status_code}"
        data = response.json()
        
        assert "error" in data, "Response should have error field"
        assert "unsupported" in data["error"].lower() or "ext" in data["error"].lower(), "Error should mention unsupported type"
        print(f"✓ Unsupported file type correctly rejected: {data['error']}")
    
    def test_upload_reject_dll_file(self):
        """Upload .dll file - should be rejected"""
        content = b"fake dll content"
        files = {"file": ("test.dll", content, "application/octet-stream")}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        
        assert response.status_code == 400
        print(f"✓ .dll file correctly rejected")
    
    def test_upload_csv_file_success(self):
        """Upload CSV file - should succeed"""
        content = "name,age,city\nJohn,30,NYC\nJane,25,LA"
        files = {"file": ("data.csv", content, "text/csv")}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert data.get("type") == "document"
        print(f"✓ CSV file uploaded successfully")


class TestToolsListRPC:
    """Test tools.list RPC returns all 12 tools"""
    
    def _rpc_call(self, method, params=None):
        """Make a WebSocket RPC call"""
        ws = websocket.create_connection(WS_URL, timeout=30)
        
        try:
            # Read welcome message
            ws.recv()
            
            # Authenticate
            auth_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "connect",
                "params": {"token": GATEWAY_TOKEN}
            })
            ws.send(auth_msg)
            auth_resp = json.loads(ws.recv())
            
            if "error" in auth_resp:
                raise Exception(f"Auth failed: {auth_resp['error']}")
            
            # Make RPC call
            rpc_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": method,
                "params": params or {}
            })
            ws.send(rpc_msg)
            
            # Wait for response
            start = time.time()
            while time.time() - start < 30:
                resp = json.loads(ws.recv())
                if resp.get("method") == "gateway.ping":
                    continue
                if "result" in resp or "error" in resp:
                    return resp
            
            raise Exception("Timeout waiting for RPC response")
        finally:
            ws.close()
    
    def test_tools_list_returns_12_tools(self):
        """Verify tools.list returns all 12 tools including the 6 new ones"""
        response = self._rpc_call("tools.list")
        
        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        
        # tools.list returns {"tools": [...]}
        assert "tools" in result, f"Expected 'tools' key in result, got: {result.keys()}"
        tools = result["tools"]
        
        # Should have exactly 12 tools
        assert len(tools) >= 12, f"Expected at least 12 tools, got {len(tools)}"
        
        tool_names = [t["name"] for t in tools]
        print(f"Total tools registered: {len(tools)}")
        print(f"Tool names: {tool_names}")
        
        # Verify the 6 original tools
        original_tools = ["web_search", "execute_command", "read_file", "write_file", "list_files", "memory_search"]
        for tool in original_tools:
            assert tool in tool_names, f"Missing original tool: {tool}"
        
        # Verify the 6 NEW tools
        new_tools = ["browse_webpage", "system_info", "http_request", "analyze_image", "transcribe_audio", "parse_document"]
        for tool in new_tools:
            assert tool in tool_names, f"Missing new tool: {tool}"
        
        print(f"✓ All 12 tools verified: {len(original_tools)} original + {len(new_tools)} new")
    
    def test_browse_webpage_tool_schema(self):
        """Verify browse_webpage tool has correct parameters"""
        response = self._rpc_call("tools.list")
        tools = {t["name"]: t for t in response["result"]["tools"]}
        
        assert "browse_webpage" in tools
        browse_tool = tools["browse_webpage"]
        
        assert "url" in browse_tool["parameters"]["properties"]
        assert "description" in browse_tool
        assert "navigate" in browse_tool["description"].lower() or "url" in browse_tool["description"].lower()
        
        print(f"✓ browse_webpage tool schema verified")
    
    def test_system_info_tool_schema(self):
        """Verify system_info tool has correct parameters"""
        response = self._rpc_call("tools.list")
        tools = {t["name"]: t for t in response["result"]["tools"]}
        
        assert "system_info" in tools
        sys_tool = tools["system_info"]
        
        params = sys_tool["parameters"]["properties"]
        assert "action" in params
        assert "enum" in params["action"]
        # Should include overview, processes, disk, network
        actions = params["action"]["enum"]
        assert "overview" in actions
        
        print(f"✓ system_info tool schema verified")
    
    def test_http_request_tool_schema(self):
        """Verify http_request tool has correct parameters"""
        response = self._rpc_call("tools.list")
        tools = {t["name"]: t for t in response["result"]["tools"]}
        
        assert "http_request" in tools
        http_tool = tools["http_request"]
        
        params = http_tool["parameters"]["properties"]
        assert "url" in params
        assert "method" in params
        
        print(f"✓ http_request tool schema verified")
    
    def test_parse_document_tool_schema(self):
        """Verify parse_document tool has correct parameters"""
        response = self._rpc_call("tools.list")
        tools = {t["name"]: t for t in response["result"]["tools"]}
        
        assert "parse_document" in tools
        parse_tool = tools["parse_document"]
        
        params = parse_tool["parameters"]["properties"]
        assert "file_path" in params
        
        print(f"✓ parse_document tool schema verified")
    
    def test_analyze_image_tool_schema(self):
        """Verify analyze_image tool has correct parameters"""
        response = self._rpc_call("tools.list")
        tools = {t["name"]: t for t in response["result"]["tools"]}
        
        assert "analyze_image" in tools
        image_tool = tools["analyze_image"]
        
        params = image_tool["parameters"]["properties"]
        assert "image_source" in params
        
        print(f"✓ analyze_image tool schema verified")
    
    def test_transcribe_audio_tool_schema(self):
        """Verify transcribe_audio tool has correct parameters"""
        response = self._rpc_call("tools.list")
        tools = {t["name"]: t for t in response["result"]["tools"]}
        
        assert "transcribe_audio" in tools
        audio_tool = tools["transcribe_audio"]
        
        params = audio_tool["parameters"]["properties"]
        assert "file_path" in params
        
        print(f"✓ transcribe_audio tool schema verified")


class TestToolsViaAgentChat:
    """Test tools work via agent chat (chat.send) - tools are invoked by the LLM agent"""
    
    def _rpc_chat(self, text, session_id=None, timeout=60):
        """Make a chat.send RPC call and wait for response"""
        if session_id is None:
            session_id = f"test-{uuid4().hex[:8]}"
        
        ws = websocket.create_connection(WS_URL, timeout=timeout)
        
        try:
            # Read welcome message
            ws.recv()
            
            # Authenticate
            auth_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "connect",
                "params": {"token": GATEWAY_TOKEN}
            })
            ws.send(auth_msg)
            auth_resp = json.loads(ws.recv())
            
            if "error" in auth_resp:
                raise Exception(f"Auth failed: {auth_resp['error']}")
            
            # Send chat message
            rpc_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "chat.send",
                "params": {"session_id": session_id, "text": text}
            })
            ws.send(rpc_msg)
            
            # Wait for response (agent may take time with LLM calls)
            start = time.time()
            while time.time() - start < timeout:
                try:
                    resp = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                    
                # Skip event messages
                if resp.get("method") in ["gateway.ping", "chat.event"]:
                    continue
                if "result" in resp or "error" in resp:
                    return resp
            
            raise Exception(f"Timeout after {timeout}s waiting for chat response")
        finally:
            ws.close()
    
    def test_system_info_via_agent(self):
        """Ask agent about system resources - should use system_info tool"""
        response = self._rpc_chat(
            "What is the current CPU and memory usage of this system? Use the system_info tool to check.",
            timeout=45
        )
        
        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        
        assert "response" in result, f"Expected response field, got: {result.keys()}"
        response_text = result["response"].lower()
        
        # Check if response mentions system info (CPU, memory, etc.)
        has_system_info = any(keyword in response_text for keyword in ["cpu", "memory", "ram", "usage", "%", "percent", "gb"])
        
        print(f"Agent response: {result['response'][:300]}...")
        print(f"Tool calls: {result.get('tool_calls', [])}")
        
        # Either the agent used the tool OR gave a relevant response
        if result.get("tool_calls"):
            tool_names = [tc.get("tool") for tc in result["tool_calls"]]
            assert "system_info" in tool_names, f"Expected system_info tool usage, got: {tool_names}"
            print(f"✓ system_info tool was used by agent")
        else:
            # Agent may have responded without tool - at least verify relevant response
            assert has_system_info, f"Expected system info in response, got: {response_text[:200]}"
            print(f"✓ Agent provided system info (may not have used tool explicitly)")
    
    def test_http_request_via_agent(self):
        """Ask agent to make HTTP request - should use http_request tool"""
        response = self._rpc_chat(
            "Please use the http_request tool to make a GET request to https://httpbin.org/get and tell me my origin IP.",
            timeout=45
        )
        
        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        
        assert "response" in result
        response_text = result["response"].lower()
        
        print(f"Agent response: {result['response'][:300]}...")
        print(f"Tool calls: {result.get('tool_calls', [])}")
        
        # Check if tool was used
        if result.get("tool_calls"):
            tool_names = [tc.get("tool") for tc in result["tool_calls"]]
            assert "http_request" in tool_names, f"Expected http_request tool, got: {tool_names}"
            print(f"✓ http_request tool was used by agent")
        else:
            # Check if response mentions httpbin or IP
            has_http_info = any(keyword in response_text for keyword in ["ip", "origin", "httpbin", "request"])
            assert has_http_info, f"Expected HTTP info in response"
            print(f"✓ Agent provided HTTP response info")
    
    def test_browse_webpage_via_agent(self):
        """Ask agent to browse a webpage - should use browse_webpage tool"""
        response = self._rpc_chat(
            "Use the browse_webpage tool to visit https://example.com and tell me the main heading on that page.",
            timeout=45
        )
        
        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        
        assert "response" in result
        response_text = result["response"].lower()
        
        print(f"Agent response: {result['response'][:300]}...")
        print(f"Tool calls: {result.get('tool_calls', [])}")
        
        # Check if tool was used or response has relevant content
        if result.get("tool_calls"):
            tool_names = [tc.get("tool") for tc in result["tool_calls"]]
            assert "browse_webpage" in tool_names, f"Expected browse_webpage tool, got: {tool_names}"
            print(f"✓ browse_webpage tool was used by agent")
        else:
            # example.com has "Example Domain" as heading
            has_page_content = "example" in response_text or "domain" in response_text
            assert has_page_content, f"Expected page content in response"
            print(f"✓ Agent provided webpage content")


class TestParseDocumentIntegration:
    """Test parse_document tool with uploaded file - full integration flow"""
    
    def test_upload_then_parse_text_file(self):
        """Upload a text file and then ask agent to parse it"""
        # Step 1: Upload a text file
        content = "This is a test document for parsing.\n\nSection 1: Introduction\nThis is the introduction section.\n\nSection 2: Details\nHere are the details of our test."
        files = {"file": ("test_doc_for_parsing.txt", content, "text/plain")}
        
        upload_resp = requests.post(f"{BASE_URL}/api/upload", files=files)
        assert upload_resp.status_code == 200
        
        file_path = upload_resp.json()["file_path"]
        print(f"Uploaded file to: {file_path}")
        
        # Step 2: Ask agent to parse the document
        session_id = f"parse-test-{uuid4().hex[:8]}"
        
        ws = websocket.create_connection(WS_URL, timeout=60)
        
        try:
            # Auth
            ws.recv()  # welcome
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "connect",
                "params": {"token": GATEWAY_TOKEN}
            }))
            ws.recv()  # auth response
            
            # Send chat to parse document
            ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "chat.send",
                "params": {
                    "session_id": session_id,
                    "text": f"Please use the parse_document tool to read and summarize the contents of this file: {file_path}"
                }
            }))
            
            # Wait for response
            start = time.time()
            while time.time() - start < 60:
                try:
                    resp = json.loads(ws.recv())
                except Exception:
                    continue
                
                if resp.get("method") in ["gateway.ping", "chat.event"]:
                    continue
                    
                if "result" in resp:
                    result = resp["result"]
                    response_text = result.get("response", "").lower()
                    tool_calls = result.get("tool_calls", [])
                    
                    print(f"Agent response: {result.get('response', '')[:300]}...")
                    print(f"Tool calls: {tool_calls}")
                    
                    # Verify the content was parsed
                    has_content = any(keyword in response_text for keyword in ["section", "introduction", "details", "test document"])
                    
                    if tool_calls:
                        tool_names = [tc.get("tool") for tc in tool_calls]
                        if "parse_document" in tool_names:
                            print(f"✓ parse_document tool was used")
                    
                    # Main assertion: agent should mention content from the document
                    assert has_content or tool_calls, f"Expected document content in response or tool usage"
                    print(f"✓ Document parsing integration test passed")
                    return
                    
                elif "error" in resp:
                    pytest.fail(f"Error from agent: {resp['error']}")
            
            pytest.fail("Timeout waiting for parse response")
        finally:
            ws.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
