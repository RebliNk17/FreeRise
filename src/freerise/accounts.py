"""How an account is named to the user: "ישראכרט ••1234", "עו״ש וואן זירו ••5678"."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, joinedload

from freerise.models import Account, Balance, Transaction
from freerise.reconcile.card_bills import ISSUER_NAMES

PROVIDER_HE = {
    **ISSUER_NAMES,
    "onezero": "וואן זירו",
    "pepper": "פפר",
    "mislaka": "המסלקה",
    "hafenix": "הפניקס",
    "migdal": "מגדל",
}


def account_label(a: Account) -> str:
    """The user's own name if they renamed it, else provider + last 4 digits."""
    cred, last4 = a.credential, a.provider_account_id[-4:]
    # Default is f"{cred.label} {last4}" (sync._upsert_account); the credential may be renamed.
    if not a.display_name.endswith(f" {last4}"):
        return a.display_name
    name = PROVIDER_HE.get(cred.provider, cred.label)
    # LTR isolate so RTL text renders "••1234", not "1234••".
    return f"{'עו״ש ' if a.kind == 'bank' else ''}{name} \u2066••{last4}\u2069"


def account_provider(a: Account) -> str:
    """The user's own name for it if renamed, else the provider ("וואן זירו", "ישראכרט")."""
    if not a.display_name.endswith(f" {a.provider_account_id[-4:]}"):
        return a.display_name
    return PROVIDER_HE.get(a.credential.provider, a.credential.label)


def account_holder(a: Account) -> str:
    """Whose card/account it is: the user's (or provider's) holder, else the login owner."""
    return a.holder or a.credential.owner


def account_holders(session: Session) -> dict[int, str]:
    return {
        a.id: account_holder(a)
        for a in session.scalars(select(Account).options(joinedload(Account.credential)))
    }


def account_labels(session: Session) -> dict[int, str]:
    return {
        a.id: account_label(a)
        for a in session.scalars(select(Account).options(joinedload(Account.credential)))
    }


INACTIVE_AFTER = timedelta(days=180)


def active_card_ids(s: Session, accounts: list[Account]) -> set[int]:
    """Which accounts count as in use. Cards need a charge in the last 6 months or a
    non-zero balance (expired/replaced cards keep being returned by providers);
    bank accounts and funds always count."""
    ids = [a.id for a in accounts]
    active = {a.id for a in accounts if a.kind != "card"}
    active |= set(
        s.scalars(
            select(Transaction.account_id)
            .where(
                Transaction.account_id.in_(ids), Transaction.date >= date.today() - INACTIVE_AFTER
            )
            .distinct()
        )
    )
    latest = latest_balances().where(Balance.account_id.in_(ids)).subquery()
    active |= set(s.scalars(select(latest.c.account_id).where(latest.c.balance != 0)))
    return active


def latest_balances():
    """Each account's newest balance reading (account_id, balance, as_of): the last one saved.
    Not the latest as_of: a card's reading can be dated on its coming charge day, ahead of newer ones."""
    return (
        select(Balance.account_id, Balance.balance, Balance.as_of)
        .ext(distinct_on(Balance.account_id))
        .order_by(Balance.account_id, Balance.id.desc())
    )
