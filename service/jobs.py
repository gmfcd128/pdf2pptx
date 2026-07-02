import enum
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    input_path: Path
    output_path: Path
    status: JobStatus = JobStatus.QUEUED
    progress: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class JobStore:
    """In-memory job registry, keyed by job id.

    Fine for a single-replica container serializing GPU work through one worker.
    If this service is ever scaled to multiple replicas, this (and the in-process
    asyncio.Queue in service/main.py) need to move to a shared store/queue
    (e.g. Redis) instead.
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create(self, job_id: str, input_path, output_path) -> Job:
        job = Job(id=job_id, input_path=Path(input_path), output_path=Path(output_path))
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)
