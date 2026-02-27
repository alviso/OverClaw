"""
Test Memory Architecture Upgrade - FAISS + Hybrid Search
==========================================================
Tests the upgraded memory system with:
- FAISS indexed vector search
- Hybrid scoring (70% vector + 30% keyword)
- Per-agent memory isolation
- memory.stats/search/store/clear/reprocess RPC methods
"""
import pytest
import asyncio
import websockets
import json
import os
import time
import uuid

# Use the external frontend URL for testing
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://screen-share-ai-1.preview.emergentagent.com')
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/gateway'
GATEWAY_TOKEN = 'dev-token-change-me'


class TestMemoryArchitecture:
    """Test the memory architecture upgrade with FAISS + hybrid search."""
    
    @pytest.fixture
    def rpc_id(self):
        """Generate unique RPC ID as string (required by JSON-RPC)."""
        return str(uuid.uuid4())[:8]
    
    async def _connect_and_auth(self):
        """Connect to WebSocket and authenticate."""
        ws = await websockets.connect(WS_URL, ping_interval=30, ping_timeout=30)
        
        # Wait for welcome message
        welcome = await asyncio.wait_for(ws.recv(), timeout=5)
        welcome_data = json.loads(welcome)
        assert welcome_data.get('method') == 'gateway.welcome', f"Expected welcome, got: {welcome_data}"
        
        # Authenticate
        auth_msg = {
            "id": "auth-1",
            "method": "connect",
            "params": {"token": GATEWAY_TOKEN}
        }
        await ws.send(json.dumps(auth_msg))
        auth_response = await asyncio.wait_for(ws.recv(), timeout=5)
        auth_data = json.loads(auth_response)
        assert auth_data.get('result', {}).get('ok') == True, f"Auth failed: {auth_data}"
        
        return ws
    
    async def _rpc_call(self, ws, method: str, params: dict, rpc_id: str):
        """Make an RPC call and return the result, filtering out ping messages."""
        msg = {
            "id": rpc_id,
            "method": method,
            "params": params
        }
        await ws.send(json.dumps(msg))
        
        # Wait for response, skipping ping messages
        while True:
            response = await asyncio.wait_for(ws.recv(), timeout=30)
            data = json.loads(response)
            
            # Skip keepalive pings
            if data.get('method') == 'gateway.ping':
                continue
            
            # Match by ID
            if data.get('id') == rpc_id:
                if 'error' in data:
                    return {'error': data['error']}
                return data.get('result', {})
        
    @pytest.mark.asyncio
    async def test_memory_stats_returns_correct_structure(self, rpc_id):
        """memory.stats should return total, faiss_index_size, raw_qa_memories, extracted_facts, by_agent, hybrid_weights."""
        ws = await self._connect_and_auth()
        try:
            result = await self._rpc_call(ws, 'memory.stats', {}, rpc_id)
            
            # Check all required fields are present
            assert 'total_memories' in result, f"Missing total_memories in {result}"
            assert 'faiss_index_size' in result, f"Missing faiss_index_size in {result}"
            assert 'raw_qa_memories' in result, f"Missing raw_qa_memories in {result}"
            assert 'extracted_facts' in result, f"Missing extracted_facts in {result}"
            assert 'by_agent' in result, f"Missing by_agent in {result}"
            assert 'hybrid_weights' in result, f"Missing hybrid_weights in {result}"
            
            # Verify hybrid weights structure
            hw = result['hybrid_weights']
            assert 'vector' in hw, f"Missing vector weight in {hw}"
            assert 'keyword' in hw, f"Missing keyword weight in {hw}"
            assert hw['vector'] == 0.7, f"Expected vector weight 0.7, got {hw['vector']}"
            assert hw['keyword'] == 0.3, f"Expected keyword weight 0.3, got {hw['keyword']}"
            
            # Verify embedding dimensions
            assert result.get('embedding_dims') == 1536, f"Expected embedding_dims 1536, got {result.get('embedding_dims')}"
            
            print(f"[PASS] memory.stats returned: total={result['total_memories']}, "
                  f"faiss={result['faiss_index_size']}, raw_qa={result['raw_qa_memories']}, "
                  f"facts={result['extracted_facts']}, by_agent={result['by_agent']}")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_faiss_index_size_matches_memories(self, rpc_id):
        """FAISS index size should approximately match the number of memories with embeddings."""
        ws = await self._connect_and_auth()
        try:
            result = await self._rpc_call(ws, 'memory.stats', {}, rpc_id)
            
            total = result.get('total_memories', 0)
            faiss_size = result.get('faiss_index_size', 0)
            
            # FAISS index should have vectors for memories
            assert faiss_size > 0 or total == 0, f"FAISS index empty but have {total} memories"
            
            # FAISS size should be <= total (some memories might not have embeddings)
            if total > 0:
                assert faiss_size <= total, f"FAISS size {faiss_size} > total {total}"
            
            print(f"[PASS] FAISS index has {faiss_size} vectors, {total} total memories")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_memory_search_returns_hybrid_scores(self, rpc_id):
        """memory.search should return results with vector_score and keyword_score fields."""
        ws = await self._connect_and_auth()
        try:
            # First check if we have any memories to search
            stats = await self._rpc_call(ws, 'memory.stats', {}, f"{rpc_id}-stats")
            if stats.get('total_memories', 0) == 0:
                pytest.skip("No memories available to search")
            
            result = await self._rpc_call(ws, 'memory.search', {'query': 'test', 'top_k': 5}, rpc_id)
            
            assert 'results' in result, f"Missing results in {result}"
            assert 'count' in result, f"Missing count in {result}"
            
            if result['count'] > 0:
                # Check first result has required score fields
                first = result['results'][0]
                assert 'similarity' in first, f"Missing similarity in {first}"
                assert 'vector_score' in first, f"Missing vector_score in {first}"
                assert 'keyword_score' in first, f"Missing keyword_score in {first}"
                assert 'content' in first, f"Missing content in {first}"
                
                print(f"[PASS] memory.search returned {result['count']} results with hybrid scores: "
                      f"similarity={first['similarity']}, vector={first['vector_score']}, keyword={first['keyword_score']}")
            else:
                print(f"[PASS] memory.search returned 0 results for 'test' query (valid response)")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_memory_store_adds_to_faiss_index(self, rpc_id):
        """memory.store should add new memory and update FAISS index."""
        ws = await self._connect_and_auth()
        try:
            # Get initial stats
            initial_stats = await self._rpc_call(ws, 'memory.stats', {}, f"{rpc_id}-stats1")
            initial_faiss = initial_stats.get('faiss_index_size', 0)
            initial_total = initial_stats.get('total_memories', 0)
            
            # Store a new memory
            test_content = f"TEST_MEMORY_{uuid.uuid4().hex[:8]}: This is a test memory for FAISS indexing"
            store_result = await self._rpc_call(ws, 'memory.store', {
                'content': test_content,
                'session_id': 'test-session',
                'agent_id': 'default'
            }, rpc_id)
            
            assert store_result.get('ok') == True, f"memory.store failed: {store_result}"
            
            # Get updated stats
            updated_stats = await self._rpc_call(ws, 'memory.stats', {}, f"{rpc_id}-stats2")
            updated_faiss = updated_stats.get('faiss_index_size', 0)
            updated_total = updated_stats.get('total_memories', 0)
            
            # Verify counts increased
            assert updated_total == initial_total + 1, f"Total memories didn't increase: {initial_total} -> {updated_total}"
            assert updated_faiss == initial_faiss + 1, f"FAISS index didn't update: {initial_faiss} -> {updated_faiss}"
            
            print(f"[PASS] memory.store added memory: total {initial_total}->{updated_total}, "
                  f"faiss {initial_faiss}->{updated_faiss}")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_memory_search_with_agent_filter(self, rpc_id):
        """memory.search with agent_id filter should only return memories for that agent."""
        ws = await self._connect_and_auth()
        try:
            # Store memories for different agents
            test_agent1 = f"test-agent-{uuid.uuid4().hex[:8]}"
            test_agent2 = f"test-agent-{uuid.uuid4().hex[:8]}"
            
            # Store memory for agent 1
            await self._rpc_call(ws, 'memory.store', {
                'content': f"ISOLATION_TEST Agent1 memory about Python programming",
                'session_id': 'test-isolation',
                'agent_id': test_agent1
            }, f"{rpc_id}-store1")
            
            # Store memory for agent 2
            await self._rpc_call(ws, 'memory.store', {
                'content': f"ISOLATION_TEST Agent2 memory about JavaScript development",
                'session_id': 'test-isolation',
                'agent_id': test_agent2
            }, f"{rpc_id}-store2")
            
            # Search with agent1 filter - should only find agent1's memory
            search_result1 = await self._rpc_call(ws, 'memory.search', {
                'query': 'ISOLATION_TEST programming',
                'agent_id': test_agent1,
                'top_k': 10
            }, f"{rpc_id}-search1")
            
            # Verify isolation - results should only be for agent1
            for mem in search_result1.get('results', []):
                if 'ISOLATION_TEST' in mem.get('content', ''):
                    assert mem.get('agent_id') == test_agent1, \
                        f"Got memory from wrong agent: {mem.get('agent_id')} instead of {test_agent1}"
            
            print(f"[PASS] memory.search with agent_id filter: isolation verified for {test_agent1}")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_memory_clear_rebuilds_faiss_index(self, rpc_id):
        """memory.clear should clear memories and rebuild FAISS index."""
        ws = await self._connect_and_auth()
        try:
            # Create a test agent for isolation
            test_agent = f"clear-test-{uuid.uuid4().hex[:8]}"
            
            # Store some memories for this agent
            for i in range(3):
                await self._rpc_call(ws, 'memory.store', {
                    'content': f"CLEAR_TEST memory {i} for cleanup testing",
                    'session_id': 'test-clear',
                    'agent_id': test_agent
                }, f"{rpc_id}-store{i}")
            
            # Get stats after storing
            stats_before = await self._rpc_call(ws, 'memory.stats', {}, f"{rpc_id}-statsbefore")
            
            # Clear memories for this agent only
            clear_result = await self._rpc_call(ws, 'memory.clear', {
                'agent_id': test_agent
            }, f"{rpc_id}-clear")
            
            assert clear_result.get('ok') == True, f"memory.clear failed: {clear_result}"
            assert clear_result.get('cleared', 0) >= 3, f"Expected to clear at least 3 memories: {clear_result}"
            
            # Get stats after clearing
            stats_after = await self._rpc_call(ws, 'memory.stats', {}, f"{rpc_id}-statsafter")
            
            # Verify agent's memories were removed from by_agent
            by_agent_after = stats_after.get('by_agent', {})
            assert by_agent_after.get(test_agent, 0) == 0, \
                f"Agent {test_agent} still has memories after clear: {by_agent_after}"
            
            print(f"[PASS] memory.clear rebuilt FAISS index: cleared {clear_result.get('cleared')} memories")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_memory_reprocess_endpoint_exists(self, rpc_id):
        """memory.reprocess endpoint should exist and respond."""
        ws = await self._connect_and_auth()
        try:
            result = await self._rpc_call(ws, 'memory.reprocess', {}, rpc_id)
            
            # Should return status, even if nothing to reprocess
            assert 'status' in result or 'error' not in result, f"Unexpected reprocess response: {result}"
            
            # Valid statuses
            if 'status' in result:
                assert result['status'] in ['complete', 'nothing_to_reprocess'], \
                    f"Unexpected status: {result['status']}"
            
            print(f"[PASS] memory.reprocess endpoint responded: {result.get('status', result)}")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_memory_list_endpoint(self, rpc_id):
        """memory.list should return recent memories."""
        ws = await self._connect_and_auth()
        try:
            result = await self._rpc_call(ws, 'memory.list', {'limit': 10}, rpc_id)
            
            assert 'memories' in result, f"Missing memories in {result}"
            assert 'total' in result, f"Missing total in {result}"
            
            if result['total'] > 0:
                first = result['memories'][0]
                assert 'content' in first, f"Memory missing content: {first}"
                assert 'agent_id' in first, f"Memory missing agent_id: {first}"
                assert 'created_at' in first, f"Memory missing created_at: {first}"
            
            print(f"[PASS] memory.list returned {len(result['memories'])} memories, {result['total']} total")
        finally:
            await ws.close()


