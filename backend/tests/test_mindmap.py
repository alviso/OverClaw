"""
Tests for Mindmap feature - Cognitive Landscape visualization.
Tests RPC methods: mindmap.get, mindmap.generate, mindmap.set_importance
"""
import pytest
import asyncio
import json
import os
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/gateway"
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "dev-token-change-me")


async def send_rpc(ws, method, params=None, req_id=1):
    """Send an RPC request and wait for response"""
    msg = {
        "jsonrpc": "2.0",
        "id": str(req_id),
        "method": method,
        "params": params or {}
    }
    await ws.send(json.dumps(msg))
    
    # Wait for response with matching id
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if data.get("id") == str(req_id):
            return data
        # Skip events/notifications


async def connect_and_auth(ws):
    """Connect to WebSocket and authenticate"""
    # Wait for welcome message
    welcome = await asyncio.wait_for(ws.recv(), timeout=5)
    print(f"Got welcome: {welcome[:100]}...")
    
    # Authenticate
    auth_resp = await send_rpc(ws, "connect", {"token": GATEWAY_TOKEN}, req_id="auth")
    if "error" in auth_resp:
        raise AssertionError(f"Auth failed: {auth_resp}")
    print(f"Authenticated: client_id={auth_resp.get('result', {}).get('client_id')}")
    return auth_resp


