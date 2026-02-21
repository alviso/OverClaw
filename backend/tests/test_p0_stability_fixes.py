"""
P0 Stability Fixes - Backend Tests
Tests for:
1. Unified secret loading in setup.py with ENV_ONLY_FIELDS
2. Process manager resilience with liveness checks
3. DB_NAME hardcoded fallback fixes
"""
import pytest
import requests
import os
import sys

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
GATEWAY_TOKEN = "dev-token-change-me"


class TestHealthEndpoint:
    """Health check endpoint tests"""
    
    def test_health_returns_200(self):
        """Backend should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Status not healthy: {data}"
        assert "gateway" in data
        assert "version" in data
        assert "uptime" in data
        print(f"✓ Health check passed: {data.get('gateway')} v{data.get('version')}")


class TestSetupStatus:
    """Setup status endpoint tests - verifying ENV_ONLY_FIELDS behavior"""
    
    def test_setup_status_returns_200(self):
        """Setup status should return successfully"""
        response = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        assert response.status_code == 200, f"Setup status failed: {response.text}"
        
        data = response.json()
        assert "fields" in data
        assert "needs_setup" in data
        assert "has_any_llm" in data
        print(f"✓ Setup status returned: needs_setup={data.get('needs_setup')}, has_any_llm={data.get('has_any_llm')}")
    
    def test_gateway_token_is_env_only(self):
        """gateway_token should show source='none' for placeholder values (env-only field)"""
        response = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        fields = data.get("fields", {})
        gateway_token_field = fields.get("gateway_token", {})
        
        # The current GATEWAY_TOKEN is "dev-token-change-me" which matches placeholder pattern
        # So it should show as is_set=false, source="none"
        assert gateway_token_field.get("source") == "none", f"gateway_token source should be 'none' for placeholder, got: {gateway_token_field}"
        assert gateway_token_field.get("is_set") == False, f"gateway_token is_set should be false for placeholder"
        print(f"✓ gateway_token correctly shows as env-only field with source='none' for placeholder")
    
    def test_openai_api_key_from_environment(self):
        """openai_api_key should show source='environment' when set in env"""
        response = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        fields = data.get("fields", {})
        openai_field = fields.get("openai_api_key", {})
        
        # OPENAI_API_KEY is set in .env with a real value
        assert openai_field.get("source") == "environment", f"openai_api_key source should be 'environment', got: {openai_field}"
        assert openai_field.get("is_set") == True, "openai_api_key should be set"
        assert openai_field.get("masked_value"), "openai_api_key should have masked value"
        print(f"✓ openai_api_key correctly shows source='environment', is_set=True")
    
    def test_anthropic_api_key_from_environment(self):
        """anthropic_api_key should show source='environment' when set in env"""
        response = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        fields = data.get("fields", {})
        anthropic_field = fields.get("anthropic_api_key", {})
        
        assert anthropic_field.get("source") == "environment", f"anthropic_api_key source should be 'environment', got: {anthropic_field}"
        assert anthropic_field.get("is_set") == True, "anthropic_api_key should be set"
        print(f"✓ anthropic_api_key correctly shows source='environment', is_set=True")
    
    def test_has_any_llm_is_true(self):
        """has_any_llm should be True when OpenAI or Anthropic key is set"""
        response = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("has_any_llm") == True, "has_any_llm should be True with API keys set"
        assert data.get("needs_setup") == False, "needs_setup should be False with LLM keys set"
        print(f"✓ has_any_llm=True, needs_setup=False correctly set")


class TestSetupSave:
    """Test POST /api/setup/save endpoint"""
    
    def test_setup_save_no_values(self):
        """Save with empty data should return error"""
        response = requests.post(f"{BASE_URL}/api/setup/save", json={}, timeout=10)
        assert response.status_code == 200  # Returns 200 with error in body
        
        data = response.json()
        assert data.get("ok") == False, "Save with no values should fail"
        assert "error" in data or "No values" in str(data), f"Should have error message: {data}"
        print(f"✓ Empty save correctly returns error: {data.get('error', data)}")
    
    def test_setup_save_updates_env(self):
        """Save should update environment variables"""
        # We'll save a test value for slack_bot_token (which is not set)
        test_token = "xoxb-test-token-for-testing"
        response = requests.post(
            f"{BASE_URL}/api/setup/save",
            json={"slack_bot_token": test_token},
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("ok") == True, f"Save should succeed: {data}"
        assert "slack_bot_token" in data.get("applied", []), f"slack_bot_token should be applied: {data}"
        
        # Verify it's now showing in status
        status_resp = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        status_data = status_resp.json()
        slack_field = status_data.get("fields", {}).get("slack_bot_token", {})
        
        assert slack_field.get("is_set") == True, f"slack_bot_token should now be set: {slack_field}"
        # Source will be "database" since we saved it
        assert slack_field.get("source") in ["database", "environment"], f"Source should be database or environment: {slack_field}"
        print(f"✓ Setup save works correctly, slack_bot_token saved and showing as set")


class TestGatewayTokenNotOverriddenByDB:
    """Verify gateway_token env is NOT overridden by DB values"""
    
    def test_gateway_token_env_only(self):
        """Even if we save gateway_token to DB, it should not override env value"""
        # First, save a fake gateway_token to DB
        save_resp = requests.post(
            f"{BASE_URL}/api/setup/save",
            json={"gateway_token": "fake-db-gateway-token"},
            timeout=10
        )
        # It will save to DB, but...
        
        # Check that setup/status still shows the env-only behavior
        status_resp = requests.get(f"{BASE_URL}/api/setup/status", timeout=10)
        status_data = status_resp.json()
        gateway_field = status_data.get("fields", {}).get("gateway_token", {})
        
        # gateway_token is env-only, so it should still show source as 'none' for placeholder
        # OR 'environment' for real values, but NEVER 'database'
        source = gateway_field.get("source")
        # The placeholder "dev-token-change-me" should show as is_set=false, source='none'
        assert source in ["none", "environment"], f"gateway_token source should be 'none' or 'environment', not 'database': {gateway_field}"
        print(f"✓ gateway_token correctly shows as env-only (source='{source}'), DB value is NOT overriding")


class TestCodePatterns:
    """Verify no problematic code patterns exist"""
    
    def test_no_pymongo_if_not_db_pattern(self):
        """Verify no 'if not _db' patterns exist (should use 'is None')"""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "if not _db", "/app/backend", "--include=*.py"],
            capture_output=True,
            text=True
        )
        # Should find nothing
        if result.stdout.strip():
            pytest.fail(f"Found 'if not _db' patterns (should use 'is None'):\n{result.stdout}")
        print(f"✓ No 'if not _db' patterns found in codebase")
    
    def test_env_only_fields_defined(self):
        """Verify _ENV_ONLY_FIELDS is defined in setup.py with gateway_token"""
        with open("/app/backend/gateway/setup.py", "r") as f:
            content = f.read()
        
        assert "_ENV_ONLY_FIELDS" in content, "_ENV_ONLY_FIELDS should be defined in setup.py"
        assert '"gateway_token"' in content or "'gateway_token'" in content, "gateway_token should be in _ENV_ONLY_FIELDS"
        print(f"✓ _ENV_ONLY_FIELDS correctly defined with gateway_token")
    
    def test_process_manager_has_liveness_check(self):
        """Verify _is_pid_alive function exists in process_manager.py"""
        with open("/app/backend/gateway/tools/process_manager.py", "r") as f:
            content = f.read()
        
        assert "_is_pid_alive" in content, "_is_pid_alive function should exist"
        assert "cleanup_dead_processes" in content, "cleanup_dead_processes function should exist"
        assert "os.kill(pid, 0)" in content, "Liveness check should use os.kill(pid, 0)"
        print(f"✓ Process manager has liveness check functions")


class TestProcessManagerDirectImport:
    """Test process manager module directly"""
    
    def test_cleanup_dead_processes_function(self):
        """Test that cleanup_dead_processes can be imported and called"""
        sys.path.insert(0, "/app/backend")
        from gateway.tools.process_manager import cleanup_dead_processes, _processes
        
        # Call cleanup - should not raise
        initial_count = len(_processes)
        cleanup_dead_processes()
        final_count = len(_processes)
        print(f"✓ cleanup_dead_processes works: {initial_count} -> {final_count} processes")
    
    def test_is_pid_alive_function(self):
        """Test _is_pid_alive function"""
        sys.path.insert(0, "/app/backend")
        from gateway.tools.process_manager import _is_pid_alive
        import os
        
        # Current process should be alive
        assert _is_pid_alive(os.getpid()) == True, "Current process should be alive"
        
        # PID 1 (init) should be alive
        assert _is_pid_alive(1) == True, "PID 1 should be alive"
        
        # Very high PID should not exist
        assert _is_pid_alive(999999) == False, "PID 999999 should not exist"
        print(f"✓ _is_pid_alive correctly detects process liveness")
    
    def test_recover_processes_function(self):
        """Test that recover_processes can be imported and called"""
        sys.path.insert(0, "/app/backend")
        from gateway.tools.process_manager import recover_processes
        
        # Should not raise
        recover_processes()
        print(f"✓ recover_processes function works")


class TestDBNameFallback:
    """Verify DB_NAME is properly used (not hardcoded)"""
    
    def test_slack_channel_uses_db_name_env(self):
        """slack_channel.py should use os.environ['DB_NAME']"""
        with open("/app/backend/gateway/channels/slack_channel.py", "r") as f:
            content = f.read()
        
        # Should use DB_NAME from env, not hardcoded
        assert 'os.environ["DB_NAME"]' in content or "os.environ['DB_NAME']" in content, \
            "slack_channel.py should use os.environ['DB_NAME']"
        # Should NOT have hardcoded DB name in client connection
        assert 'client["overclaw"]' not in content and "client['overclaw']" not in content, \
            "slack_channel.py should not have hardcoded DB name 'overclaw'"
        print(f"✓ slack_channel.py correctly uses os.environ['DB_NAME']")
    
    def test_slack_notify_uses_db_name_env(self):
        """slack_notify.py should use os.environ['DB_NAME']"""
        with open("/app/backend/gateway/tools/slack_notify.py", "r") as f:
            content = f.read()
        
        assert 'os.environ["DB_NAME"]' in content or "os.environ['DB_NAME']" in content, \
            "slack_notify.py should use os.environ['DB_NAME']"
        print(f"✓ slack_notify.py correctly uses os.environ['DB_NAME']")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
