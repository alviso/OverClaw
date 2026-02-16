"""
Phase 8 Tests - Task Scheduler, Notifications, and Monitor Tool
Tests for:
- tasks.create, tasks.list, tasks.pause, tasks.resume, tasks.delete, tasks.run_now, tasks.history
- notifications.list, notifications.mark_read, notifications.clear
- monitor_url tool registration
"""
import pytest
import json
import os
import time
import websocket
from uuid import uuid4

# Use public URL for testing - WS connection uses local to avoid timeout
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://overclaw-preview.preview.emergentagent.com").rstrip("/")
WS_URL = "ws://localhost:8001/api/gateway"  # Use localhost for WS to avoid 60s timeout
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "dev-token-change-me")


class WebSocketRPCClient:
    """Helper class for WebSocket RPC calls"""
    
    def __init__(self, url=WS_URL, token=GATEWAY_TOKEN, timeout=30):
        self.url = url
        self.token = token
        self.timeout = timeout
        self.ws = None
    
    def connect(self):
        """Establish WebSocket connection and authenticate"""
        self.ws = websocket.create_connection(self.url, timeout=self.timeout)
        
        # Read welcome message
        welcome = json.loads(self.ws.recv())
        assert welcome.get("method") == "gateway.welcome", f"Expected welcome, got: {welcome}"
        
        # Authenticate using "connect" method
        auth_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "connect",
            "params": {"token": self.token}
        })
        self.ws.send(auth_msg)
        auth_resp = json.loads(self.ws.recv())
        
        if "error" in auth_resp:
            raise Exception(f"Auth failed: {auth_resp['error']}")
        
        return self
    
    def close(self):
        """Close WebSocket connection"""
        if self.ws:
            self.ws.close()
    
    def call(self, method: str, params: dict = None, timeout: int = None):
        """Make an RPC call and return the result"""
        if not self.ws:
            raise Exception("WebSocket not connected")
        
        request_id = str(uuid4())
        rpc_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        })
        self.ws.send(rpc_msg)
        
        # Wait for response with matching ID
        wait_timeout = timeout or self.timeout
        start = time.time()
        while time.time() - start < wait_timeout:
            try:
                resp = json.loads(self.ws.recv())
            except Exception:
                continue
            
            # Skip event messages
            if resp.get("method") in ["gateway.ping", "chat.event", "notification.new"]:
                continue
            
            # Check if this is our response
            if resp.get("id") == request_id:
                if "error" in resp:
                    return {"error": resp["error"]}
                return resp.get("result", {})
        
        raise Exception(f"Timeout waiting for response to {method}")


