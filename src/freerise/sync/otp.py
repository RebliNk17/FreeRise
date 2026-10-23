import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from freerise.crypto import decrypt_str, encrypt_str
from freerise.models import OtpRequest


class OtpTimeout(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


async def wait_for_otp(
    session_factory: sessionmaker, sync_run_id: int, timeout_s: int = 300, poll_s: float = 2
) -> str:
    with session_factory() as s:
        req = OtpRequest(
            sync_run_id=sync_run_id,
            status="waiting",
            expires_at=_now() + timedelta(seconds=timeout_s),
        )
        s.add(req)
        s.commit()
        req_id, expires_at = req.id, req.expires_at
    while True:
        await asyncio.sleep(poll_s)
        with session_factory() as s:
            req = s.get(OtpRequest, req_id, with_for_update=True)
            if req is None:  # its credential was deleted (verify canceled)
                raise OtpTimeout("OTP request gone")
            if req.status == "answered":
                return decrypt_str(req.code_enc)
            if req.status == "expired" or _now() >= expires_at:  # expired: canceled by the user
                req.status = "expired"
                s.commit()
                raise OtpTimeout(f"OTP not entered within {timeout_s}s")


def answer_otp(session: Session, otp_request_id: int, code: str) -> None:
    req = session.get(OtpRequest, otp_request_id, with_for_update=True)
    if req is None or req.status != "waiting" or _now() >= req.expires_at:
        raise ValueError("OTP request is not waiting")
    req.code_enc = encrypt_str(code)
    req.status = "answered"
    session.commit()
