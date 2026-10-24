from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from freerise.api.deps import DB, get_or_404
from freerise.categorize.pipeline import (
    category_usage,
    set_category,
    set_merchant_category,
    uncategorized_merchants,
)
from freerise.models import Category, MerchantRule, Transaction

router = APIRouter()

Group = Literal["income", "fixed", "variable", "savings", "transfer", "card_bill", "ignore"]


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    group: Group
    sort_order: int


class CategoryIn(BaseModel):
    name: str
    group: Group


class CategoryPatch(BaseModel):
    name: str | None = None
    group: Group | None = None


class InstallmentOut(BaseModel):
    number: int | None
    total: int
    amount: float  # per payment, positive


class MonthlyOut(BaseModel):
    amount: float  # median monthly total, positive
    months: int  # distinct months charged
    since: date


class Uncategorized(BaseModel):
    merchant_key: str
    sample_description: str
    count: int
    total: float  # signed sum
    kind: Literal["bank", "card"]
    sample_date: date  # latest one
    account_label: str  # latest one's account
    first_date: date  # earliest one
    installment: InstallmentOut | None  # latest installment payment, if paid in installments
    monthly: MonthlyOut | None  # charged monthly at a similar amount: likely fixed


class TxnCategoryIn(BaseModel):
    category_id: int
    remember: bool = True
    apply_to_past: bool = False


class MerchantCategoryIn(BaseModel):
    merchant_key: str
    category_id: int
    apply_to_past: bool = True
    remember: bool = True  # False: categorize its uncategorized txns once, no rule


class Changed(BaseModel):
    changed: int


class RuleOut(BaseModel):
    id: int
    pattern: str
    match: str
    category_id: int
    category_name: str
    source: str


def _commit(db: DB) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "category name already exists") from None


@router.get("/categories")
def list_categories(db: DB) -> list[CategoryOut]:
    return list(db.scalars(select(Category).order_by(Category.sort_order, Category.id)))


@router.post("/categories")
def create_category(body: CategoryIn, db: DB) -> CategoryOut:
    c = Category(name=body.name, group=body.group)
    db.add(c)
    _commit(db)
    return c


@router.patch("/categories/{id}")
def update_category(id: int, body: CategoryPatch, db: DB) -> CategoryOut:
    c = get_or_404(db, Category, id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    _commit(db)
    return c


@router.get("/categories/usage")
def get_category_usage(db: DB) -> list[int]:
    """Category ids, most used first (quick picks)."""
    return category_usage(db)


@router.get("/categories/uncategorized")
def list_uncategorized(db: DB) -> list[Uncategorized]:
    return uncategorized_merchants(db)


@router.put("/categories/merchant")
def categorize_merchant(body: MerchantCategoryIn, db: DB) -> Changed:
    get_or_404(db, Category, body.category_id)
    if not body.merchant_key:
        raise HTTPException(422, "merchant_key required")
    n = set_merchant_category(
        db, body.merchant_key, body.category_id, body.apply_to_past, body.remember
    )
    db.commit()
    return Changed(changed=n)


@router.put("/transactions/{id}/category")
def categorize_transaction(id: int, body: TxnCategoryIn, db: DB) -> Changed:
    get_or_404(db, Transaction, id)
    get_or_404(db, Category, body.category_id)
    n = set_category(db, id, body.category_id, body.remember, body.apply_to_past)
    db.commit()
    return Changed(changed=n)


@router.get("/rules")
def list_rules(db: DB) -> list[RuleOut]:
    rows = db.execute(
        select(MerchantRule, Category.name)
        .join(Category, Category.id == MerchantRule.category_id)
        .order_by(MerchantRule.id)
    )
    return [
        RuleOut(
            id=r.id,
            pattern=r.pattern,
            match=r.match,
            category_id=r.category_id,
            category_name=name,
            source=r.source,
        )
        for r, name in rows
    ]


@router.delete("/rules/{id}", status_code=204)
def delete_rule(id: int, db: DB) -> None:
    db.delete(get_or_404(db, MerchantRule, id))
    db.commit()
