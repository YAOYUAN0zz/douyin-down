"""纯 Python 的后台下载任务模型，不依赖 FastAPI。

将 job 生命周期从 HTTP 层解耦，便于被 CLI 以外的入口复用（如未来的 MCP server）。

持久化：终态 job（success/partial/failed/cancelled）写入 storage.database 的 job 表，
服务重启后由 load_persisted() 恢复；pending/running 只存在于内存。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

JobExecutor = Callable[["DownloadJob"], Awaitable[Dict[str, int]]]


def _now_iso() -> str:
    # 统一使用 timezone-aware UTC ISO-8601 字符串
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # 跑完但部分条目失败
    FAILED = "failed"
    CANCELLED = "cancelled"

    TERMINAL = frozenset({SUCCESS, PARTIAL, FAILED, CANCELLED})


class DownloadJob:
    def __init__(self, job_id: str, url: str, options: Optional[Dict[str, Any]] = None):
        self.job_id = job_id
        self.url = url
        # 每任务下载选项（如 video_quality 画质覆盖），None 表示跟随全局配置
        self.options = options or None
        self.status = JobStatus.PENDING
        self.created_at = _now_iso()
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        # 单调时钟时间戳，用于 TTL / LRU 剪裁（不受系统时钟跳变影响）
        self.finished_monotonic: Optional[float] = None
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.error: Optional[str] = None
        # 实时进度：由 JobProgressReporter 从下载器回调写入，随 /jobs 轮询下发
        self.progress: Dict[str, Any] = {
            "step": "",
            "detail": "",
            "items_total": 0,
            "items_done": 0,
            "current": None,  # {"aweme_id", "bytes_read", "bytes_total"}
            "output_dir": None,
            "author": None,
        }
        self._task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "options": self.options,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "error": self.error,
            "progress": dict(self.progress, current=self.progress.get("current")),
        }

    @classmethod
    def from_persisted(cls, row: Dict[str, Any]) -> "DownloadJob":
        """从数据库行恢复终态 job（进度字段不恢复）。"""
        job = cls(job_id=str(row.get("job_id")), url=str(row.get("url") or ""))
        job.options = row.get("overrides") or None
        job.status = str(row.get("status") or JobStatus.FAILED)
        job.created_at = str(row.get("created_at") or "")
        job.started_at = row.get("started_at")
        job.finished_at = row.get("finished_at")
        job.total = int(row.get("total") or 0)
        job.success = int(row.get("success") or 0)
        job.failed = int(row.get("failed") or 0)
        job.skipped = int(row.get("skipped") or 0)
        job.error = row.get("error")
        if row.get("author_nickname"):
            job.progress["author"] = row.get("author_nickname")
        return job


class JobProgressReporter:
    """把下载器的进度回调写进 DownloadJob，供 /jobs 轮询展示。

    实现 core.downloader_base.ProgressReporter 协议及其可选扩展回调
    （on_item_progress / on_output_dir / on_author）。所有方法都在事件循环
    线程内被同步调用，直接改 job 字段即可，无需加锁。
    """

    def __init__(self, job: "DownloadJob"):
        self.job = job

    def update_step(self, step: str, detail: str = "") -> None:
        self.job.progress["step"] = step
        self.job.progress["detail"] = detail

    def set_item_total(self, total: int, detail: str = "") -> None:
        self.job.progress["items_total"] = int(total or 0)
        if detail:
            self.job.progress["detail"] = detail

    def advance_item(self, status: str, detail: str = "") -> None:
        self.job.progress["items_done"] = int(self.job.progress.get("items_done") or 0) + 1
        # 一条作品收尾后清掉字节进度，避免下一条开始前显示旧文件的数字
        self.job.progress["current"] = None

    def on_item_progress(self, *, aweme_id: str, bytes_read: int, bytes_total: int) -> None:
        self.job.progress["current"] = {
            "aweme_id": aweme_id,
            "bytes_read": int(bytes_read or 0),
            "bytes_total": int(bytes_total or 0),
        }

    def on_output_dir(self, *, path: str) -> None:
        self.job.progress["output_dir"] = path

    def on_author(self, *, nickname: Optional[str] = None, sec_uid: Optional[str] = None) -> None:
        if nickname:
            self.job.progress["author"] = nickname


class JobManager:
    """内存 job 存储 + 并发执行器，带 TTL + 容量上限 + 可选 SQLite 持久化。

    剪裁策略：
    - 每次 submit 前先剪裁一次：
        a. 丢弃 finished_monotonic 超过 job_ttl_seconds 的终态 job；
          （从数据库恢复的 job 无 finished_monotonic，不参与 TTL 剪裁）
        b. 若剩余总数仍超过 max_jobs，按 finished_monotonic 升序淘汰最老的终态 job；
        c. in-flight（pending/running）job 永不淘汰。
    - 内存剪裁不删数据库行；数据库行只在 delete/clear 时删除。
    """

    DEFAULT_MAX_JOBS = 500
    DEFAULT_JOB_TTL_SECONDS = 24 * 3600  # 24 小时

    def __init__(
        self,
        executor: JobExecutor,
        *,
        max_concurrency: int = 2,
        max_jobs: int = DEFAULT_MAX_JOBS,
        job_ttl_seconds: float = DEFAULT_JOB_TTL_SECONDS,
        database: Optional[Any] = None,
    ):
        self.executor = executor
        self.database = database
        self._jobs: Dict[str, DownloadJob] = {}
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._lock = asyncio.Lock()
        self.max_jobs = max(1, int(max_jobs))
        self.job_ttl_seconds = max(0.0, float(job_ttl_seconds))

    async def load_persisted(self) -> int:
        """启动时从数据库恢复终态 job（最新的 max_jobs 条）。"""
        if self.database is None:
            return 0
        rows = await self.database.load_terminal_jobs(limit=self.max_jobs)
        restored = 0
        async with self._lock:
            for row in rows:
                job = DownloadJob.from_persisted(row)
                if job.job_id and job.job_id not in self._jobs:
                    self._jobs[job.job_id] = job
                    restored += 1
        return restored

    async def submit(self, url: str, options: Optional[Dict[str, Any]] = None) -> DownloadJob:
        job_id = uuid.uuid4().hex[:12]
        job = DownloadJob(job_id=job_id, url=url, options=options)
        async with self._lock:
            self._prune_locked()
            self._jobs[job_id] = job
        # 异步调度，立即返回 job 给调用方
        job._task = asyncio.create_task(self._run(job))
        return job

    async def cancel(self, job_id: str) -> Optional[DownloadJob]:
        """取消 in-flight job。返回 job；不存在返回 None；已终态抛 ValueError。"""
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status in JobStatus.TERMINAL:
            raise ValueError("job already finished")
        if job._task is not None and not job._task.done():
            job._task.cancel()
            # 等待任务收尾（_run 的 CancelledError 分支落终态并持久化）
            try:
                await job._task
            except asyncio.CancelledError:
                pass
        # 兜底：task 已 done 但状态未落（不应发生）
        if job.status not in JobStatus.TERMINAL:
            job.status = JobStatus.CANCELLED
            job.finished_at = _now_iso()
            job.finished_monotonic = time.monotonic()
            await self._persist(job)
        return job

    async def retry(self, job_id: str) -> Optional[DownloadJob]:
        """以原参数重建一个新 job。原 job 不存在返回 None；未终态抛 ValueError。"""
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status not in JobStatus.TERMINAL:
            raise ValueError("job still in flight")
        return await self.submit(job.url, options=dict(job.options) if job.options else None)

    async def delete(self, job_id: str) -> Optional[DownloadJob]:
        """删除终态 job（内存 + 数据库）。不存在返回 None；未终态抛 ValueError。"""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status not in JobStatus.TERMINAL:
                raise ValueError("job still in flight")
            self._jobs.pop(job_id, None)
        if self.database is not None:
            await self.database.delete_jobs([job_id])
        return job

    async def clear_finished(self) -> int:
        """清空全部终态 job（内存 + 数据库），返回清除数量。"""
        async with self._lock:
            terminal_ids = [
                jid for jid, j in self._jobs.items() if j.status in JobStatus.TERMINAL
            ]
            for jid in terminal_ids:
                self._jobs.pop(jid, None)
        if self.database is not None and terminal_ids:
            await self.database.delete_jobs(terminal_ids)
        return len(terminal_ids)

    def _prune_locked(self) -> None:
        """持锁内调用：按 TTL + 容量上限剪裁终态 job（仅内存）。"""
        now = time.monotonic()

        # 1) TTL
        if self.job_ttl_seconds > 0:
            expired_ids = [
                jid
                for jid, j in self._jobs.items()
                if j.status in JobStatus.TERMINAL
                and j.finished_monotonic is not None
                and (now - j.finished_monotonic) > self.job_ttl_seconds
            ]
            for jid in expired_ids:
                self._jobs.pop(jid, None)

        # 2) 容量上限：只淘汰终态 job，保留 in-flight
        if len(self._jobs) < self.max_jobs:
            return
        terminal_jobs = [
            (j.finished_monotonic or 0.0, jid)
            for jid, j in self._jobs.items()
            if j.status in JobStatus.TERMINAL
        ]
        terminal_jobs.sort(key=lambda pair: pair[0])
        overflow = len(self._jobs) - self.max_jobs + 1  # +1 是为新 job 腾位
        for _, jid in terminal_jobs[:overflow]:
            self._jobs.pop(jid, None)

    async def _persist(self, job: DownloadJob) -> None:
        if self.database is None:
            return
        try:
            payload = job.to_dict()
            payload["author_nickname"] = job.progress.get("author")
            payload["overrides"] = job.options
            await self.database.upsert_job(payload)
        except Exception:
            # 持久化失败不阻断任务收尾；下次终态写入会重试
            pass

    async def _run(self, job: DownloadJob) -> None:
        try:
            async with self._semaphore:
                job.status = JobStatus.RUNNING
                job.started_at = _now_iso()
                try:
                    counts = await self.executor(job)
                    job.total = int(counts.get("total", 0))
                    job.success = int(counts.get("success", 0))
                    job.failed = int(counts.get("failed", 0))
                    job.skipped = int(counts.get("skipped", 0))
                    if job.failed == 0:
                        job.status = JobStatus.SUCCESS
                    elif job.success > 0 or job.skipped > 0:
                        # 部分条目失败：与全军覆没区分开
                        job.status = JobStatus.PARTIAL
                    else:
                        job.status = JobStatus.FAILED
                except Exception as exc:
                    job.status = JobStatus.FAILED
                    job.error = f"{type(exc).__name__}: {exc}"
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
        finally:
            job.finished_at = _now_iso()
            job.finished_monotonic = time.monotonic()
            # shield：cancel() 引发的 CancelledError 不应打断持久化写入
            await asyncio.shield(self._persist(job))

    async def get(self, job_id: str) -> Optional[DownloadJob]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_jobs(self) -> List[DownloadJob]:
        async with self._lock:
            return list(self._jobs.values())

    async def shutdown(self) -> None:
        """等待所有 pending/running 任务结束。"""
        tasks = [j._task for j in self._jobs.values() if j._task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
