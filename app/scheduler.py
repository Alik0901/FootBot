# app/scheduler.py
import logging
from datetime import datetime
from typing import Callable, Optional, List, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func

from app.models import SessionLocal, Subscription

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _utcnow_naive() -> datetime:
    """
    Возвращает naive UTC (без tzinfo), чтобы совпадать с тем,
    как мы сохраняем expires_at в БД.
    """
    return datetime.utcnow()


def _fmt_rows(rows: List[Tuple[int, datetime]]) -> str:
    """
    Упрощённое человекочитаемое представление содержимого БД.
    rows: [(user_id, max_exp), ...]
    """
    return ", ".join(f"{uid}:{exp.isoformat() if exp else 'None'}" for uid, exp in rows)


def _remove_expired_subscriptions(on_expire: Callable[[int, str], None]) -> None:
    """
    1) Сканирует таблицу подписок:
       для каждого user_id берём max(expires_at) как «срок последней подписки».
    2) Если max_exp <= now → считаем пользователя просроченным:
       - логируем
       - вызываем on_expire(user_id, last_plan)
       - удаляем все просроченные записи этого пользователя (expires_at <= now)
    3) Коммитим изменения.
    """
    now = _utcnow_naive()
    log.info("[SCHED] Tick start | now=%s", now.isoformat())

    session = SessionLocal()
    try:
        # 1) Берём по каждому user_id максимальную дату истечения
        agg_rows: List[Tuple[int, datetime]] = (
            session.query(
                Subscription.user_id.label("uid"),
                func.max(Subscription.expires_at).label("max_exp"),
            )
            .group_by(Subscription.user_id)
            .all()
        )

        log.info("[SCHED] Max per user (uid:max_exp): %s", _fmt_rows(agg_rows))

        # Разделяем на активных и просроченных
        expired_uids: List[int] = []
        active_uids: List[int] = []
        for uid, max_exp in agg_rows:
            if max_exp is None:
                # Теоретически невозможно, но логируем
                log.warning("[SCHED] user_id=%s has NULL max_exp — пропускаю", uid)
                continue
            if max_exp <= now:
                expired_uids.append(uid)
            else:
                active_uids.append(uid)

        log.info(
            "[SCHED] Summary: total_users=%d, active=%d, expired=%d",
            len(agg_rows), len(active_uids), len(expired_uids)
        )

        if not expired_uids:
            log.info("[SCHED] No expired users this tick")
            return

        # 2) Обрабатываем просроченных
        for uid in expired_uids:
            # Берём последнюю запись (на случай нескольких подписок)
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

            # Вызов внешнего колбэка (он сам планирует корутину через общий loop)
            try:
                on_expire(uid, last_plan)
                log.info("[SCHED] on_expire scheduled for user_id=%s", uid)
            except Exception as e:
                log.exception("[SCHED] on_expire failed for user_id=%s: %s", uid, e)

            # 3) Чистим все ПРОсроченные записи пользователя (<= now)
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

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _remove_expired_subscriptions,
        trigger="interval",
        seconds=interval_seconds,
        args=[on_expire],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,   # на случай коротких провалов
        id="remove_expired_subscriptions",
        next_run_time=None,      # первый запуск на следующем тике
    )
    _scheduler.start()
    log.info("Scheduler started (interval=%ss)", interval_seconds)
    return _scheduler
