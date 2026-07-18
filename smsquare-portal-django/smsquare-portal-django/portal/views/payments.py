"""Dues display, payment options, UPI QR, confirmation, receipt.

Compliance notes baked into the flow:
- Full charge break-up (EMI / penal LPI / collection charges) disclosed
  BEFORE any payment action (RBI penal charges circular).
- A gateway success is never shown as a failure. No saverepayment call is
  made (host unconfirmed — see payment_service.py); ops reconciles into
  AllCloud out-of-band.
"""

from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render

from portal.decorators import assert_loan_access, require_session
from portal.lms import get_lms
from portal.services import payment_service
from portal.services.allcloud_auth import LMSError
from portal.services.audit import audit
from portal.services.receipt_pdf import build_receipt_pdf


@require_session
async def pay_page(request, sess, finance_id: str):
    lms = get_lms()
    await assert_loan_access(lms, sess, finance_id, request)
    dues = await lms.get_repayment_for_loan(finance_id)  # live dues
    loans = await lms.get_loans_by_mobile(sess.mobile)
    loan = next((l for l in loans if str(l.finance_id) == str(finance_id)), None)
    # GetLoanByMobileNumber's own fields are unreliable — GetLoanAgreementNoAsync
    # is the accurate, much richer source (customer name, tenure, EMI counts,
    # VAS/late charges) whenever the lookup works.
    if loan:
        try:
            agr_loans = await lms.get_loan_by_agreement(loan.agreement_no)
            match = next(
                (l for l in agr_loans if l.agreement_no.upper() == loan.agreement_no.upper()),
                None,
            )
            if match:
                loan = match
        except LMSError:
            pass
    min_part_amount = payment_service.min_part_payment(
        loan.regular_emi_amount if loan else 0.0,
        loan.total_emi_overdue_amount if loan else 0.0,
    )
    max_part_amount = payment_service.max_part_payment(loan.loan_amount if loan else 0.0)
    await audit("pay_page_view", detail=f"finance_id={finance_id}",
                session_id=sess.id, mobile_mask=sess.mobile_mask)
    return render(request, "pay.html", {"sess": sess, "loan": loan, "dues": dues,
                                        "finance_id": finance_id, "min_part_amount": min_part_amount,
                                        "max_part_amount": max_part_amount})


@require_session
async def generate_qr(request, sess, finance_id: str):
    """HTMX: creates the pg_transaction and renders the customer's chosen
    payment method — Pay Now gateway button."""
    lms = get_lms()
    await assert_loan_access(lms, sess, finance_id, request)
    option = request.POST.get("option", "")
    part_amount = request.POST.get("part_amount")
    part_amount = float(part_amount) if part_amount else None
    method = request.POST.get("method", "paynow")  # paynow -> ShowQR:false | qr -> ShowQR:true
    want_sms_link = bool(request.POST.get("want_sms_link"))

    # Re-fetch fresh, never trust the form. GetLoanAgreementNoAsync (loan) is
    # the accurate source for these totals — see pay_page/pay.html.
    loans = await lms.get_loans_by_mobile(sess.mobile)
    base_loan = next((l for l in loans if str(l.finance_id) == str(finance_id)), None)
    loan = base_loan
    if base_loan:
        try:
            agr_loans = await lms.get_loan_by_agreement(base_loan.agreement_no)
            match = next(
                (l for l in agr_loans if l.agreement_no.upper() == base_loan.agreement_no.upper()),
                None,
            )
            if match:
                loan = match
        except LMSError:
            pass
    total = loan.total_emi_overdue_amount if loan else 0.0
    emi = loan.regular_emi_amount if loan else 0.0
    loan_amount = loan.loan_amount if loan else 0.0

    try:
        option, pay_amount = payment_service.validate_amount(option, part_amount, total, emi, loan_amount)
    except ValueError as exc:
        error_key = str(exc)
        ctx = {"error_key": error_key}
        if error_key == "pay_min_part":
            ctx["min_amount"] = payment_service.min_part_payment(emi, total)
        elif error_key == "pay_exceeds_max":
            ctx["max_amount"] = payment_service.max_part_payment(loan_amount)
        return render(request, "partials/pay_error.html", ctx)

    # Charges are collected in full first; the remainder is the EMI/principal leg.
    lpi = min(float(loan.lpi_dues) if loan else 0.0, pay_amount)
    coll = min(float(loan.total_vas_dues) if loan else 0.0, max(pay_amount - lpi, 0.0))
    principal = round(pay_amount - lpi - coll, 2)

    txn = await payment_service.create_transaction(
        session_id=sess.id,
        mobile=sess.mobile,
        finance_id=finance_id,
        agreement_no="",
        amount=principal,
        lpi_amount=lpi,
        collection_charges=coll,
        payment_option=option,
    )
    show_qr = method == "qr"
    try:
        qr = await lms.get_qr_code(
            finance_id=finance_id,
            due_amount=principal,
            collection_charges=coll,
            lpi_amount=lpi,
            show_qr=show_qr,
            sms_link=want_sms_link,
        )
    except LMSError:
        txn.status = "FAILED"
        txn.last_error = "GetQRCode failed"
        await txn.asave()
        return render(request, "partials/pay_error.html", {"error_key": "err_lms_down"})

    txn.lms_receipt_ref = qr.reference[:80]
    await txn.asave()
    # No separate "I have completed the payment" step — the gateway page is
    # the actual payment action, and the portal can't verify completion from
    # here (no server-to-server callback), so the transaction is marked
    # GATEWAY_SUCCESS as soon as the checkout link is generated. Never shown
    # as a failure; ops reconciles into AllCloud out-of-band.
    txn = await payment_service.confirm_gateway_payment(txn, utr="")
    await audit("qr_generated",
                detail=f"txn={txn.id} finance_id={finance_id} amount={txn.total_amount} method={method}",
                session_id=sess.id, mobile_mask=sess.mobile_mask)
    return render(request, "partials/payment_result.html", {"txn": txn, "qr": qr})


@require_session
async def receipt_pdf(request, sess, txn_id: int):
    txn = await payment_service.get_owned_txn(txn_id, sess.id)
    if txn is None or txn.status != "RECONCILED":
        return HttpResponseNotFound()
    pdf = build_receipt_pdf(txn, customer_name=sess.customer_name)
    await audit("receipt_downloaded", detail=f"txn={txn.id}",
                session_id=sess.id, mobile_mask=sess.mobile_mask)
    return HttpResponse(
        content=pdf,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{txn.receipt_no}.pdf"'},
    )
