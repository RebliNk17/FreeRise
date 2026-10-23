from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Path
from pydantic import BaseModel

from freerise.api.deps import DB, today
from freerise.cashflow.cycles import Cycle, cycle_by_label, cycle_for, get_start_day
from freerise.cashflow.fees import fees_in_cycle
from freerise.cashflow.summary import cycle_history, cycle_summary
from freerise.view import hiding

router = APIRouter()


class CycleOut(BaseModel):
    start: date
    end: date
    label_year: int
    label_month: int

    @classmethod
    def of(cls, c: Cycle) -> CycleOut:
        return cls(
            start=c.start, end=c.end, label_year=c.label_month.year, label_month=c.label_month.month
        )


class CategoryTotalOut(BaseModel):
    category_id: int | None
    name: str
    total: float
    count: int


class GroupOut(BaseModel):
    group: Literal["fixed", "variable", "savings", "income"]
    total: float
    categories: list[CategoryTotalOut]


class HistoryOut(CycleOut):
    net: float


class FeeItemOut(BaseModel):
    """amount positive."""

    txn_id: int
    date: date
    description: str
    account_id: int
    account_name: str
    merchant_key: str
    fee_key: str  # merchant_key without number tokens; new_fee_merchants holds these
    amount: float


class FeesOut(BaseModel):
    total: float
    count: int
    previous_total: float
    items: list[FeeItemOut]
    new_fee_merchants: list[str]


class CashflowOut(BaseModel):
    """Totals as cycle_summary returns them: spending and expense groups positive."""

    cycle: CycleOut
    income: float
    spending: float
    net: float
    verdict: Literal["positive", "negative"]
    groups: list[GroupOut]
    uncategorized_total: float
    uncategorized_count: int
    pending_count: int
    income_fixed: float
    income_variable: float
    basis: str
    history: list[HistoryOut]
    fees: FeesOut


def _cashflow(db: DB, c: Cycle) -> CashflowOut:
    s = cycle_summary(db, c)
    f = fees_in_cycle(db, c)
    return CashflowOut(
        cycle=CycleOut.of(c),
        income=s.income,
        spending=s.spending,
        net=s.net,
        verdict=s.verdict,
        groups=[
            GroupOut(
                group=g.group,
                total=g.total,
                categories=[CategoryTotalOut(**vars(x)) for x in g.categories],
            )
            for g in s.groups
        ],
        uncategorized_total=s.uncategorized_total,
        uncategorized_count=s.uncategorized_count,
        pending_count=s.pending_count,
        income_fixed=s.income_fixed,
        income_variable=s.income_variable,
        basis=s.basis,
        history=[
            HistoryOut(**CycleOut.of(hc).model_dump(), net=net) for hc, net in cycle_history(db, c)
        ],
        fees=FeesOut(
            total=f.total,
            count=f.count,
            previous_total=f.previous_total,
            items=[FeeItemOut(**vars(x)) for x in f.items],
            new_fee_merchants=f.new_fee_merchants,
        ),
    )


@router.get("/cashflow/current")
def cashflow_current(db: DB, hide_accounts: str | None = None) -> CashflowOut:
    with hiding(hide_accounts):
        return _cashflow(db, cycle_for(today(), get_start_day(db)))


@router.get("/cashflow/{year}/{month}")
def cashflow_for(
    db: DB,
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    hide_accounts: str | None = None,
) -> CashflowOut:
    with hiding(hide_accounts):
        return _cashflow(db, cycle_by_label(year, month, get_start_day(db)))
