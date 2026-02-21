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
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "dev-token-change-me")


class TestMindmapRPC:
    """WebSocket RPC tests for mindmap feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test ID counter"""
        self.request_id = 0
    
    def get_request_id(self):
        self.request_id += 1
        return str(self.request_id)
    
    async def rpc_call(self, ws, method, params=None):
        """Make an RPC call and return result"""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self.get_request_id()
        }
        await ws.send(json.dumps(msg))
        response = await ws.recv()
        return json.loads(response)
    
    async def wait_for_auth(self, ws):
        """Wait for auth.success, skipping any other messages like 'hot'"""
        while True:
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(response)
            if data.get("type") == "auth.success":
                return data
            elif data.get("type") == "hot":
                # Skip hot reload messages
                continue
            elif data.get("type") == "error" or "error" in data:
                raise AssertionError(f"Auth error: {data}")
            # For other message types, continue waiting
            print(f"Received message while waiting for auth: {data.get('type')}")
    
    @pytest.mark.asyncio
    async def test_mindmap_get_returns_cached_data(self):
        """Test that mindmap.get returns the cached mindmap with nodes and edges"""
        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            close_timeout=5
        ) as ws:
            # Wait for auth success
            auth_data = await self.wait_for_auth(ws)
            print(f"Auth successful: {auth_data}")
            
            # Call mindmap.get
            result = await self.rpc_call(ws, "mindmap.get")
            print(f"mindmap.get response: {json.dumps(result, indent=2)}")
            
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
                    # importance may not be present if not set
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
        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            close_timeout=60  # LLM generation may take time
        ) as ws:
            # Wait for auth success
            auth_data = await self.wait_for_auth(ws)
            
            # Call mindmap.generate (this calls LLM so may take time)
            print("Calling mindmap.generate - this may take a few seconds...")
            result = await asyncio.wait_for(
                self.rpc_call(ws, "mindmap.generate"),
                timeout=45  # Allow time for LLM call
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
        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            close_timeout=10
        ) as ws:
            # Wait for auth success
            auth_response = await asyncio.wait_for(ws.recv(), timeout=5)
            auth_data = json.loads(auth_response)
            assert auth_data.get("type") == "auth.success", f"Auth failed: {auth_data}"
            
            # First get the current mindmap to find a topic node
            result = await self.rpc_call(ws, "mindmap.get")
            mindmap = result.get("result", {})
            topics = [n for n in mindmap.get("nodes", []) if n.get("type") == "topic"]
            
            if not topics:
                pytest.skip("No topic nodes available to test set_importance")
            
            topic_id = topics[0]["id"]
            print(f"Testing set_importance on topic: {topic_id}")
            
            # Test setting importance to high
            result = await self.rpc_call(ws, "mindmap.set_importance", {
                "node_id": topic_id,
                "importance": "high"
            })
            print(f"Set importance to high: {result}")
            assert "result" in result, f"Expected result: {result}"
            assert result["result"].get("ok") == True, f"set_importance should succeed: {result}"
            assert result["result"].get("node_id") == topic_id
            assert result["result"].get("importance") == "high"
            
            # Verify the change persisted
            get_result = await self.rpc_call(ws, "mindmap.get")
            updated_mindmap = get_result.get("result", {})
            updated_topic = next((n for n in updated_mindmap.get("nodes", []) if n.get("id") == topic_id), None)
            if updated_topic:
                assert updated_topic.get("importance") == "high", f"Importance should be high: {updated_topic}"
            
            # Test setting to low
            result = await self.rpc_call(ws, "mindmap.set_importance", {
                "node_id": topic_id,
                "importance": "low"
            })
            assert result["result"].get("ok") == True
            assert result["result"].get("importance") == "low"
            print("set_importance to low succeeded")
    
    @pytest.mark.asyncio
    async def test_mindmap_set_importance_validation(self):
        """Test that set_importance validates importance level"""
        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            close_timeout=10
        ) as ws:
            # Wait for auth success
            auth_response = await asyncio.wait_for(ws.recv(), timeout=5)
            auth_data = json.loads(auth_response)
            assert auth_data.get("type") == "auth.success"
            
            # Test with invalid importance level
            result = await self.rpc_call(ws, "mindmap.set_importance", {
                "node_id": "test-node",
                "importance": "invalid"
            })
            print(f"Invalid importance response: {result}")
            res = result.get("result", {})
            assert res.get("ok") == False or res.get("error"), f"Should reject invalid importance: {result}"
    
    @pytest.mark.asyncio
    async def test_mindmap_set_importance_requires_params(self):
        """Test that set_importance requires node_id and importance"""
        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            close_timeout=10
        ) as ws:
            # Wait for auth success
            auth_response = await asyncio.wait_for(ws.recv(), timeout=5)
            auth_data = json.loads(auth_response)
            assert auth_data.get("type") == "auth.success"
            
            # Test without node_id
            result = await self.rpc_call(ws, "mindmap.set_importance", {
                "importance": "high"
            })
            res = result.get("result", {})
            assert res.get("ok") == False or res.get("error"), f"Should require node_id: {result}"
            
            # Test without importance
            result = await self.rpc_call(ws, "mindmap.set_importance", {
                "node_id": "test"
            })
            res = result.get("result", {})
            assert res.get("ok") == False or res.get("error"), f"Should require importance: {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