class TestTaskSchedulerRPC:
    """Tests for tasks.* RPC methods"""
    
    @pytest.fixture(autouse=True)
    def setup_ws(self):
        """Setup WebSocket connection for each test"""
        self.client = WebSocketRPCClient().connect()
        yield
        self.client.close()
    
    def test_tasks_list(self):
        """Test that tasks.list returns tasks array"""
        result = self.client.call("tasks.list")
        
        assert "tasks" in result, f"Expected 'tasks' key in result: {result}"
        assert isinstance(result["tasks"], list), "tasks should be a list"
        assert "count" in result, "Expected 'count' key in result"
        
        print(f"tasks.list returned {result.get('count')} tasks")
    
    def test_tasks_create(self):
        """Test creating a scheduled task with all parameters"""
        task_params = {
            "name": "TEST_Phase8_Monitor_Task",
            "prompt": "Check the current time and report it",
            "interval_seconds": 120,
            "agent_id": "default",
            "notify": "on_change"
        }
        result = self.client.call("tasks.create", task_params)
        
        assert result.get("ok") == True, f"Expected ok=True: {result}"
        assert "task" in result, f"Expected 'task' in result: {result}"
        
        task = result["task"]
        assert task["name"] == task_params["name"], "Task name mismatch"
        assert task["prompt"] == task_params["prompt"], "Task prompt mismatch"
        assert task["interval_seconds"] >= 10, "Interval should be at least 10s"
        assert task["agent_id"] == task_params["agent_id"], "Agent ID mismatch"
        assert task["notify"] == task_params["notify"], "Notify mode mismatch"
        assert task["enabled"] == True, "Task should be enabled by default"
        assert "id" in task, "Task should have an ID"
        
        print(f"Created task: {task['id']}")
        
        # Cleanup
        self.client.call("tasks.delete", {"id": task["id"]})
    
    def test_tasks_crud_flow(self):
        """Test full CRUD flow: create, list, pause, resume, delete"""
        # CREATE
        task_params = {
            "name": "TEST_CRUD_Task",
            "prompt": "Say hello",
            "interval_seconds": 60,
            "agent_id": "default",
            "notify": "never"
        }
        create_result = self.client.call("tasks.create", task_params)
        assert create_result.get("ok") == True, f"Create failed: {create_result}"
        task_id = create_result["task"]["id"]
        print(f"Created task: {task_id}")
        
        # LIST - verify task appears
        list_result = self.client.call("tasks.list")
        task_ids = [t["id"] for t in list_result.get("tasks", [])]
        assert task_id in task_ids, f"Created task not in list: {task_ids}"
        print(f"Task {task_id} found in list")
        
        # PAUSE
        pause_result = self.client.call("tasks.pause", {"id": task_id})
        assert pause_result.get("ok") == True, f"Pause failed: {pause_result}"
        print(f"Paused task: {task_id}")
        
        # Verify paused state
        list_result = self.client.call("tasks.list")
        task = next((t for t in list_result.get("tasks", []) if t["id"] == task_id), None)
        assert task is not None, "Task not found after pause"
        assert task["enabled"] == False, "Task should be disabled after pause"
        
        # RESUME
        resume_result = self.client.call("tasks.resume", {"id": task_id})
        assert resume_result.get("ok") == True, f"Resume failed: {resume_result}"
        print(f"Resumed task: {task_id}")
        
        # Verify resumed state
        list_result = self.client.call("tasks.list")
        task = next((t for t in list_result.get("tasks", []) if t["id"] == task_id), None)
        assert task is not None, "Task not found after resume"
        assert task["enabled"] == True, "Task should be enabled after resume"
        
        # DELETE
        delete_result = self.client.call("tasks.delete", {"id": task_id})
        assert delete_result.get("ok") == True, f"Delete failed: {delete_result}"
        print(f"Deleted task: {task_id}")
        
        # Verify deleted
        list_result = self.client.call("tasks.list")
        task_ids = [t["id"] for t in list_result.get("tasks", [])]
        assert task_id not in task_ids, f"Task still in list after delete"
        print("CRUD flow completed successfully")
    
    def test_tasks_run_now(self):
        """Test triggering immediate task execution"""
        # Create a simple task
        task_params = {
            "name": "TEST_RunNow_Task",
            "prompt": "What is 2 + 2?",
            "interval_seconds": 3600,  # 1 hour - won't run naturally
            "agent_id": "default",
            "notify": "never"
        }
        create_result = self.client.call("tasks.create", task_params)
        assert create_result.get("ok") == True, f"Create failed: {create_result}"
        task_id = create_result["task"]["id"]
        
        # Trigger immediate run
        run_result = self.client.call("tasks.run_now", {"id": task_id})
        assert run_result.get("ok") == True, f"run_now failed: {run_result}"
        print(f"Triggered immediate run for task: {task_id}")
        
        # Note: We don't wait for execution since it calls real LLM
        # Just verify the API accepted the request
        
        # Cleanup
        self.client.call("tasks.delete", {"id": task_id})
    
    def test_tasks_history(self):
        """Test retrieving task execution history"""
        # Create a task
        task_params = {
            "name": "TEST_History_Task",
            "prompt": "Hello",
            "interval_seconds": 60,
            "agent_id": "default",
            "notify": "never"
        }
        create_result = self.client.call("tasks.create", task_params)
        assert create_result.get("ok") == True
        task_id = create_result["task"]["id"]
        
        # Get history (may be empty for new task)
        history_result = self.client.call("tasks.history", {"id": task_id, "limit": 10})
        assert "history" in history_result, f"Expected 'history' key: {history_result}"
        assert isinstance(history_result["history"], list), "history should be a list"
        print(f"Task history has {len(history_result['history'])} entries")
        
        # Cleanup
        self.client.call("tasks.delete", {"id": task_id})


class TestNotificationsRPC:
    """Tests for notifications.* RPC methods"""
    
    @pytest.fixture(autouse=True)
    def setup_ws(self):
        """Setup WebSocket connection for each test"""
        self.client = WebSocketRPCClient().connect()
        yield
        self.client.close()
    
    def test_notifications_list(self):
        """Test listing notifications with unread count"""
        result = self.client.call("notifications.list", {"limit": 50})
        
        assert "notifications" in result, f"Expected 'notifications' key: {result}"
        assert "unread_count" in result, f"Expected 'unread_count' key: {result}"
        assert isinstance(result["notifications"], list), "notifications should be a list"
        assert isinstance(result["unread_count"], int), "unread_count should be an integer"
        
        print(f"Found {len(result['notifications'])} notifications, {result['unread_count']} unread")
    
    def test_notifications_list_unread_only(self):
        """Test listing only unread notifications"""
        result = self.client.call("notifications.list", {"limit": 50, "unread_only": True})
        
        assert "notifications" in result, f"Expected 'notifications' key: {result}"
        # If there are notifications, they should all be unread
        for notif in result.get("notifications", []):
            assert notif.get("read") == False or notif.get("read") is None, "Should only return unread notifications"
        
        print(f"Found {len(result['notifications'])} unread notifications")
    
    def test_notifications_mark_all_read(self):
        """Test marking all notifications as read (no id param)"""
        result = self.client.call("notifications.mark_read", {})
        
        assert result.get("ok") == True, f"mark_read (all) failed: {result}"
        print(f"Marked {result.get('marked', 'all')} notifications as read")
        
        # Verify unread count is 0
        list_result = self.client.call("notifications.list", {"limit": 10})
        assert list_result.get("unread_count", 0) == 0, "Unread count should be 0 after mark all read"
    
    def test_notifications_clear(self):
        """Test clearing all notifications"""
        result = self.client.call("notifications.clear")
        
        assert result.get("ok") == True, f"clear failed: {result}"
        print(f"Cleared {result.get('cleared', 'all')} notifications")
        
        # Verify list is empty
        list_result = self.client.call("notifications.list", {"limit": 10})
        assert len(list_result.get("notifications", [])) == 0, "Notifications should be empty after clear"


