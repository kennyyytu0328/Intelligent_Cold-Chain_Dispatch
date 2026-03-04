"""Tests for labor reconciliation Celery task."""
import pytest
from unittest.mock import patch, MagicMock


class TestReconcileLaborHours:
    @patch("app.core.config.get_settings")
    def test_early_return_when_disabled(self, mock_get_settings):
        """Reconciliation should do nothing when labor is disabled."""
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_get_settings.return_value = settings

        from app.services.tasks import reconcile_labor_hours
        result = reconcile_labor_hours()

        assert result == {"status": "skipped", "reason": "labor dimension disabled"}

    @patch("app.services.tasks.Session")
    @patch("app.core.config.get_settings")
    def test_reconciliation_runs_when_enabled(self, mock_get_settings, mock_session_cls):
        """Reconciliation should execute SQL when labor is enabled."""
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        mock_get_settings.return_value = settings

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        from app.services.tasks import reconcile_labor_hours
        result = reconcile_labor_hours()

        assert result["status"] == "completed"
        mock_session.execute.assert_called()
        mock_session.commit.assert_called()
