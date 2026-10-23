from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Kind = Literal["bank", "card", "fund"]
TxnStatus = Literal["pending", "completed"]
Trigger = Literal["schedule", "manual", "verify"]
SyncStatus = Literal["requested", "running", "success", "failed", "otp_timeout"]
FailureKind = Literal["auth_failed", "provider_changed", "timeout", "otp_timeout", "other"]
FAILURE_KINDS = ("auth_failed", "provider_changed", "timeout", "otp_timeout", "other")
OtpStatus = Literal["waiting", "answered", "expired"]
CategoryGroup = Literal["income", "fixed", "variable", "savings", "transfer", "card_bill", "ignore"]
RuleMatch = Literal["exact", "contains"]
RuleSource = Literal["user", "seed", "ai", "provider"]
GROUPS = ("income", "fixed", "variable", "savings", "transfer", "card_bill", "ignore")

Money = Numeric(12, 2)


def _in(col: str, vals: tuple[str, ...], name: str) -> CheckConstraint:
    return CheckConstraint(f"{col} IN ({', '.join(repr(v) for v in vals)})", name=name)


def _fk(target: str) -> Mapped[int]:
    return mapped_column(ForeignKey(f"{target}.id", ondelete="CASCADE"))


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str]
    totp_secret_enc: Mapped[bytes | None]


class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[int] = _fk("users")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Credential(Base):
    __tablename__ = "credentials"
    provider: Mapped[str]
    label: Mapped[str]
    owner: Mapped[str]
    secret_enc: Mapped[bytes]
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None]
    # False until a verify run logged in and fetched accounts; unverified rows are hidden and
    # never synced on schedule.
    verified: Mapped[bool] = mapped_column(default=True, server_default="true")
    # New details for a verified connection, swapped into secret_enc once they verify.
    pending_secret_enc: Mapped[bytes | None]


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("credential_id", "provider_account_id"),
        _in("kind", ("bank", "card", "fund"), "ck_accounts_kind"),
    )
    credential_id: Mapped[int] = _fk("credentials")
    provider_account_id: Mapped[str]
    kind: Mapped[Kind] = mapped_column(String)
    display_name: Mapped[str]
    excluded: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Whose card/account. NULL: unknown (sync may fill it from the provider); "": cleared by
    # the user. Both show credential.owner.
    holder: Mapped[str | None]

    credential: Mapped[Credential] = relationship()


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "txn_key"),
        Index("ix_transactions_account_id_date", "account_id", "date"),
        Index("ix_transactions_merchant_key", "merchant_key"),
        _in("status", ("pending", "completed"), "ck_transactions_status"),
        _in("cycle_date_source", ("auto", "manual"), "ck_transactions_cycle_date_source"),
    )
    account_id: Mapped[int] = _fk("accounts")
    txn_key: Mapped[str]
    date: Mapped[date]
    processed_date: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Money)
    original_amount: Mapped[Decimal | None] = mapped_column(Money)
    original_currency: Mapped[str | None]
    description: Mapped[str]
    memo: Mapped[str | None]
    identifier: Mapped[str | None]
    installment_number: Mapped[int | None]
    installment_total: Mapped[int | None]
    provider_category: Mapped[str | None]
    status: Mapped[TxnStatus] = mapped_column(String)
    raw: Mapped[dict] = mapped_column(JSONB)
    merchant_key: Mapped[str] = mapped_column(String, server_default="")
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    category_source: Mapped[str | None]  # rule|map|provider|ai|manual
    note: Mapped[str | None]
    # Date used for cycle membership when the txn belongs to a neighbour cycle (late/early
    # income); NULL = its own date. Reconciliation and recurring detection use the real date.
    cycle_date: Mapped[date | None]
    cycle_date_source: Mapped[str | None] = mapped_column(String)  # auto|manual

    @hybrid_property
    def effective_date(self) -> date:
        return self.cycle_date or self.date

    @effective_date.inplace.expression
    @classmethod
    def _effective_date_expression(cls):
        return func.coalesce(cls.cycle_date, cls.date)


