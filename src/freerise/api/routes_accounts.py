from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import joinedload

from freerise.accounts import account_holder, account_label, active_card_ids
from freerise.api.deps import DB, get_or_404
from freerise.models import Account, Balance, Credential

router = APIRouter()


class AccountOut(BaseModel):
    id: int
    credential_id: int
    provider: str
    kind: str
    display_name: str
    label: str  # account_label(): what the UI shows
    holder: str  # whose account: the stored holder, else the credential's owner
    excluded: bool
    balance: float | None
    balance_as_of: datetime | None
    active: bool  # cards: used in the last 6 months or carrying a balance


class AccountPatch(BaseModel):
    display_name: str | None = None
    excluded: bool | None = None
    # "" clears -> credential owner; stored as "" so sync never fills it in again
    holder: str | None = Field(None, max_length=100)


def _rows(db: DB, account_id: int | None = None) -> list[AccountOut]:
    latest = (
        select(Balance.account_id, Balance.balance, Balance.as_of)
        .ext(distinct_on(Balance.account_id))
        .order_by(Balance.account_id, Balance.as_of.desc())
        .subquery()
    )
    q = (
        select(Account, Credential.provider, latest.c.balance, latest.c.as_of)
        .options(joinedload(Account.credential))
        .join(Credential, Credential.id == Account.credential_id)
        .outerjoin(latest, latest.c.account_id == Account.id)
        .order_by(Account.id)
    )
    if account_id is not None:
        q = q.where(Account.id == account_id)
    rows = db.execute(q).all()
    active = active_card_ids(db, [a for a, *_ in rows])
    return [
        AccountOut(
            id=a.id,
            credential_id=a.credential_id,
            provider=provider,
            kind=a.kind,
            display_name=a.display_name,
            label=account_label(a),
            holder=account_holder(a),
            excluded=a.excluded,
            balance=bal,
            balance_as_of=as_of,
            active=a.id in active,
        )
        for a, provider, bal, as_of in rows
    ]


@router.get("/accounts")
def list_accounts(db: DB) -> list[AccountOut]:
    return _rows(db)


@router.patch("/accounts/{id}")
def update_account(id: int, body: AccountPatch, db: DB) -> AccountOut:
    a = get_or_404(db, Account, id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(a, k, v.strip() if k == "holder" else v)
    db.commit()
    return _rows(db, id)[0]
