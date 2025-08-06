from abc import ABC, abstractmethod
from typing import Any

import httpx
from exceptions.task_exceptions import SchedulerException
from handler.redis_handler import low_prio_queue
from logger.logger import log
from rq.job import Job
from rq_scheduler import Scheduler
from utils.context import ctx_httpx_client

tasks_scheduler = Scheduler(queue=low_prio_queue, connection=low_prio_queue.connection)


class Task(ABC):
    title: str
    description: str
    enabled: bool
    manual_run: bool
    cron_string: str | None = None

    def __init__(
        self,
        title: str,
        description: str,
        enabled: bool = False,
        manual_run: bool = False,
        cron_string: str | None = None,
    ):
        self.title = title
        self.description = description or title
        self.enabled = enabled
        self.manual_run = manual_run
        self.cron_string = cron_string

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any: ...


class PeriodicTask(Task):
    def __init__(self, *args, func: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.func = func

    def _get_existing_job(self):
        existing_jobs = tasks_scheduler.get_jobs()
        for job in existing_jobs:
            if isinstance(job, Job) and job.func_name == self.func:
                return job

        return None

    def init(self):
        job = self._get_existing_job()

        if self.enabled and not job:
            return self.schedule()
        elif job and not self.enabled:
            return self.unschedule()

    def schedule(self):
        if not self.enabled:
            raise SchedulerException(f"Scheduled {self.description} is not enabled.")

        if self._get_existing_job():
            log.info(f"{self.description.capitalize()} is already scheduled.")
            return None

        if self.cron_string:
            return tasks_scheduler.cron(
                self.cron_string,
                func=self.func,
                repeat=None,
            )

        return None

    def unschedule(self):
        job = self._get_existing_job()

        if not job:
            log.info(f"{self.description.capitalize()} is not scheduled.")
            return None

        tasks_scheduler.cancel(job)
        log.info(f"{self.description.capitalize()} unscheduled.")


class RemoteFilePullTask(PeriodicTask):
    def __init__(self, *args, url: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.url = url

    async def run(self, force: bool = False) -> bytes | None:
        if not self.enabled and not force:
            log.info(f"Scheduled {self.description} not enabled, unscheduling...")
            self.unschedule()
            return None

        log.info(f"Scheduled {self.description} started...")

        httpx_client = ctx_httpx_client.get()
        try:
            response = await httpx_client.get(self.url, timeout=120)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as e:
            log.error(f"Scheduled {self.description} failed", exc_info=True)
            log.error(e)
            return None