class TestMonitorTool:
    """Tests for monitor_url tool registration"""
    
    @pytest.fixture(autouse=True)
    def setup_ws(self):
        """Setup WebSocket connection for each test"""
        self.client = WebSocketRPCClient().connect()
        yield
        self.client.close()
    
    def test_monitor_url_tool_registered(self):
        """Test that monitor_url tool is registered in tools.list"""
        result = self.client.call("tools.list")
        
        assert "tools" in result, f"Expected 'tools' key: {result}"
        tool_names = [t.get("name") for t in result.get("tools", [])]
        
        assert "monitor_url" in tool_names, f"monitor_url tool not found. Available tools: {tool_names}"
        print(f"monitor_url tool is registered. Total tools: {len(tool_names)}")
        
        # Verify tool schema
        monitor_tool = next((t for t in result["tools"] if t.get("name") == "monitor_url"), None)
        assert monitor_tool is not None, "monitor_url tool not found"
        assert "description" in monitor_tool, "Tool should have description"
        assert "parameters" in monitor_tool, "Tool should have parameters"
        
        params = monitor_tool.get("parameters", {})
        props = params.get("properties", {})
        assert "url" in props, "monitor_url should have 'url' parameter"
        assert "focus" in props, "monitor_url should have 'focus' parameter"
        
        print(f"monitor_url tool schema verified: {monitor_tool.get('description', '')[:100]}...")


class TestIntegrationScenarios:
    """Integration tests for task+notification flow"""
    
    @pytest.fixture(autouse=True)
    def setup_ws(self):
        """Setup WebSocket connection for each test"""
        self.client = WebSocketRPCClient().connect()
        yield
        self.client.close()
    
    def test_scheduler_and_notifications_available(self):
        """Test that both scheduler and notification manager are initialized"""
        # Test scheduler
        tasks_result = self.client.call("tasks.list")
        assert "error" not in tasks_result or "Scheduler not available" not in str(tasks_result.get("error", "")), \
            f"Scheduler not available: {tasks_result}"
        
        # Test notifications
        notifs_result = self.client.call("notifications.list", {"limit": 10})
        assert "error" not in notifs_result or "Notifications not available" not in str(notifs_result.get("error", "")), \
            f"Notifications not available: {notifs_result}"
        
        print("Both scheduler and notification manager are available")
    
    def test_create_task_with_notify_always(self):
        """Test creating a task with notify=always mode"""
        task_params = {
            "name": "TEST_NotifyAlways_Task",
            "prompt": "Report the current status",
            "interval_seconds": 3600,
            "agent_id": "default",
            "notify": "always"  # Should create notification on every run
        }
        result = self.client.call("tasks.create", task_params)
        assert result.get("ok") == True, f"Create failed: {result}"
        task = result["task"]
        assert task["notify"] == "always", "notify mode should be 'always'"
        
        # Cleanup
        self.client.call("tasks.delete", {"id": task["id"]})
        print("Created task with notify=always successfully")
    
    def test_create_task_with_notify_never(self):
        """Test creating a task with notify=never mode"""
        task_params = {
            "name": "TEST_NotifyNever_Task",
            "prompt": "Silent task",
            "interval_seconds": 60,
            "agent_id": "default",
            "notify": "never"
        }
        result = self.client.call("tasks.create", task_params)
        assert result.get("ok") == True, f"Create failed: {result}"
        task = result["task"]
        assert task["notify"] == "never", "notify mode should be 'never'"
        
        # Cleanup
        self.client.call("tasks.delete", {"id": task["id"]})
        print("Created task with notify=never successfully")


# Cleanup fixture to remove test tasks after all tests
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_tasks():
    """Cleanup any TEST_ prefixed tasks after module completes"""
    yield
    try:
        client = WebSocketRPCClient().connect()
        
        # List and delete TEST_ tasks
        list_result = client.call("tasks.list")
        for task in list_result.get("tasks", []):
            if task.get("name", "").startswith("TEST_"):
                client.call("tasks.delete", {"id": task["id"]})
                print(f"Cleaned up test task: {task['id']}")
        
        client.close()
    except Exception as e:
        print(f"Cleanup error: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
