# app/scheduler.py
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, List, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from sqlalchemy import func

from app.models import SessionLocal, Subscription

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _utcnow_naive() -> datetime:
    # Храним и сравниваем naive UTC
    return datetime.utcnow()


def _fmt_rows(rows: List[Tuple[int, datetime]]) -> str:
    return ", ".join(f"{uid}:{(exp.isoformat() if exp else 'None')}" for uid, exp in rows)


def _remove_expired_subscriptions(on_expire: Callable[[int, str], None]) -> None:
    now = _utcnow_naive()
    log.info("[SCHED] Tick start | now=%s", now.isoformat())

    session = SessionLocal()
    try:
        # max(expires_at) по каждому user_id
        agg_rows: List[Tuple[int, datetime]] = (
            session.query(
                Subscription.user_id.label("uid"),
                func.max(Subscription.expires_at).label("max_exp"),
            )
            .group_by(Subscription.user_id)
            .all()
        )

        log.info("[SCHED] Max per user (uid:max_exp): %s", _fmt_rows(agg_rows))

        expired_uids: List[int] = []
        active_uids: List[int] = []

        for uid, max_exp in agg_rows:
            if max_exp is None:
                log.warning("[SCHED] user_id=%s has NULL max_exp — skip", uid)
                continue
            # Используем строго "<" (а не "<="), чтобы граничные значения не
            # пролетали между тиками из‑за микросекунд
            if max_exp < now:
                expired_uids.append(uid)
            else:
                active_uids.append(uid)

        log.info(
            "[SCHED] Summary: total=%d, active=%d, expired=%d",
            len(agg_rows), len(active_uids), len(expired_uids)
        )

        if not expired_uids:
            log.info("[SCHED] No expired users this tick")
            return

        # обрабатываем просроченных
        for uid in expired_uids:
            last_sub: Subscription = (
                session.query(Subscription)
                .filter(Subscription.user_id == uid)
                .order_by(Subscription.expires_at.desc())
                .first()
            )

            last_plan = last_sub.plan if last_sub else "-"
            last_exp  = last_sub.expires_at if last_sub else None

            log.info(
                "[SCHED] Expiring user_id=%s | last_plan=%s | last_exp=%s | now=%s",
                uid, last_plan, last_exp.isoformat() if last_exp else None, now.isoformat()
            )

            try:
                on_expire(uid, last_plan)  # внутри — планирование корутины в общий loop
                log.info("[SCHED] on_expire scheduled for user_id=%s", uid)
            except Exception as e:
                log.exception("[SCHED] on_expire call failed for user_id=%s: %s", uid, e)

            deleted = (
                session.query(Subscription)
                .filter(
                    Subscription.user_id == uid,
                    Subscription.expires_at <= now
                )
                .delete(synchronize_session=False)
            )
            log.info("[SCHED] Deleted %d expired rows for user_id=%s", deleted, uid)

        session.commit()
        log.info("[SCHED] Tick committed successfully")

    except Exception:
        log.exception("[SCHED] remove_expired_subscriptions error — rolling back")
        session.rollback()
    finally:
        session.close()
        log.info("[SCHED] Tick end")


def start_scheduler(on_expire: Callable[[int, str], None], interval_seconds: int = 60) -> BackgroundScheduler:
    """
    Запускает APScheduler. on_expire(user_id, plan) — колбэк, который кикает пользователя.
    """
    global _scheduler
    if _scheduler:
        return _scheduler

    # Явные executors — надёжнее в gunicorn gthread
    executors = {
        "default": ThreadPoolExecutor(max_workers=2),
    }
    _scheduler = BackgroundScheduler(timezone="UTC", executors=executors)
    first_run = _utcnow_naive() + timedelta(seconds=5)  # первый тик через 5 секунд

    _scheduler.add_job(
        _remove_expired_subscriptions,
        trigger="interval",
        seconds=interval_seconds,
        args=[on_expire],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
        id="remove_expired_subscriptions",
        next_run_time=first_run,  # гарантированно дергаем первый раз
    )
    _scheduler.start()

    # Логируем, что реально видит планировщик
    try:
        jobs = _scheduler.get_jobs()
        log.info("Scheduler started (interval=%ss). Jobs: %s", interval_seconds, [j.id for j in jobs])
        for j in jobs:
            log.info("Job %s next_run_time=%s", j.id, j.next_run_time)
    except Exception:
        log.exception("Failed to list scheduler jobs")

    return _scheduler
