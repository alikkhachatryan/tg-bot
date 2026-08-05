from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.workers.tasks import scheduler_heartbeat


class SchedulerSettings:
    functions: ClassVar[list[object]] = [scheduler_heartbeat]
    cron_jobs: ClassVar[list[object]] = [
        cron(scheduler_heartbeat, minute={0, 15, 30, 45}, unique=True)
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1
    job_timeout = 60
    max_tries = 2
