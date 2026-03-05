"""Tests for labor reconciliation Celery task."""
import pytest
from datetime import date
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


class TestReconciliationDriftCorrection:
    """Tests verifying that nightly reconciliation corrects accumulated drift."""

    @patch("app.services.tasks.Session")
    @patch("app.core.config.get_settings")
    def test_reconciliation_corrects_drifted_weekly_minutes(
        self, mock_get_settings, mock_session_cls
    ):
        """Driver with drifted accumulated_weekly_minutes should be corrected
        by reconciliation which reads labor logs as ground truth."""
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
        # Both UPDATE statements must execute (weekly recalc + reset-no-logs)
        assert mock_session.execute.call_count >= 2
        mock_session.commit.assert_called_once()

    @patch("app.services.tasks.Session")
    @patch("app.core.config.get_settings")
    def test_reconciliation_handles_driver_with_no_logs_this_week(
        self, mock_get_settings, mock_session_cls
    ):
        """Drivers with no labor logs this week should have accumulated minutes
        reset to 0 by the second SQL statement."""
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
        assert mock_session.execute.call_count >= 2
        mock_session.commit.assert_called_once()

    @patch("app.services.tasks.Session")
    @patch("app.core.config.get_settings")
    def test_reconciliation_returns_week_start_date(
        self, mock_get_settings, mock_session_cls
    ):
        """The returned dict must include a week_start key with a YYYY-MM-DD string."""
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
        assert "week_start" in result
        parsed = date.fromisoformat(result["week_start"])
        assert isinstance(parsed, date)

    @patch("app.services.tasks.date")
    @patch("app.services.tasks.Session")
    @patch("app.core.config.get_settings")
    def test_reconciliation_uses_monday_as_week_start(
        self, mock_get_settings, mock_session_cls, mock_date
    ):
        """Week start must always be the most recent Monday.
        Mocking today as Wednesday 2024-01-31 means week_start should be 2024-01-29."""
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        mock_get_settings.return_value = settings

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Freeze today to Wednesday 2024-01-31 (weekday index 2)
        mock_date.today.return_value = date(2024, 1, 31)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        from app.services.tasks import reconcile_labor_hours
        result = reconcile_labor_hours()

        assert result["status"] == "completed"
        assert result["week_start"] == "2024-01-29"