class Balance(Base):
    __tablename__ = "balances"
    account_id: Mapped[int] = _fk("accounts")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    balance: Mapped[Decimal] = mapped_column(Money)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_status", "status"),
        _in("trigger", ("schedule", "manual", "verify"), "ck_sync_runs_trigger"),
        _in(
            "status",
            ("requested", "running", "success", "failed", "otp_timeout"),
            "ck_sync_runs_status",
        ),
        _in("failure_kind", FAILURE_KINDS, "ck_sync_runs_failure_kind"),
    )
    credential_id: Mapped[int] = _fk("credentials")
    trigger: Mapped[Trigger] = mapped_column(String)
    status: Mapped[SyncStatus] = mapped_column(String)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]
    failure_kind: Mapped[FailureKind | None] = mapped_column(String)  # set when not success
    added: Mapped[int] = mapped_column(default=0, server_default="0")
    updated: Mapped[int] = mapped_column(default=0, server_default="0")
    progress: Mapped[str | None]  # "login" | "fetch" (scraper phase)
    progress_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class OtpRequest(Base):
    __tablename__ = "otp_requests"
    __table_args__ = (_in("status", ("waiting", "answered", "expired"), "ck_otp_requests_status"),)
    sync_run_id: Mapped[int] = _fk("sync_runs")
    status: Mapped[OtpStatus] = mapped_column(String)
    code_enc: Mapped[bytes | None]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (_in('"group"', GROUPS, "ck_categories_group"),)
    name: Mapped[str] = mapped_column(String, unique=True)
    group: Mapped[CategoryGroup] = mapped_column(String)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")


class MerchantRule(Base):
    __tablename__ = "merchant_rules"
    __table_args__ = (
        UniqueConstraint("pattern", "match"),
        _in("match", ("exact", "contains"), "ck_merchant_rules_match"),
        _in("source", ("user", "seed", "ai", "provider"), "ck_merchant_rules_source"),
    )
    pattern: Mapped[str]
    match: Mapped[RuleMatch] = mapped_column(String)
    category_id: Mapped[int] = _fk("categories")
    source: Mapped[RuleSource] = mapped_column(String)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, unique=True)
    value: Mapped[object] = mapped_column(JSONB)


Direction = Literal["expense", "income"]
Cadence = Literal["monthly", "bimonthly", "quarterly", "semiannual", "annual"]
AmountKind = Literal["fixed", "variable"]
RecurringStatus = Literal["pending", "confirmed", "dismissed"]
CADENCES = ("monthly", "bimonthly", "quarterly", "semiannual", "annual")


class RecurringItem(Base):
    __tablename__ = "recurring_items"
    __table_args__ = (
        UniqueConstraint("merchant_key", "direction"),
        _in("direction", ("expense", "income"), "ck_recurring_items_direction"),
        _in("cadence", CADENCES, "ck_recurring_items_cadence"),
        _in("amount_kind", ("fixed", "variable"), "ck_recurring_items_amount_kind"),
        _in("status", ("pending", "confirmed", "dismissed"), "ck_recurring_items_status"),
    )
    merchant_key: Mapped[str]
    direction: Mapped[Direction] = mapped_column(String)
    label: Mapped[str]
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    cadence: Mapped[Cadence] = mapped_column(String)
    amount_kind: Mapped[AmountKind] = mapped_column(String)
    expected_amount: Mapped[Decimal] = mapped_column(Money)  # positive
    last_date: Mapped[date]
    next_expected_date: Mapped[date]
    status: Mapped[RecurringStatus] = mapped_column(
        String, default="pending", server_default="pending"
    )
    basis: Mapped[str]
    # Account of the latest occurrence; the one before it switched, and when it switched.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    previous_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL")
    )
    account_changed_on: Mapped[date | None]
    # Marked fixed by the user: detection never deletes it or changes its day/amount.
    user_defined: Mapped[bool] = mapped_column(default=False, server_default="false")
    expected_day: Mapped[int | None]  # user-defined day of month (31 = month end)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CycleGoal(Base):
    __tablename__ = "cycle_goals"
    cycle_start: Mapped[date] = mapped_column(unique=True)
    amount: Mapped[Decimal] = mapped_column(Money)


