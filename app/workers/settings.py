from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.workers.tasks import worker_healthcheck


class WorkerSettings:
    functions: ClassVar[list[object]] = [worker_healthcheck]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
    job_timeout = 300
    max_tries = 3
    health_check_interval = 30
