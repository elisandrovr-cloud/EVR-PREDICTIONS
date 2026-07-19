"""Admin panel API: users, subscriptions, payments, logs, models, sources, jobs."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbDep, audit
from app.api.schemas import AuditLogOut, ModelWeightOut, SourceStatusOut, UserOut
from app.infrastructure.db.models import (
    ApiSourceStatus,
    AuditLog,
    ModelWeight,
    Payment,
    Prediction,
    Subscription,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def users(admin: AdminUser, db: DbDep, limit: int = 100, offset: int = 0) -> list[UserOut]:
    rows = db.scalars(select(User).order_by(User.id).offset(offset).limit(min(limit, 500))).all()
    return [UserOut.model_validate(u) for u in rows]


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: dict[str, Any], admin: AdminUser, db: DbDep, request: Request) -> dict[str, str]:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if "role" in payload and payload["role"] in ("user", "premium", "admin"):
        user.role = payload["role"]
    if "is_active" in payload:
        user.is_active = bool(payload["is_active"])
    db.commit()
    audit(db, request, "admin.user_update", user_id=admin.id, target=user_id, changes=payload)
    return {"status": "updated"}


@router.get("/subscriptions")
def subscriptions(admin: AdminUser, db: DbDep) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Subscription, User.email).join(User, User.id == Subscription.user_id)
    ).all()
    return [
        {"id": s.id, "email": email, "plan": s.plan, "status": s.status,
         "started_at": s.started_at, "expires_at": s.expires_at}
        for s, email in rows
    ]


@router.get("/payments")
def payments(admin: AdminUser, db: DbDep, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(limit)).all()
    return [
        {"id": p.id, "user_id": p.user_id, "amount": p.amount, "currency": p.currency,
         "status": p.status, "created_at": p.created_at}
        for p in rows
    ]


@router.get("/logs", response_model=list[AuditLogOut])
def logs(admin: AdminUser, db: DbDep, limit: int = 200) -> list[AuditLogOut]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 1000))).all()
    return [AuditLogOut.model_validate(r) for r in rows]


@router.get("/models", response_model=list[ModelWeightOut])
def models(admin: AdminUser, db: DbDep) -> list[ModelWeightOut]:
    rows = db.scalars(select(ModelWeight).order_by(ModelWeight.market, ModelWeight.weight.desc())).all()
    return [ModelWeightOut.model_validate(r) for r in rows]


@router.get("/sources", response_model=list[SourceStatusOut])
def sources(admin: AdminUser, db: DbDep) -> list[SourceStatusOut]:
    rows = db.scalars(select(ApiSourceStatus).order_by(ApiSourceStatus.source)).all()
    return [SourceStatusOut.model_validate(r) for r in rows]


@router.get("/overview")
def overview(admin: AdminUser, db: DbDep) -> dict[str, Any]:
    today = date.today()
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "predictions_today": db.scalar(
            select(func.count(Prediction.id)).where(Prediction.game_date == today)
        ) or 0,
        "value_bets_today": db.scalar(
            select(func.count(Prediction.id)).where(
                Prediction.game_date == today, Prediction.is_value_bet.is_(True))
        ) or 0,
    }


@router.post("/jobs/{job_name}")
def trigger_job(job_name: str, admin: AdminUser, db: DbDep, request: Request) -> dict[str, str]:
    """Manually enqueue a pipeline job (refresh, predict, close-day)."""
    from app.workers import tasks

    mapping = {
        "refresh": tasks.refresh_all_data,
        "predict": tasks.generate_predictions,
        "parlays": tasks.build_parlays,
        "close-day": tasks.close_previous_day,
        "bootstrap": tasks.bootstrap_reference_data,
    }
    task = mapping.get(job_name)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_name}'")
    async_result = task.delay()
    audit(db, request, "admin.job_trigger", user_id=admin.id, job=job_name, task_id=async_result.id)
    return {"status": "queued", "task_id": async_result.id}