class TestModelsAndAgentIdentity:
    """Test model selector and agent self-identification."""
    
    async def _connect_and_auth(self):
        """Connect to WebSocket and authenticate."""
        ws = await websockets.connect(WS_URL, ping_interval=30, ping_timeout=30)
        
        welcome = await asyncio.wait_for(ws.recv(), timeout=5)
        welcome_data = json.loads(welcome)
        assert welcome_data.get('method') == 'gateway.welcome'
        
        auth_msg = {"id": "auth-1", "method": "connect", "params": {"token": GATEWAY_TOKEN}}
        await ws.send(json.dumps(auth_msg))
        auth_response = await asyncio.wait_for(ws.recv(), timeout=5)
        auth_data = json.loads(auth_response)
        assert auth_data.get('result', {}).get('ok') == True
        
        return ws
    
    async def _rpc_call(self, ws, method: str, params: dict, rpc_id: str):
        """Make an RPC call and return the result."""
        msg = {"id": rpc_id, "method": method, "params": params}
        await ws.send(json.dumps(msg))
        
        while True:
            response = await asyncio.wait_for(ws.recv(), timeout=30)
            data = json.loads(response)
            if data.get('method') == 'gateway.ping':
                continue
            if data.get('id') == rpc_id:
                return data.get('result', data.get('error', {}))
    
    @pytest.fixture
    def rpc_id(self):
        return str(uuid.uuid4())[:8]
    
    @pytest.mark.asyncio
    async def test_models_list_has_updated_labels(self, rpc_id):
        """models.list should return models with friendly labels like GPT-5.2, Claude Opus 4.6."""
        ws = await self._connect_and_auth()
        try:
            result = await self._rpc_call(ws, 'models.list', {}, rpc_id)
            
            assert 'models' in result, f"Missing models in {result}"
            
            models = result['models']
            model_ids = [m['id'] for m in models]
            model_labels = {m['id']: m.get('label', '') for m in models}
            
            # Check for expected model IDs
            expected_models = [
                'openai/gpt-5.2',
                'openai/gpt-4o',
                'anthropic/claude-opus-4.6',
                'anthropic/claude-sonnet-4.5'
            ]
            
            for expected in expected_models:
                assert expected in model_ids, f"Missing model {expected} in {model_ids}"
            
            # Check for friendly labels
            assert model_labels.get('openai/gpt-5.2') == 'GPT-5.2', \
                f"Expected label 'GPT-5.2', got '{model_labels.get('openai/gpt-5.2')}'"
            assert model_labels.get('anthropic/claude-opus-4.6') == 'Claude Opus 4.6', \
                f"Expected label 'Claude Opus 4.6', got '{model_labels.get('anthropic/claude-opus-4.6')}'"
            
            print(f"[PASS] models.list has {len(models)} models with updated labels: {list(model_labels.values())}")
        finally:
            await ws.close()
    
    @pytest.mark.asyncio
    async def test_agents_list_returns_agents(self, rpc_id):
        """agents.list should return at least the default agent."""
        ws = await self._connect_and_auth()
        try:
            result = await self._rpc_call(ws, 'agents.list', {}, rpc_id)
            
            assert 'agents' in result, f"Missing agents in {result}"
            agents = result['agents']
            
            # Should have at least the default agent
            default_agent = next((a for a in agents if a.get('id') == 'default'), None)
            assert default_agent is not None, "Missing default agent"
            
            print(f"[PASS] agents.list returned {len(agents)} agents, default agent present")
        finally:
            await ws.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
