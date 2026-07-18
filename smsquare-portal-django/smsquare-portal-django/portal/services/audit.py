"""Append-only audit trail. Every customer-visible action is recorded with
masked identifiers only — no raw mobile numbers, no OTPs, no card/UPI data.

Async (views are async throughout, matching the original httpx-async LMS
client) — call sites must `await audit(...)`."""

from portal.models import AuditLog


async def audit(
    action: str,
    detail: str = "",
    session_id: str = "",
    mobile_mask: str = "",
    ip: str = "",
) -> None:
    await AuditLog.objects.acreate(
        session_id=session_id,
        mobile_mask=mobile_mask,
        action=action,
        detail=detail[:2000],
        ip=ip,
    )