class TestMindmapRPC:
    """WebSocket RPC tests for mindmap feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test ID counter"""
        self.request_id = 0
    
    def get_request_id(self):
        self.request_id += 1
        return str(self.request_id)
    
    @pytest.mark.asyncio
    async def test_mindmap_get_returns_cached_data(self):
        """Test that mindmap.get returns the cached mindmap with nodes and edges"""
        async with websockets.connect(WS_URL, close_timeout=5) as ws:
            await connect_and_auth(ws)
            
            # Call mindmap.get
            result = await send_rpc(ws, "mindmap.get", {}, self.get_request_id())
            print(f"mindmap.get response: {json.dumps(result, indent=2)[:500]}")
            
            # Verify result structure
            assert "result" in result, f"Expected result in response: {result}"
            mindmap = result["result"]
            
            # According to main agent note, there should be cached data with 14 nodes (9 topics + 5 people)
            assert "nodes" in mindmap, "Expected nodes in mindmap"
            assert "edges" in mindmap, "Expected edges in mindmap"
            
            if mindmap.get("nodes"):
                # If data exists, verify structure
                node = mindmap["nodes"][0]
                assert "id" in node, "Node should have id"
                assert "label" in node, "Node should have label"
                assert "type" in node, "Node should have type (topic/person)"
                
                # Count topic and person nodes
                topics = [n for n in mindmap["nodes"] if n.get("type") == "topic"]
                people = [n for n in mindmap["nodes"] if n.get("type") == "person"]
                print(f"Found {len(topics)} topics and {len(people)} people nodes")
                print(f"Total nodes: {len(mindmap['nodes'])}, edges: {len(mindmap['edges'])}")
                
                # Verify topic node has expected fields
                if topics:
                    topic = topics[0]
                    assert "category" in topic, "Topic should have category"
                    print(f"Sample topic: {topic}")
                
                # Verify person node has expected fields
                if people:
                    person = people[0]
                    print(f"Sample person: {person}")
            else:
                # Empty is also valid (might need generation)
                print("Mindmap is empty, may need generation")
                assert mindmap.get("empty") == True or mindmap.get("nodes") == []
    
    @pytest.mark.asyncio
    async def test_mindmap_generate_creates_new_mindmap(self):
        """Test that mindmap.generate creates a new mindmap with LLM"""
        async with websockets.connect(WS_URL, close_timeout=60) as ws:
            await connect_and_auth(ws)
            
            # Call mindmap.generate (this calls LLM so may take time)
            print("Calling mindmap.generate - this may take a few seconds...")
            result = await asyncio.wait_for(
                send_rpc(ws, "mindmap.generate", {}, self.get_request_id()),
                timeout=45
            )
            print(f"mindmap.generate response: {json.dumps(result, indent=2)[:500]}...")
            
            # Verify result structure
            assert "result" in result, f"Expected result in response: {result}"
            mindmap = result["result"]
            
            # Check required fields
            assert "nodes" in mindmap, "Generated mindmap should have nodes"
            assert "edges" in mindmap, "Generated mindmap should have edges"
            assert "generated_at" in mindmap, "Generated mindmap should have generated_at timestamp"
            
            # If not empty/error, verify we have nodes
            if not mindmap.get("empty") and not mindmap.get("error"):
                assert len(mindmap["nodes"]) > 0, "Generated mindmap should have at least one node"
                print(f"Generated {len(mindmap['nodes'])} nodes and {len(mindmap['edges'])} edges")
    
    @pytest.mark.asyncio
    async def test_mindmap_set_importance_on_topic(self):
        """Test setting importance level on a topic node"""
        async with websockets.connect(WS_URL, close_timeout=10) as ws:
            await connect_and_auth(ws)
            
            # First get the current mindmap to find a topic node
            result = await send_rpc(ws, "mindmap.get", {}, self.get_request_id())
            mindmap = result.get("result", {})
            topics = [n for n in mindmap.get("nodes", []) if n.get("type") == "topic"]
            
            if not topics:
                pytest.skip("No topic nodes available to test set_importance")
            
            topic_id = topics[0]["id"]
            print(f"Testing set_importance on topic: {topic_id}")
            
            # Test setting importance to high
            result = await send_rpc(ws, "mindmap.set_importance", {
                "node_id": topic_id,
                "importance": "high"
            }, self.get_request_id())
            print(f"Set importance to high: {result}")
            assert "result" in result, f"Expected result: {result}"
            assert result["result"].get("ok") == True, f"set_importance should succeed: {result}"
            assert result["result"].get("node_id") == topic_id
            assert result["result"].get("importance") == "high"
            
            # Verify the change persisted
            get_result = await send_rpc(ws, "mindmap.get", {}, self.get_request_id())
            updated_mindmap = get_result.get("result", {})
            updated_topic = next((n for n in updated_mindmap.get("nodes", []) if n.get("id") == topic_id), None)
            if updated_topic:
                assert updated_topic.get("importance") == "high", f"Importance should be high: {updated_topic}"
            
            # Test setting to low
            result = await send_rpc(ws, "mindmap.set_importance", {
                "node_id": topic_id,
                "importance": "low"
            }, self.get_request_id())
            assert result["result"].get("ok") == True
            assert result["result"].get("importance") == "low"
            print("set_importance to low succeeded")
    
    @pytest.mark.asyncio
    async def test_mindmap_set_importance_validation(self):
        """Test that set_importance validates importance level"""
        async with websockets.connect(WS_URL, close_timeout=10) as ws:
            await connect_and_auth(ws)
            
            # Test with invalid importance level
            result = await send_rpc(ws, "mindmap.set_importance", {
                "node_id": "test-node",
                "importance": "invalid"
            }, self.get_request_id())
            print(f"Invalid importance response: {result}")
            res = result.get("result", {})
            assert res.get("ok") == False or res.get("error"), f"Should reject invalid importance: {result}"
    
    @pytest.mark.asyncio
    async def test_mindmap_set_importance_requires_params(self):
        """Test that set_importance requires node_id and importance"""
        async with websockets.connect(WS_URL, close_timeout=10) as ws:
            await connect_and_auth(ws)
            
            # Test without node_id
            result = await send_rpc(ws, "mindmap.set_importance", {
                "importance": "high"
            }, self.get_request_id())
            res = result.get("result", {})
            assert res.get("ok") == False or res.get("error"), f"Should require node_id: {result}"
            
            # Test without importance
            result = await send_rpc(ws, "mindmap.set_importance", {
                "node_id": "test"
            }, self.get_request_id())
            res = result.get("result", {})
            assert res.get("ok") == False or res.get("error"), f"Should require importance: {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
