from app.db import models  # noqa: F401
from app.db.base import Base
from app.workers.scheduler import SchedulerSettings
from app.workers.settings import WorkerSettings


def test_database_metadata_and_worker_settings_load() -> None:
    assert Base.metadata.naming_convention is not None
    assert "users" in Base.metadata.tables
    assert WorkerSettings.functions
    assert SchedulerSettings.cron_jobs
