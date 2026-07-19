"""Engine performance endpoints: accuracy history, ROI, model weights."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbDep
from app.api.schemas import EngineMetricOut, ModelWeightOut
from app.infrastructure.db.models import EngineMetric, ModelWeight

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/engine", response_model=list[EngineMetricOut])
def engine_history(db: DbDep, days: int = 30, market: str = "all") -> list[EngineMetricOut]:
    since = date.today() - timedelta(days=min(days, 365))
    rows = db.scalars(
        select(EngineMetric)
        .where(EngineMetric.metric_date >= since, EngineMetric.market == market)
        .order_by(EngineMetric.metric_date)
    ).all()
    return [EngineMetricOut.model_validate(r) for r in rows]


@router.get("/weights", response_model=list[ModelWeightOut])
def weights(db: DbDep, market: str | None = None) -> list[ModelWeightOut]:
    q = select(ModelWeight)
    if market:
        q = q.where(ModelWeight.market == market)
    rows = db.scalars(q.order_by(ModelWeight.market, ModelWeight.weight.desc())).all()
    return [ModelWeightOut.model_validate(r) for r in rows]
