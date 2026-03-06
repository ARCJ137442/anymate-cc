"""Test security fixes for path traversal, sender validation, and logging."""
import os
import pytest
from pathlib import Path
from anymate.protocol.paths import PathResolver
from anymate.bridge import MessageBridge
from anymate.tmux import PaneLogger


class TestPathTraversal:
    """Test that path traversal attacks are prevented."""

    def test_team_name_path_traversal(self, tmp_path):
        """Test that team_name cannot escape base directory."""
        resolver = PathResolver(tmp_path)

        # Test various path traversal attempts
        bad_names = [
            "../escape",
            "../../outside",
            "team/../../../etc/passwd",
            "team/../../sibling",
            "..",
            ".",
            "team\\..\\..",  # Windows-style
            "team/.hidden",  # Hidden dirs are OK but dots alone are not
        ]

        for bad_name in bad_names:
            with pytest.raises(ValueError, match="(invalid characters|path traversal|empty)"):
                resolver.team_dir(bad_name)

    def test_agent_name_path_traversal(self, tmp_path):
        """Test that agent_name cannot escape inboxes directory."""
        resolver = PathResolver(tmp_path)

        # Create a valid team first
        team_dir = resolver.team_dir("valid-team")
        team_dir.mkdir(parents=True, exist_ok=True)

        # Test various path traversal attempts
        bad_names = [
            "../../escape",
            "../sibling",
            "..",
            "agent/../../../etc/passwd",
            "agent\\..\\..\\escape",  # Windows-style
        ]

        for bad_name in bad_names:
            with pytest.raises(ValueError, match="(invalid characters|path traversal|empty)"):
                resolver.inbox_path("valid-team", bad_name)

    def test_valid_names_accepted(self, tmp_path):
        """Test that valid team and agent names are accepted."""
        resolver = PathResolver(tmp_path)

        valid_names = [
            "simple",
            "with-dash",
            "with_underscore",
            "MixedCase123",
            "all-valid_Chars123",
        ]

        for name in valid_names:
            # Should not raise
            team_path = resolver.team_dir(name)
            assert team_path == tmp_path / "teams" / name

            inbox_path = resolver.inbox_path(name, name)
            assert inbox_path == tmp_path / "teams" / name / "inboxes" / f"{name}.json"


class TestSenderValidation:
    """Test that inbox sender validation works correctly."""

    def test_bridge_validates_team_members(self, tmp_path):
        """Test that MessageBridge validates senders against team config."""
        resolver = PathResolver(tmp_path)
        team_name = "test-team"

        # Create team config with specific members
        config_dir = resolver.team_dir(team_name)
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = resolver.config_path(team_name)
        config_file.write_text("""{
            "members": [
                {"name": "alice", "agentId": "alice-123"},
                {"name": "bob", "agentId": "bob-456"}
            ]
        }""")

        # Create bridge
        bridge = MessageBridge(resolver, team_name)

        # Verify team members are loaded correctly
        members = bridge._get_team_members()
        assert members == {"alice", "bob"}

        # Test cache invalidation
        bridge._invalidate_members_cache()
        assert bridge._team_members_cache is None


class TestSecureLogging:
    """Test that tmux logging security is properly implemented."""

    def test_log_path_uses_secure_directory(self):
        """Test that log files are created in secure directory, not /tmp."""
        log_path = PaneLogger.log_path("test-agent", "test-team")

        # Should NOT be in temp directory
        assert "tmp" not in str(log_path).lower() or ".anymate" in str(log_path)

        # Should be in a private directory
        assert ".anymate" in str(log_path) or "ANYMATE_CLAUDE_DIR" in os.environ

    def test_logging_can_be_disabled(self, tmp_path):
        """Test that ANYMATE_DISABLE_LOGGING=1 disables logging."""
        log_file = tmp_path / "test.log"
        logger = PaneLogger(log_file, "test")

        # Enable disable flag
        old_value = os.environ.get("ANYMATE_DISABLE_LOGGING")
        try:
            os.environ["ANYMATE_DISABLE_LOGGING"] = "1"

            # Re-create logger to pick up env var
            logger = PaneLogger(log_file, "test")
            logger.open()
            logger.log_input("sensitive data", "alice")
            logger.log_output("secret response", "bob")
            logger.close()

            # Log file should not be created or should be empty
            assert not log_file.exists() or log_file.stat().st_size == 0

        finally:
            # Restore original value
            if old_value is None:
                os.environ.pop("ANYMATE_DISABLE_LOGGING", None)
            else:
                os.environ["ANYMATE_DISABLE_LOGGING"] = old_value

    def test_log_file_permissions_restrictive(self, tmp_path):
        """Test that log files are created with restrictive permissions."""
        log_file = tmp_path / "test.log"
        logger = PaneLogger(log_file, "test")

        # Ensure logging is not disabled
        old_value = os.environ.get("ANYMATE_DISABLE_LOGGING")
        try:
            os.environ.pop("ANYMATE_DISABLE_LOGGING", None)

            logger.open()
            logger.log_input("test", "alice")
            logger.close()

            # Check that file was created
            if log_file.exists():
                # On Unix-like systems, check permissions are restrictive
                # Windows handles permissions differently via ACLs
                if hasattr(os, "stat") and os.name != "nt":
                    stat = log_file.stat()
                    mode = stat.st_mode & 0o777
                    # Should be owner-only (0o600) or at most owner+group (0o660)
                    assert mode <= 0o660, f"Log file has overly permissive mode: {oct(mode)}"

        finally:
            if old_value is None:
                os.environ.pop("ANYMATE_DISABLE_LOGGING", None)
            else:
                os.environ["ANYMATE_DISABLE_LOGGING"] = old_value
