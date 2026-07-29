from __future__ import annotations

import argparse
import asyncio
import os
import signal
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.data_source.crawler.base import crawler_settings
from app.data_source.crawler.crawl4ai_client import (
    ensure_crawl4ai_available,
    ensure_playwright_chromium_available,
)
from app.data_source.crawler.runtime import utc_now, write_worker_health
from app.data_source.crawler.service import process_crawl_task_ids
from app.models import CrawlTaskRecord


class CrawlerWorker:
    def __init__(self, *, poll_seconds: int = 3, stale_task_seconds: int = 900):
        self.poll_seconds = max(1, poll_seconds)
        self.stale_task_seconds = max(60, stale_task_seconds)
        self.running = True
        self.last_task_id: int | None = None
        self.last_error: str | None = None
        self.browser_ready = False

    def stop(self, *_: Any) -> None:
        self.running = False

    def verify_runtime(self) -> None:
        ensure_crawl4ai_available()
        ensure_playwright_chromium_available()
        self.browser_ready = True

    def recover_stale_tasks(self) -> int:
        cutoff = utc_now() - timedelta(seconds=self.stale_task_seconds)
        with SessionLocal() as db:
            result = db.execute(
                update(CrawlTaskRecord)
                .where(
                    CrawlTaskRecord.status == "running",
                    CrawlTaskRecord.started_at.is_not(None),
                    CrawlTaskRecord.started_at < cutoff,
                )
                .values(status="pending", started_at=None, error_message="独立 Worker 重启后重新排队")
            )
            db.commit()
            return int(result.rowcount or 0)

    def claim_next_task(self) -> int | None:
        with SessionLocal() as db:
            task = db.scalar(
                select(CrawlTaskRecord)
                .where(CrawlTaskRecord.status == "pending")
                .order_by(CrawlTaskRecord.created_at.asc(), CrawlTaskRecord.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not task:
                return None
            task.status = "running"
            task.started_at = utc_now()
            task.error_message = None
            task_id = task.id
            db.commit()
            return task_id

    def heartbeat(self, *, status: str = "ok", message: str = "独立爬虫 Worker 运行正常") -> None:
        write_worker_health(
            {
                "service": "esports-site-selection-crawler",
                "pid": os.getpid(),
                "status": status,
                "message": message,
                "browser_ready": self.browser_ready,
                "last_task_id": self.last_task_id,
                "last_error": self.last_error,
            }
        )

    async def run(self, *, once: bool = False) -> None:
        try:
            await asyncio.to_thread(self.verify_runtime)
            recovered = self.recover_stale_tasks()
            message = (
                f"独立爬虫 Worker 运行正常；恢复 {recovered} 个中断任务"
                if recovered
                else "独立爬虫 Worker 运行正常"
            )
            self.heartbeat(message=message)
        except Exception as exc:
            self.last_error = str(exc)
            self.heartbeat(status="failed", message=f"爬虫运行时不可用：{exc}")
            raise

        while self.running:
            if not crawler_settings().enabled:
                self.heartbeat(status="disabled", message="爬虫 Worker 已安装，配置中心尚未启用爬虫")
                if once:
                    return
                await asyncio.sleep(self.poll_seconds)
                continue

            task_id = self.claim_next_task()
            if task_id is None:
                self.heartbeat()
                if once:
                    return
                await asyncio.sleep(self.poll_seconds)
                continue

            self.last_task_id = task_id
            self.last_error = None
            self.heartbeat(message=f"正在处理爬虫任务 {task_id}")
            try:
                await process_crawl_task_ids([task_id])
            except Exception as exc:
                self.last_error = str(exc)
                with SessionLocal() as db:
                    task = db.get(CrawlTaskRecord, task_id)
                    if task:
                        task.status = "failed"
                        task.error_message = f"Worker执行失败：{exc}"
                        task.finished_at = utc_now()
                        db.commit()
            finally:
                self.heartbeat()
            if once:
                return


def main() -> None:
    parser = argparse.ArgumentParser(description="电竞馆智能选址系统独立爬虫 Worker")
    parser.add_argument("--once", action="store_true", help="最多处理一个任务后退出")
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("CRAWLER_WORKER_POLL_SECONDS", "3")))
    parser.add_argument(
        "--stale-task-seconds",
        type=int,
        default=int(os.getenv("CRAWLER_STALE_TASK_SECONDS", "900")),
    )
    args = parser.parse_args()
    worker = CrawlerWorker(poll_seconds=args.poll_seconds, stale_task_seconds=args.stale_task_seconds)
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    asyncio.run(worker.run(once=args.once))


if __name__ == "__main__":
    main()
