from app.db.base import Base
from app.workers.scheduler import SchedulerSettings
from app.workers.settings import WorkerSettings


def test_database_metadata_and_worker_settings_load() -> None:
    assert Base.metadata.naming_convention is not None
    assert WorkerSettings.functions
    assert SchedulerSettings.cron_jobs
