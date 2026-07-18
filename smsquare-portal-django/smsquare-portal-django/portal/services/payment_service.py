"""Payment orchestration: transaction lifecycle and amount validation.

saverepayment is deliberately NOT called — its production host is
unconfirmed (absent from both reference scripts, see allcloud_client.py) and
posting a real repayment against a guessed host is too risky. A gateway
success is the terminal state from the app's own automatic flow; ops
reconciles GATEWAY_SUCCESS transactions into AllCloud out-of-band and may set
status to RECONCILED directly in pg_transactions once posted. The customer
is never shown a failure for this — see partials/payment_result.html."""

from portal.config import get_settings
from portal.models import PgTransaction


async def create_transaction(
    *,
    session_id: str,
    mobile: str,
    finance_id: str,
    agreement_no: str,
    amount: float,
    lpi_amount: float,
    collection_charges: float,
    payment_option: str,
) -> PgTransaction:
    return await PgTransaction.objects.acreate(
        session_id=session_id,
        mobile=mobile,
        finance_id=str(finance_id),
        agreement_no=agreement_no,
        amount=round(amount, 2),
        lpi_amount=round(lpi_amount, 2),
        collection_charges=round(collection_charges, 2),
        total_amount=round(amount + lpi_amount + collection_charges, 2),
        payment_option=payment_option,
    )


async def get_owned_txn(txn_id: int, session_id: str) -> PgTransaction | None:
    """Transactions are session-scoped — same IDOR posture as FinanceIds."""
    txn = await PgTransaction.objects.filter(pk=txn_id).afirst()
    if txn is None or txn.session_id != session_id:
        return None
    return txn


async def confirm_gateway_payment(txn: PgTransaction, utr: str) -> PgTransaction:
    """Customer confirmed the UPI payment. Records the UTR and marks the
    transaction GATEWAY_SUCCESS — terminal from the app's perspective; no
    LMS post is attempted (see module docstring)."""
    if txn.status in ("QR_GENERATED", "INITIATED"):
        txn.utr = (utr or "").strip()[:60]
        txn.status = "GATEWAY_SUCCESS"
        txn.receipt_no = txn.receipt_no or f"SMSQ{txn.created_at:%Y%m%d}{txn.id:06d}"
        await txn.asave()
    return txn


def min_part_payment(emi: float, dues_total: float) -> float:
    """Part payments must be at least the lower of the EMI amount or the
    total due — literally, so a loan that's fully current (dues_total=0)
    drops straight to the platform floor rather than forcing a full EMI on
    a voluntary prepayment."""
    s = get_settings()
    return max(min(emi, dues_total), s.min_part_payment)


def max_part_payment(loan_amount: float) -> float:
    """Cap on a customer-typed "any other payment" amount, so a fat-finger
    entry can't fire an oversized gateway charge — twice the original loan
    amount is far above any legitimate payoff/prepayment figure."""
    return round(2 * loan_amount, 2)


def validate_amount(
    option: str, part_amount: float | None, dues_total: float, emi: float, loan_amount: float
) -> tuple[str, float]:
    """Maps the customer's choice to the amount charged. Raises ValueError
    with an i18n key on bad input."""
    if option == "total":
        return "total", round(dues_total, 2)
    if option == "emi":
        return "emi", round(emi if emi > 0 else dues_total, 2)
    if option == "part":
        amt = round(part_amount or 0, 2)
        if amt < min_part_payment(emi, dues_total):
            raise ValueError("pay_min_part")
        if amt > max_part_payment(loan_amount):
            raise ValueError("pay_exceeds_max")
        return "part", amt
    raise ValueError("pay_bad_option")
