# app/scheduler.py
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func

from app.models import SessionLocal, Subscription

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _remove_expired_subscriptions(on_expire: Callable[[int, str], None]) -> None:
    """
    Находит юзеров, у которых НЕТ активных подписок на сейчас,
    и отключает доступ через on_expire(user_id, last_plan).
    Затем удаляет их истекшие записи.
    """
    # мы храним naive UTC → сравниваем с naive UTC
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    session = SessionLocal()
    try:
        rows = (
            session.query(Subscription.user_id, func.max(Subscription.expires_at))
            .group_by(Subscription.user_id)
            .all()
        )

        to_disable = [uid for uid, max_exp in rows if max_exp and max_exp <= now]
        if not to_disable:
            return

        log.info("Expired users to disable: %s", to_disable)

        for uid in to_disable:
            last_sub = (
                session.query(Subscription)
                .filter(Subscription.user_id == uid)
                .order_by(Subscription.expires_at.desc())
                .first()
            )
            plan = last_sub.plan if last_sub else "-"

            try:
                on_expire(uid, plan)  # внутри on_expire действия бота планируются через run_coro
            except Exception:
                log.exception("on_expire failed for user_id=%s", uid)

            session.query(Subscription).filter(
                Subscription.user_id == uid,
                Subscription.expires_at <= now
            ).delete(synchronize_session=False)

        session.commit()

    except Exception:
        log.exception("remove_expired_subscriptions error")
        session.rollback()
    finally:
        session.close()


def start_scheduler(on_expire: Callable[[int, str], None], interval_seconds: int = 60) -> BackgroundScheduler:
    """
    Запускает APScheduler. on_expire(user_id, plan) — колбэк, который кикает пользователя.
    """
    global _scheduler
    if _scheduler:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _remove_expired_subscriptions,
        "interval",
        seconds=interval_seconds,
        args=[on_expire],
        max_instances=1,
        coalesce=True,
        id="remove_expired_subscriptions",
        next_run_time=None,
    )
    _scheduler.start()
    log.info("Scheduler started (interval=%ss)", interval_seconds)
    return _scheduler
