"""
Triage Feedback System Tests — Testing the new quality feedback loop for email triage.
Tests: track_triage_message, record_feedback, get_feedback_stats, build_feedback_prompt_section,
       RPC methods (triage.feedback_stats, triage.recent_feedback), and slack_notify integration.
"""
import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')

# Configure pytest-asyncio mode
pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_connection(event_loop):
    """MongoDB connection for testing — shared across tests."""
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


class TestHealthEndpoint:
    """Basic health check to ensure backend is running."""
    
    def test_health_endpoint_returns_healthy(self):
        """Verify backend health endpoint returns healthy status."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["gateway"] == "OverClaw Gateway"
        print(f"Health check passed: version={data['version']}, uptime={data['uptime']}")


class TestEmailTriageTaskConfiguration:
    """Verify email-triage task has correct prompt_version and feedback instructions."""
    
    def test_email_triage_task_has_prompt_version_3(self, db_connection):
        """Verify email-triage task in MongoDB has prompt_version=3."""
        async def run_test():
            task = await db_connection.tasks.find_one({"id": "email-triage"}, {"_id": 0})
            assert task is not None, "email-triage task not found in MongoDB"
            assert task.get("prompt_version") == 3, f"Expected prompt_version=3, got {task.get('prompt_version')}"
            print(f"Email-triage task found with prompt_version={task['prompt_version']}")
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_email_triage_prompt_has_request_feedback_instruction(self, db_connection):
        """Verify triage prompt instructs to use request_feedback=true."""
        async def run_test():
            task = await db_connection.tasks.find_one({"id": "email-triage"}, {"_id": 0})
            assert task is not None, "email-triage task not found"
            prompt = task.get("prompt", "")
            assert "request_feedback" in prompt, "Prompt should mention request_feedback parameter"
            # Check for the instruction pattern
            assert "request_feedback" in prompt and "true" in prompt, \
                "Prompt should instruct using request_feedback=true"
            print("Triage prompt contains request_feedback instructions")
        asyncio.get_event_loop().run_until_complete(run_test())


class TestTriageFeedbackModuleFunctions:
    """Direct tests on triage_feedback module functions."""
    
    def test_set_feedback_db_function(self, db_connection):
        """Verify set_feedback_db wires the database correctly."""
        from gateway.triage_feedback import set_feedback_db
        from gateway import triage_feedback
        
        # Re-wire the DB
        set_feedback_db(db_connection)
        assert triage_feedback._db is not None, "set_feedback_db should wire the database"
        print("set_feedback_db successfully wired")
    
    def test_track_triage_message(self, db_connection):
        """Test tracking a triage message in the database."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, track_triage_message
            set_feedback_db(db_connection)
            
            channel = "TEST_CHANNEL_001"
            message_ts = "1234567890.123456"
            summary = "Test summary: You have a new email from Alice about the Q4 report."
            
            # Clean up first
            await db_connection.triage_messages.delete_many({"channel": channel})
            
            await track_triage_message(channel, message_ts, summary)
            
            # Verify the message was stored
            doc = await db_connection.triage_messages.find_one(
                {"channel": channel, "message_ts": message_ts},
                {"_id": 0}
            )
            assert doc is not None, "Tracked message not found in database"
            assert doc["channel"] == channel
            assert doc["message_ts"] == message_ts
            assert doc["summary_preview"] == summary[:500]
            assert doc["feedback"] is None  # No feedback yet
            assert "sent_at" in doc
            print(f"Message tracked: channel={channel}, ts={message_ts}")
            
            # Cleanup
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_record_feedback_positive_thumbsup(self, db_connection):
        """Test recording positive feedback with thumbsup reaction."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, track_triage_message, record_feedback
            set_feedback_db(db_connection)
            
            channel = "TEST_CHANNEL_002"
            message_ts = "1234567891.000001"
            
            # Clean and track
            await db_connection.triage_messages.delete_many({"channel": channel})
            await track_triage_message(channel, message_ts, "Test positive feedback")
            
            # Record positive feedback
            matched = await record_feedback(channel, message_ts, "thumbsup", "U12345")
            assert matched is True, "record_feedback should return True when matched"
            
            # Verify feedback was stored
            doc = await db_connection.triage_messages.find_one({"channel": channel, "message_ts": message_ts}, {"_id": 0})
            assert doc["feedback"] == "positive", f"Expected 'positive', got {doc['feedback']}"
            assert doc["feedback_reaction"] == "thumbsup"
            assert doc["feedback_user"] == "U12345"
            print("Positive feedback (thumbsup) recorded correctly")
            
            # Cleanup
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_record_feedback_positive_plus_one(self, db_connection):
        """Test recording positive feedback with +1 reaction."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, track_triage_message, record_feedback
            set_feedback_db(db_connection)
            
            channel = "TEST_CHANNEL_003"
            message_ts = "1234567892.000002"
            
            await db_connection.triage_messages.delete_many({"channel": channel})
            await track_triage_message(channel, message_ts, "Test +1 feedback")
            matched = await record_feedback(channel, message_ts, "+1", "U12345")
            
            assert matched is True
            doc = await db_connection.triage_messages.find_one({"channel": channel, "message_ts": message_ts}, {"_id": 0})
            assert doc["feedback"] == "positive", "+1 should map to positive"
            print("Positive feedback (+1) recorded correctly")
            
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_record_feedback_negative_thumbsdown(self, db_connection):
        """Test recording negative feedback with thumbsdown reaction."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, track_triage_message, record_feedback
            set_feedback_db(db_connection)
            
            channel = "TEST_CHANNEL_004"
            message_ts = "1234567893.000003"
            
            await db_connection.triage_messages.delete_many({"channel": channel})
            await track_triage_message(channel, message_ts, "Test negative feedback")
            matched = await record_feedback(channel, message_ts, "thumbsdown", "U12345")
            
            assert matched is True
            doc = await db_connection.triage_messages.find_one({"channel": channel, "message_ts": message_ts}, {"_id": 0})
            assert doc["feedback"] == "negative", "thumbsdown should map to negative"
            print("Negative feedback (thumbsdown) recorded correctly")
            
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_record_feedback_negative_minus_one(self, db_connection):
        """Test recording negative feedback with -1 reaction."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, track_triage_message, record_feedback
            set_feedback_db(db_connection)
            
            channel = "TEST_CHANNEL_005"
            message_ts = "1234567894.000004"
            
            await db_connection.triage_messages.delete_many({"channel": channel})
            await track_triage_message(channel, message_ts, "Test -1 feedback")
            matched = await record_feedback(channel, message_ts, "-1", "U12345")
            
            assert matched is True
            doc = await db_connection.triage_messages.find_one({"channel": channel, "message_ts": message_ts}, {"_id": 0})
            assert doc["feedback"] == "negative", "-1 should map to negative"
            print("Negative feedback (-1) recorded correctly")
            
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_record_feedback_rejects_unknown_reactions(self, db_connection):
        """Test that unknown reactions (not thumbsup/thumbsdown/+1/-1) are rejected."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, track_triage_message, record_feedback
            set_feedback_db(db_connection)
            
            channel = "TEST_CHANNEL_006"
            message_ts = "1234567895.000005"
            
            await db_connection.triage_messages.delete_many({"channel": channel})
            await track_triage_message(channel, message_ts, "Test unknown reaction")
            
            # Try invalid reactions
            for reaction in ["heart", "smile", "fire", "rocket", "eyes", "pray"]:
                matched = await record_feedback(channel, message_ts, reaction, "U12345")
                assert matched is False, f"Reaction '{reaction}' should be rejected"
            
            # Verify no feedback was recorded
            doc = await db_connection.triage_messages.find_one({"channel": channel, "message_ts": message_ts}, {"_id": 0})
            assert doc["feedback"] is None, "Unknown reactions should not set feedback"
            print("Unknown reactions correctly rejected: heart, smile, fire, rocket, eyes, pray")
            
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_record_feedback_returns_false_for_untracked_message(self, db_connection):
        """Test that recording feedback on an untracked message returns False."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, record_feedback
            set_feedback_db(db_connection)
            
            matched = await record_feedback("NONEXISTENT_CHANNEL", "9999999999.999999", "thumbsup", "U12345")
            assert matched is False, "Should return False for untracked message"
            print("Correctly returned False for untracked message")
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_get_feedback_stats_structure(self, db_connection):
        """Test get_feedback_stats returns proper structure."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, get_feedback_stats
            set_feedback_db(db_connection)
            
            stats = await get_feedback_stats(days=30)
            
            # Check required fields
            assert "total" in stats, "Stats should have 'total' field"
            assert "positive" in stats, "Stats should have 'positive' field"
            assert "negative" in stats, "Stats should have 'negative' field"
            assert "pending" in stats, "Stats should have 'pending' field"
            assert "approval_rate" in stats, "Stats should have 'approval_rate' field"
            assert "rated_count" in stats, "Stats should have 'rated_count' field"
            assert "days" in stats, "Stats should have 'days' field"
            
            assert isinstance(stats["total"], int)
            assert isinstance(stats["positive"], int)
            assert isinstance(stats["negative"], int)
            assert stats["days"] == 30
            print(f"Feedback stats structure verified: {stats}")
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_get_recent_feedback_structure(self, db_connection):
        """Test get_recent_feedback returns proper structure."""
        async def run_test():
            from gateway.triage_feedback import set_feedback_db, get_recent_feedback
            set_feedback_db(db_connection)
            
            entries = await get_recent_feedback(limit=10)
            
            assert isinstance(entries, list), "get_recent_feedback should return a list"
            # If there are entries, verify structure
            if entries:
                entry = entries[0]
                # Should NOT include _id
                assert "_id" not in entry, "Entries should exclude MongoDB _id"
                assert "feedback" in entry
                print(f"Recent feedback entries: {len(entries)}")
            else:
                print("No recent feedback entries yet (expected in fresh environment)")
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_build_feedback_prompt_section_with_enough_ratings(self, db_connection):
        """Test build_feedback_prompt_section generates content when >= 3 ratings exist."""
        async def run_test():
            from gateway.triage_feedback import (
                set_feedback_db, track_triage_message, record_feedback,
                build_feedback_prompt_section, get_feedback_stats
            )
            set_feedback_db(db_connection)
            
            # Create 5 test messages with ratings for this test
            test_channel = "TEST_FEEDBACK_BUILD_001"
            base_ts = 9900000000.0
            
            # Clean up first
            await db_connection.triage_messages.delete_many({"channel": test_channel})
            
            for i in range(5):
                ts = f"{base_ts + i:.6f}"
                await track_triage_message(test_channel, ts, f"Test summary {i}")
                # Mix of positive and negative feedback
                reaction = "thumbsup" if i % 2 == 0 else "thumbsdown"
                await record_feedback(test_channel, ts, reaction, f"U{i}")
            
            stats = await get_feedback_stats(days=30)
            print(f"Stats after seeding: {stats}")
            
            # Now build the prompt section
            section = await build_feedback_prompt_section()
            
            if stats.get("rated_count", 0) >= 3:
                # Should have content now
                assert len(section) > 0, "Should generate feedback prompt section with >= 3 ratings"
                assert "## Feedback from Previous Summaries" in section
                print(f"Feedback prompt section generated (len={len(section)})")
            else:
                print("Not enough ratings in DB for feedback section generation")
            
            # Cleanup
            await db_connection.triage_messages.delete_many({"channel": test_channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestSlackNotifyToolIntegration:
    """Verify slack_notify tool has request_feedback parameter and FEEDBACK_FOOTER."""
    
    def test_slack_notify_has_request_feedback_parameter(self):
        """Verify slack_notify tool schema includes request_feedback."""
        from gateway.tools.slack_notify import SlackNotifyTool
        tool = SlackNotifyTool()
        
        # Check parameters schema
        params = tool.parameters
        assert "properties" in params
        assert "request_feedback" in params["properties"], "request_feedback parameter missing"
        
        rf_param = params["properties"]["request_feedback"]
        assert rf_param["type"] == "boolean", "request_feedback should be boolean type"
        print(f"request_feedback parameter found: {rf_param}")
    
    def test_feedback_footer_constant_exists(self):
        """Verify FEEDBACK_FOOTER constant exists with thumbsup/thumbsdown text."""
        from gateway.tools.slack_notify import FEEDBACK_FOOTER
        
        assert FEEDBACK_FOOTER is not None
        assert "thumbsup" in FEEDBACK_FOOTER, "FEEDBACK_FOOTER should mention thumbsup"
        assert "thumbsdown" in FEEDBACK_FOOTER, "FEEDBACK_FOOTER should mention thumbsdown"
        print(f"FEEDBACK_FOOTER verified: {FEEDBACK_FOOTER}")


class TestSlackChannelReactionHandler:
    """Verify Slack channel has reaction_added event handler."""
    
    def test_reaction_added_handler_exists(self):
        """Verify the _process_reaction method exists in SlackChannel."""
        from gateway.channels.slack_channel import SlackChannel
        
        channel = SlackChannel()
        assert hasattr(channel, '_process_reaction'), "SlackChannel should have _process_reaction method"
        assert callable(channel._process_reaction), "_process_reaction should be callable"
        print("_process_reaction method found in SlackChannel")


class TestTriageFeedbackRPCMethods:
    """Test RPC methods triage.feedback_stats and triage.recent_feedback."""
    
    def test_triage_feedback_stats_rpc_registered(self):
        """Verify triage.feedback_stats RPC method is registered."""
        from gateway.methods import get_method
        
        handler = get_method("triage.feedback_stats")
        assert handler is not None, "triage.feedback_stats RPC method not registered"
        print("triage.feedback_stats RPC method is registered")
    
    def test_triage_recent_feedback_rpc_registered(self):
        """Verify triage.recent_feedback RPC method is registered."""
        from gateway.methods import get_method
        
        handler = get_method("triage.recent_feedback")
        assert handler is not None, "triage.recent_feedback RPC method not registered"
        print("triage.recent_feedback RPC method is registered")


class TestSchedulerFeedbackInjection:
    """Verify scheduler injects feedback context for email-triage task."""
    
    def test_scheduler_has_feedback_injection_logic(self):
        """Verify _execute_task checks for email-triage and injects feedback."""
        import inspect
        from gateway.scheduler import TaskScheduler
        
        # Get the source of _execute_task method
        source = inspect.getsource(TaskScheduler._execute_task)
        
        assert "email-triage" in source, "Scheduler should check for email-triage task"
        assert "build_triage_prompt_with_feedback" in source, "Scheduler should call build_triage_prompt_with_feedback"
        print("Scheduler feedback injection logic verified in _execute_task")


class TestDbNullCheckPattern:
    """Verify all _db checks use 'is None' pattern."""
    
    def test_triage_feedback_uses_is_none_pattern(self):
        """Verify triage_feedback module uses '_db is None' not 'if not _db'."""
        import inspect
        from gateway import triage_feedback
        
        source = inspect.getsource(triage_feedback)
        
        # Should use 'is None' pattern
        assert "_db is None" in source, "Should use '_db is None' pattern"
        print("triage_feedback uses correct '_db is None' pattern")


class TestEndToEndFeedbackFlow:
    """End-to-end test: track message -> record feedback -> verify stats update."""
    
    def test_full_feedback_flow(self, db_connection):
        """Test complete flow: track -> feedback -> stats -> prompt section."""
        async def run_test():
            from gateway.triage_feedback import (
                set_feedback_db, track_triage_message, record_feedback,
                get_feedback_stats, get_recent_feedback, build_feedback_prompt_section
            )
            set_feedback_db(db_connection)
            
            # Step 1: Track 5 messages
            channel = "E2E_TEST_CHANNEL"
            
            # Clean up first
            await db_connection.triage_messages.delete_many({"channel": channel})
            
            messages = []
            for i in range(5):
                ts = f"1700000000.{i:06d}"
                summary = f"E2E test summary #{i}: Important email about project X"
                await track_triage_message(channel, ts, summary)
                messages.append(ts)
                print(f"Tracked message {i}: ts={ts}")
            
            # Verify all messages tracked
            count = await db_connection.triage_messages.count_documents({"channel": channel})
            assert count == 5, f"Expected 5 tracked messages, got {count}"
            
            # Step 2: Record feedback on messages
            # 3 positive, 2 negative -> 60% approval rate
            await record_feedback(channel, messages[0], "thumbsup", "USER_001")
            await record_feedback(channel, messages[1], "+1", "USER_002")
            await record_feedback(channel, messages[2], "thumbsup", "USER_003")
            await record_feedback(channel, messages[3], "thumbsdown", "USER_004")
            await record_feedback(channel, messages[4], "-1", "USER_005")
            
            # Step 3: Verify stats
            stats = await get_feedback_stats(days=30)
            print(f"Stats after E2E feedback: {stats}")
            
            assert stats["positive"] >= 3, f"Expected >= 3 positive, got {stats['positive']}"
            assert stats["negative"] >= 2, f"Expected >= 2 negative, got {stats['negative']}"
            
            # Step 4: Verify recent feedback
            recent = await get_recent_feedback(limit=10)
            assert len(recent) >= 5, f"Expected >= 5 recent entries, got {len(recent)}"
            
            # Step 5: Build prompt section
            section = await build_feedback_prompt_section()
            assert len(section) > 0, "Should generate feedback section with 5+ ratings"
            assert "Feedback from Previous Summaries" in section
            print(f"E2E flow complete. Prompt section length: {len(section)}")
            
            # Cleanup
            await db_connection.triage_messages.delete_many({"channel": channel})
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestFeedbackAutoTuningLogic:
    """Verify auto-tuning logic in build_feedback_prompt_section."""
    
    def test_auto_tuning_adjusts_based_on_approval_rate(self):
        """Verify prompt section includes appropriate guidance based on approval rate."""
        import inspect
        from gateway.triage_feedback import build_feedback_prompt_section
        
        source = inspect.getsource(build_feedback_prompt_section)
        
        # Check for auto-tuning thresholds
        assert "< 60" in source, "Should have < 60% threshold for dissatisfied guidance"
        assert ">= 80" in source, "Should have >= 80% threshold for satisfied guidance"
        
        # Check for guidance text
        assert "NOT satisfied" in source, "Should include 'NOT satisfied' guidance for low approval"
        assert "maintain" in source.lower(), "Should include 'maintain' guidance for high approval"
        assert "mixed" in source.lower(), "Should include 'mixed' guidance for medium approval"
        
        print("Auto-tuning logic verified: <60%, >=80%, and mixed thresholds present")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
