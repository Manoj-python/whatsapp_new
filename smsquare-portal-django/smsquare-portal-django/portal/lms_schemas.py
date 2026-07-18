"""Pydantic models for AllCloud responses.

Schemas are undocumented, so every model tolerates unknown fields
(extra="ignore") and uses alias fallbacks via validation_alias where field
naming is uncertain. Use /dev/lms-probe in UAT to inspect raw payloads and
tighten these over time.

Confirmed live (2026-07-14): AllCloud sends CustomerId/ContactNumber as JSON
numbers, not strings, on GetCustomerSearch — coerce_numbers_to_str handles
that (and any other str-typed field AllCloud sends numerically) app-wide.
"""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TolerantModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore", populate_by_name=True, coerce_numbers_to_str=True
    )


class CustomerSearchResult(TolerantModel):
    customer_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CustomerId", "CustomerID", "customerId", "Id"),
    )
    # Confirmed live (2026-07-16): GetCustomerSearch has NO "CustomerName"
    # field — only FirstName/LastName separately.
    first_name: str = Field(default="", validation_alias=AliasChoices("FirstName",))
    last_name: str = Field(default="", validation_alias=AliasChoices("LastName",))
    customer_name_raw: str = Field(
        default="",
        validation_alias=AliasChoices("CustomerName", "Name", "customerName"),
    )
    contact: str = Field(
        default="", validation_alias=AliasChoices("Contact", "ContactNumber", "Mobile")
    )
    # Confirmed live (2026-07-14): GetCustomerSearch returns DOB — the
    # agreement-lookup endpoint does NOT, so this is the only source of DOB
    # for the alternate login flow.
    dob: str = Field(default="", validation_alias=AliasChoices("DOB", "DateOfBirth"))

    @property
    def customer_name(self) -> str:
        return self.customer_name_raw or f"{self.first_name} {self.last_name}".strip()


class CoBorrower(TolerantModel):
    customer_id: str = Field(
        default="", validation_alias=AliasChoices("CustomerId", "CustomerID")
    )
    order_type_id: str = Field(
        default="", validation_alias=AliasChoices("OrderTypeId", "OrderType")
    )
    entity_type_id: str = Field(default="", validation_alias=AliasChoices("EntityTypeId",))
    borrower_name: str = Field(default="", validation_alias=AliasChoices("BorrowerName",))


class RepaymentScheduleEntry(TolerantModel):
    installment_no: int = Field(default=0, validation_alias=AliasChoices("InstallmentNo",))
    due_amount: float = Field(default=0.0, validation_alias=AliasChoices("DueAmount",))


