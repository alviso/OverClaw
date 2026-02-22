"""
Test Email Triage Prompt - Verifies the improved email triage prompt seeding
Tests for: prompt quality, correct defaults, key phrases, no redundant context
"""
import pytest
import requests
import os
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

# MongoDB client for direct database verification
mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]


class TestHealthEndpoint:
    """Health endpoint tests"""
    
    def test_health_returns_healthy(self):
        """Verify /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got: {data.get('status')}"
        assert "version" in data, "Response should contain version"
        assert "uptime" in data, "Response should contain uptime"
        print(f"✓ Health check passed: status={data['status']}, version={data['version']}")


class TestEmailTriageTaskInMongoDB:
    """Direct MongoDB verification of email-triage task"""
    
    def test_email_triage_task_exists(self):
        """Verify email-triage task exists in MongoDB tasks collection"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        
        assert task is not None, "Email triage task not found in MongoDB"
        print(f"✓ Email triage task found in MongoDB: id={task['id']}")
    
    def test_email_triage_prompt_version_is_2(self):
        """Verify email-triage task has prompt_version=2"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt_version = task.get("prompt_version")
        assert prompt_version == 2, f"Expected prompt_version=2, got: {prompt_version}"
        print(f"✓ Prompt version is correct: {prompt_version}")
    
    def test_email_triage_defaults_interval(self):
        """Verify email-triage task has interval_seconds=300"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        interval = task.get("interval_seconds")
        assert interval == 300, f"Expected interval_seconds=300, got: {interval}"
        print(f"✓ Interval is correct: {interval} seconds (5 minutes)")
    
    def test_email_triage_defaults_enabled_false(self):
        """Verify email-triage task is disabled by default (enabled=False)"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        enabled = task.get("enabled")
        assert enabled == False, f"Expected enabled=False, got: {enabled}"
        print(f"✓ Task is disabled by default: enabled={enabled}")
    
    def test_email_triage_defaults_notify_exists(self):
        """Verify email-triage task has a notify setting (defaults code has 'always', but existing tasks may have user overrides)"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        notify = task.get("notify")
        assert notify in ["always", "never", "on_change"], f"Expected valid notify setting, got: {notify}"
        print(f"✓ Notify setting exists: {notify}")
        
        # Also verify that the seed code (email_triage.py) has correct default
        # This is verified by code inspection - the new task creation sets notify='always'
        # Existing tasks preserve their user-configured notify setting during prompt updates
        print("  Note: Seed code default is 'always', existing task may have user override")


class TestEmailTriagePromptContent:
    """Verify the prompt content is actionable and well-structured"""
    
    def test_prompt_contains_action_required(self):
        """Verify prompt contains 'Action Required' for urgency classification"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "Action Required" in prompt, "Prompt should contain 'Action Required'"
        print("✓ Prompt contains 'Action Required' classification")
    
    def test_prompt_contains_slack_notify(self):
        """Verify prompt instructs to use slack_notify tool"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "slack_notify" in prompt, "Prompt should contain 'slack_notify' tool usage"
        print("✓ Prompt contains 'slack_notify' tool instruction")
    
    def test_prompt_contains_tier_a(self):
        """Verify prompt has Tier A classification for action-required emails"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "Tier A" in prompt, "Prompt should contain 'Tier A' classification"
        print("✓ Prompt contains 'Tier A' classification")
    
    def test_prompt_contains_tier_b(self):
        """Verify prompt has Tier B classification for FYI emails"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "Tier B" in prompt, "Prompt should contain 'Tier B' classification"
        print("✓ Prompt contains 'Tier B' classification")
    
    def test_prompt_contains_tier_c(self):
        """Verify prompt has Tier C classification for skip emails"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "Tier C" in prompt, "Prompt should contain 'Tier C' classification"
        print("✓ Prompt contains 'Tier C' classification")
    
    def test_prompt_contains_gmail_tool(self):
        """Verify prompt mentions gmail tool for fetching emails"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "gmail" in prompt.lower(), "Prompt should mention 'gmail' tool"
        print("✓ Prompt contains gmail tool instruction")


class TestEmailTriagePromptQuality:
    """Verify the prompt avoids redundant context and is actionable"""
    
    def test_prompt_no_project_history_context(self):
        """Verify prompt does NOT tell user about their project history"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "").lower()
        # These would be signs of verbose, redundant context instructions
        redundant_phrases = [
            "tell the user about their project history",
            "remind the user about their ongoing projects",
            "provide background on the user's work",
            "summarize the user's relationship with",
        ]
        for phrase in redundant_phrases:
            assert phrase not in prompt, f"Prompt should NOT contain redundant phrase: '{phrase}'"
        print("✓ Prompt does NOT contain redundant project history instructions")
    
    def test_prompt_leads_with_action(self):
        """Verify prompt emphasizes leading with action, not context"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        # The prompt should explicitly tell the AI to lead with action
        assert "Lead with the ACTION" in prompt or "lead with action" in prompt.lower(), \
            "Prompt should emphasize leading with action"
        print("✓ Prompt emphasizes leading with ACTION, not context")
    
    def test_prompt_has_no_new_emails_handling(self):
        """Verify prompt handles case of no new emails gracefully"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        assert "No new emails" in prompt or "no new unread emails" in prompt.lower(), \
            "Prompt should handle 'no new emails' case"
        print("✓ Prompt has handling for 'No new emails' case")
    
    def test_prompt_single_notification_rule(self):
        """Verify prompt instructs to send only ONE Slack notification"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        # Check for instruction to send single/one notification
        single_msg_indicators = ["ONE Slack", "single message", "one notification", "ONE slack_notify"]
        found = any(ind.lower() in prompt.lower() for ind in single_msg_indicators)
        assert found, "Prompt should instruct to send only ONE Slack message"
        print("✓ Prompt instructs to send only ONE Slack notification")
    
    def test_prompt_has_structured_format(self):
        """Verify prompt has structured format for notifications"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        prompt = task.get("prompt", "")
        # Check for formatting instructions
        format_indicators = ["Format:", "Action:", "Deadline:", "Key detail:"]
        found = sum(1 for ind in format_indicators if ind in prompt)
        assert found >= 2, f"Prompt should have structured format indicators, found: {found}"
        print(f"✓ Prompt has structured format with {found} format indicators")


class TestSchedulerCanListTasks:
    """Verify the scheduler module can list tasks including email-triage"""
    
    def test_tasks_collection_has_email_triage(self):
        """Verify tasks collection includes email-triage task"""
        tasks = list(db.tasks.find({}, {"_id": 0, "id": 1, "name": 1}))
        
        task_ids = [t.get("id") for t in tasks]
        assert "email-triage" in task_ids, f"email-triage not in tasks: {task_ids}"
        print(f"✓ Tasks collection includes email-triage. Total tasks: {len(tasks)}")
    
    def test_email_triage_has_all_required_fields(self):
        """Verify email-triage task has all required fields for scheduler"""
        task = db.tasks.find_one({"id": "email-triage"}, {"_id": 0})
        assert task is not None, "Email triage task not found"
        
        required_fields = [
            "id", "name", "description", "prompt", "prompt_version",
            "agent_id", "interval_seconds", "enabled", "notify",
            "notify_level", "running", "next_run", "created_at"
        ]
        
        missing = [f for f in required_fields if f not in task]
        assert not missing, f"Missing required fields: {missing}"
        print(f"✓ Email triage task has all {len(required_fields)} required fields")


# Cleanup
@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    mongo_client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