class InsightState(Base):
    """Snoozed (until a time) or dismissed (until the insight's key changes) home insights."""

    __tablename__ = "insight_states"
    key: Mapped[str] = mapped_column(String, unique=True)
    dismissed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed: Mapped[bool] = mapped_column(default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # rows untouched for engine.PRUNE_DAYS are deleted


Pct = Numeric(7, 4)


class Fund(Base):
    """A pension fund or keren hishtalmut policy from the clearing house."""

    __tablename__ = "funds"
    credential_id: Mapped[int] = _fk("credentials")
    policy_id: Mapped[str] = mapped_column(String, unique=True)
    product_type: Mapped[str]  # pension|hishtalmut
    pension_type: Mapped[str | None]  # makifa|mashlima
    name: Mapped[str]
    company: Mapped[str | None]
    liquidity_date: Mapped[date | None]
    fee_deposit_pct: Mapped[Decimal | None] = mapped_column(Pct)
    fee_savings_pct: Mapped[Decimal | None] = mapped_column(Pct)
    tracks: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    owner: Mapped[str]


class FundSnapshot(Base):
    __tablename__ = "fund_snapshots"
    __table_args__ = (UniqueConstraint("fund_id", "as_of"),)
    fund_id: Mapped[int] = _fk("funds")
    as_of: Mapped[date]
    balance: Mapped[Decimal] = mapped_column(Money)


class FundDeposit(Base):
    __tablename__ = "fund_deposits"
    __table_args__ = (UniqueConstraint("fund_id", "date", "amount"),)
    fund_id: Mapped[int] = _fk("funds")
    date: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Money)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class ClearingHouseReport(Base):
    __tablename__ = "clearing_house_reports"
    __table_args__ = (UniqueConstraint("credential_id", "report_month"),)
    credential_id: Mapped[int] = _fk("credentials")
    report_month: Mapped[date]
    data: Mapped[dict] = mapped_column(JSONB)


Severity = Literal["info", "warning", "critical"]
DeliveryStatus = Literal["pending", "sent", "failed"]


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        _in("severity", ("info", "warning", "critical"), "ck_notifications_severity"),
    )
    kind: Mapped[str]
    severity: Mapped[Severity] = mapped_column(String, default="info", server_default="info")
    title: Mapped[str]
    body: Mapped[str]
    link: Mapped[str | None]
    dedup_key: Mapped[str] = mapped_column(String, unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", "channel"),
        _in("status", ("pending", "sent", "failed"), "ck_notification_deliveries_status"),
    )
    notification_id: Mapped[int] = _fk("notifications")
    channel: Mapped[str]
    status: Mapped[DeliveryStatus] = mapped_column(String, default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]


class SavingsPlan(Base):
    """A savings goal ("יעדי חיסכון"); its monthly amount is added to the cycle goal."""

    __tablename__ = "savings_plans"
    name: Mapped[str]
    target_amount: Mapped[Decimal] = mapped_column(Money)
    target_date: Mapped[date]
    saved_amount: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    monthly_override: Mapped[Decimal | None] = mapped_column(Money)
    active: Mapped[bool] = mapped_column(default=True, server_default="true")


class PlanContribution(Base):
    """One "העברתי החודש" per plan per cycle."""

    __tablename__ = "plan_contributions"
    __table_args__ = (UniqueConstraint("plan_id", "cycle_start"),)
    plan_id: Mapped[int] = _fk("savings_plans")
    cycle_start: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Money)


class TrackedCategory(Base):
    """A variable category shown as its own card on the home screen."""

    __tablename__ = "tracked_categories"
    __table_args__ = (_in("mode", ("weekly", "monthly"), "ck_tracked_categories_mode"),)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), unique=True
    )
    mode: Mapped[str] = mapped_column(String, default="monthly", server_default="monthly")
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")
    active: Mapped[bool] = mapped_column(default=True, server_default="true")


class CategoryBudget(Base):
    """User override of a tracked category's expected spending for one cycle."""

    __tablename__ = "category_budgets"
    __table_args__ = (UniqueConstraint("cycle_start", "category_id"),)
    cycle_start: Mapped[date]
    category_id: Mapped[int] = _fk("categories")
    amount: Mapped[Decimal] = mapped_column(Money)


class CategoryWeekBudget(Base):
    __tablename__ = "category_week_budgets"
    __table_args__ = (UniqueConstraint("cycle_start", "category_id", "week_index"),)
    cycle_start: Mapped[date]
    category_id: Mapped[int] = _fk("categories")
    week_index: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Money)


class TransactionSplit(Base):
    """One part of a split transaction. A split txn counts as its parts wherever money is
    summed by category (cashflow.parts.txn_parts); parts sum to the txn amount."""

    __tablename__ = "transaction_splits"
    __table_args__ = (UniqueConstraint("transaction_id", "category_id"),)
    transaction_id: Mapped[int] = _fk("transactions")
    category_id: Mapped[int] = _fk("categories")
    amount: Mapped[Decimal] = mapped_column(Money)  # signed, like the transaction