class LoanSummary(TolerantModel):
    finance_id: str = Field(
        default="",
        validation_alias=AliasChoices("FinanceId", "FinanceID", "financeId", "LoanId"),
    )
    agreement_no: str = Field(
        default="",
        validation_alias=AliasChoices("AgreementNo", "AgreementNumber", "agreementNo"),
    )
    # Confirmed live (2026-07-14) field names from GetLoanAgreementNoAsync —
    # GetLoanByMobileNumber returns blank/zero for all of these under the
    # originally-guessed names (ProductType/OverdueAmount/DPD/Status), so the
    # real AllCloud names are added alongside the guesses.
    product_type: str = Field(
        default="",
        validation_alias=AliasChoices(
            "ProductType", "Product", "ProductName", "Scheme", "LoanType", "ProductCategory"
        ),
    )
    customer_name: str = Field(
        default="", validation_alias=AliasChoices("CustomerName", "Name")
    )
    emi_amount: float = Field(
        default=0.0,
        validation_alias=AliasChoices("EMIAmount", "EmiAmount", "EMI", "InstallmentAmount"),
    )
    # Confirmed live (2026-07-15): GetLoanAgreementNoAsync has BOTH
    # NextPaymentDate (stale/last-processed — NOT the next due date) and
    # NextEMIDueDate (the real next due date). NextEMIDueDate must win, so
    # it's listed first — AliasChoices picks the first alias present.
    next_due_date: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NextEMIDueDate", "NextDueDate", "DueDate", "NextInstallmentDate", "NextPaymentDate"
        ),
    )
    # Confirmed live (2026-07-15): the payload has SEVERAL "total" fields at
    # once (TotalDueAmount=26403, TotalEMIOverdueAmount=28461,
    # TotalLoanOverdueAmount=98047, LoanTotalDue=95989) — the last two are
    # full-payoff figures, not current dues. TotalDueAmount is the correct
    # "EMI overdue" amount and must be listed first.
    overdue_amount: float = Field(
        default=0.0,
        validation_alias=AliasChoices(
            "TotalDueAmount", "OverdueAmount", "TotalOverdue", "OverDueAmount",
            "TotalLoanOverdueAmount", "TotalEMIOverdueAmount", "LoanTotalDue",
        ),
    )
    dpd: int = Field(
        default=0, validation_alias=AliasChoices("DPD", "Dpd", "DaysPastDue", "DPDDays")
    )
    status: str = Field(
        default="",
        validation_alias=AliasChoices(
            "Status", "LoanStatus", "AccountStatus", "StatusId", "DisbursementStatus"
        ),
    )
    loan_amount: float = Field(
        default=0.0,
        validation_alias=AliasChoices("LoanAmount", "FinanceAmount", "SanctionAmount", "TotalAmount"),
    )
    # Confirmed live (2026-07-14), GetLoanAgreementNoAsync loan-detail page
    # fields (see routers/payments.py pay_page):
    duration: int = Field(default=0, validation_alias=AliasChoices("Duration",))
    no_of_paid_emi: float = Field(default=0.0, validation_alias=AliasChoices("NoOfPaidEMI",))
    emi_due_count: float = Field(default=0.0, validation_alias=AliasChoices("EMIDueCount",))
    lpi_dues: float = Field(default=0.0, validation_alias=AliasChoices("LPIDues",))
    total_vas_dues: float = Field(default=0.0, validation_alias=AliasChoices("TotalVASDues",))
    total_emi_overdue_amount: float = Field(
        default=0.0, validation_alias=AliasChoices("TotalEMIOverdueAmount",)
    )
    repayment_schedules: list[RepaymentScheduleEntry] = Field(
        default_factory=list, validation_alias=AliasChoices("RepaymentSchedules",)
    )
    # Confirmed live (2026-07-14): GetLoanAgreementNoAsync has NEITHER a
    # DOB NOR a Contact/mobile field at the loan level — the only identity
    # data is the primary borrower's CustomerId under lstCoBorrowers, which
    # is cross-checked against GetCustomerSearch's CustomerId instead.
    co_borrowers: list[CoBorrower] = Field(
        default_factory=list, validation_alias=AliasChoices("lstCoBorrowers", "CoBorrowers")
    )

    @property
    def primary_customer_id(self) -> str | None:
        for cb in self.co_borrowers:
            if cb.order_type_id.lower() == "primary" and cb.customer_id:
                return cb.customer_id
        return self.co_borrowers[0].customer_id if self.co_borrowers else None

    @property
    def primary_customer_name(self) -> str:
        for cb in self.co_borrowers:
            if cb.order_type_id.lower() == "primary" and "customer" in cb.entity_type_id.lower():
                return cb.borrower_name
        return self.customer_name

    @property
    def regular_emi_amount(self) -> float:
        """The steady-state EMI, taken from the 2nd schedule entry — the
        1st installment's DueAmount often differs (day-1 adjustments)."""
        if len(self.repayment_schedules) > 1:
            return self.repayment_schedules[1].due_amount
        if self.repayment_schedules:
            return self.repayment_schedules[0].due_amount
        return self.emi_amount


class EmiDueEntry(TolerantModel):
    """One row of GetRepaymentForLoanByLoanId's confirmed-live `EmiDues`
    breakdown — EMIType is "Over Due" or "Up Coming"."""

    emi_type: str = Field(default="", validation_alias=AliasChoices("EMIType",))
    emi_amount: float = Field(default=0.0, validation_alias=AliasChoices("EMIAmount",))
    due_date: str = Field(default="", validation_alias=AliasChoices("EMIDueDate",))


class RepaymentDue(TolerantModel):
    """Live dues — always fetched fresh from LMS, never cached.

    Confirmed live (2026-07-14) field names differ substantially from the
    originally-guessed ones: the current-due amount is `BalanceAmount` /
    `EMIdues` (not `DueAmount`), penal charges are `LPIDue` (not
    `LPIAmount`), and there is no flat overdue-amount/next-due-date field at
    all — both live only inside the nested `EmiDues` breakdown, keyed by
    `EMIType` ("Over Due" / "Up Coming"). GetLoanByMobileNumber's own
    overdue/status/next-due fields are unreliable, so the dashboard derives
    all of that from this endpoint instead — see `overdue_amount`/
    `next_due_date`/`is_overdue` below.
    """

    finance_id: str = Field(
        default="", validation_alias=AliasChoices("FinanceId", "FinanceID", "LoanId")
    )
    due_amount: float = Field(
        default=0.0,
        validation_alias=AliasChoices(
            "DueAmount", "EMIDue", "InstallmentDue", "TotalDue", "BalanceAmount", "EMIdues"
        ),
    )
    lpi_amount: float = Field(
        default=0.0,
        validation_alias=AliasChoices(
            "LPIAmount", "LPI", "LPC", "PenalCharges", "LatePaymentCharges", "LPIDue"
        ),
    )
    collection_charges: float = Field(
        default=0.0,
        validation_alias=AliasChoices("CollectionCharges", "CollectionCharge", "OtherCharges"),
    )
    vas_due: float = Field(default=0.0, validation_alias=AliasChoices("VasDue", "VASDue"))
    hand_loan: float = Field(default=0.0, validation_alias=AliasChoices("HandLoan",))
    total_due: float = Field(
        default=0.0,
        validation_alias=AliasChoices("TotalDueAmount", "TotalPayable", "TotalOutstandingDue"),
    )
    emi_amount: float = Field(
        default=0.0, validation_alias=AliasChoices("EMIAmount", "EmiAmount", "EMI")
    )
    emi_dues_breakdown: list[EmiDueEntry] = Field(
        default_factory=list, validation_alias=AliasChoices("EmiDues",)
    )

    def computed_total(self) -> float:
        return round(
            self.total_due
            or (self.due_amount + self.lpi_amount + self.collection_charges
                + self.vas_due + self.hand_loan),
            2,
        )

    @property
    def overdue_amount(self) -> float:
        return sum(
            e.emi_amount for e in self.emi_dues_breakdown if "over" in e.emi_type.lower()
        )

    @property
    def is_overdue(self) -> bool:
        return self.overdue_amount > 0

    @property
    def next_due_date(self) -> str:
        for e in self.emi_dues_breakdown:
            if "over" not in e.emi_type.lower() and e.due_date:
                return e.due_date
        return ""


class LccDetails(TolerantModel):
    """GetLccDetailsByAgreementNo (voicecall) — confirmed live 2026-07-14.
    A richer per-agreement summary than GetLoanByMobileNumber/
    GetRepaymentForLoanByLoanId: clean Status text, a real next-due date
    (InstallmentDueDate), and TotalDues/LPCDue already computed. Used to
    power the dashboard cards; the pay page still uses RepaymentDue for the
    granular due/LPI/collection-charge breakdown (RBI disclosure)."""

    finance_id: str = Field(default="", validation_alias=AliasChoices("FinanceId",))
    agreement_no: str = Field(default="", validation_alias=AliasChoices("AgreementNo",))
    customer_name: str = Field(default="", validation_alias=AliasChoices("CustomerName",))
    customer_contact: str = Field(default="", validation_alias=AliasChoices("CustomerContact",))
    vehicle_class: str = Field(default="", validation_alias=AliasChoices("VehicleClass",))
    registration_no: str = Field(default="", validation_alias=AliasChoices("RegistrationNo",))
    installment_due_date: str = Field(
        default="", validation_alias=AliasChoices("InstallmentDueDate",)
    )
    current_month_tbc: float = Field(
        default=0.0, validation_alias=AliasChoices("CurrentMonthTBC",)
    )
    total_dues: float = Field(default=0.0, validation_alias=AliasChoices("TotalDues",))
    lpc_due: float = Field(default=0.0, validation_alias=AliasChoices("LPCDue",))
    vas_due_amount: float = Field(default=0.0, validation_alias=AliasChoices("VasDueAmount",))
    hand_loan_due_amount: float = Field(
        default=0.0, validation_alias=AliasChoices("HandLoanDueAmount",)
    )
    emi_due_count: float = Field(default=0.0, validation_alias=AliasChoices("EMIDueCount",))
    running_emi_count: int = Field(default=0, validation_alias=AliasChoices("RunningEmiCount",))
    status: str = Field(default="", validation_alias=AliasChoices("Status",))

    @property
    def is_overdue(self) -> bool:
        # Status ("Active"/"Closed"/...) doesn't reliably signal delinquency
        # — confirmed live, a loan with real arrears still showed "Active".
        # A nonzero late-payment charge is a much more direct overdue signal.
        return self.lpc_due > 0


class QRCodeResponse(TolerantModel):
    """GetQRCode — confirmed live 2026-07-15. Despite the name, the response
    carries NO QR image; it returns a payment-gateway checkout URL
    ({"Status":1, "custname", "urn", "dueamount", "URL":"https://pay.alcd.in/
    Checkout/Pay?id=...", "aggrementno"}). The portal renders a QR locally
    from that URL (scan option) alongside a Pay Now button (click option)."""

    qr_base64: str = Field(
        default="",
        validation_alias=AliasChoices(
            "QRCodeImage", "QRCode", "QRImage", "QrCodeBase64", "Base64Image", "QRString"
        ),
    )
    pay_url: str = Field(
        default="",
        validation_alias=AliasChoices("URL", "PaymentURL", "PayURL", "CheckoutURL"),
    )
    status: int = Field(default=0, validation_alias=AliasChoices("Status",))
    customer_name: str = Field(default="", validation_alias=AliasChoices("custname",))
    sms_link: str = Field(
        default="",
        validation_alias=AliasChoices("SMSLink", "PaymentLink", "SmsLink", "Link"),
    )
    reference: str = Field(
        default="",
        validation_alias=AliasChoices("urn", "ReferenceNo", "TransactionRef", "OrderId", "TxnId"),
    )
