"""English / Telugu strings. Language chosen via /lang/{code} (cookie)."""

LANGS = ("en", "te")

STRINGS: dict[str, dict[str, str]] = {
    "brand": {"en": "SMSquare Credit Services", "te": "SMSquare క్రెడిట్ సర్వీసెస్"},
    "tagline": {"en": "Vehicle Finance Customer Portal", "te": "వాహన ఫైనాన్స్ కస్టమర్ పోర్టల్"},
    "login_title": {"en": "Login to your account", "te": "మీ ఖాతాలోకి లాగిన్ అవ్వండి"},
    "mobile_number": {"en": "Registered mobile number", "te": "నమోదిత మొబైల్ నంబర్"},
    "send_otp": {"en": "Send OTP", "te": "OTP పంపండి"},
    "enter_otp": {"en": "Enter the 6-digit OTP sent to", "te": "ఈ నంబర్‌కు పంపిన 6 అంకెల OTP నమోదు చేయండి"},
    "verify_login": {"en": "Verify & Login", "te": "ధృవీకరించి లాగిన్ అవ్వండి"},
    "resend_otp": {"en": "Resend OTP", "te": "OTP మళ్లీ పంపండి"},
    "resend_wait": {"en": "You can resend in", "te": "మళ్లీ పంపడానికి వేచి ఉండండి"},
    "alt_login": {"en": "Login with Agreement No. + Mobile + Date of Birth", "te": "అగ్రిమెంట్ నంబర్ + మొబైల్ + పుట్టిన తేదీతో లాగిన్"},
    "mobile_login": {"en": "Login with mobile number", "te": "మొబైల్ నంబర్‌తో లాగిన్"},
    "agreement_no": {"en": "Agreement number (e.g. LNTSPAR-240300005)", "te": "అగ్రిమెంట్ నంబర్ (ఉదా: LNTSPAR-240300005)"},
    "dob": {"en": "Date of birth", "te": "పుట్టిన తేదీ"},
    "continue": {"en": "Continue", "te": "కొనసాగించండి"},
    "logout": {"en": "Logout", "te": "లాగ్ అవుట్"},
    "welcome": {"en": "Welcome", "te": "స్వాగతం"},
    "loading": {"en": "Please wait…", "te": "దయచేసి వేచి ఉండండి…"},
    "your_loans": {"en": "Your Loans", "te": "మీ రుణాలు"},
    "product": {"en": "Product", "te": "ప్రొడక్ట్"},
    "emi": {"en": "EMI", "te": "EMI"},
    "next_due": {"en": "Next due", "te": "తదుపరి గడువు"},
    "overdue": {"en": "Overdue", "te": "బకాయి"},
    "dpd": {"en": "Days past due", "te": "గడువు దాటిన రోజులు"},
    "status": {"en": "Status", "te": "స్థితి"},
    "view_pay": {"en": "View dues & pay", "te": "బకాయిలు చూసి చెల్లించండి"},
    "loan_details": {"en": "Loan Details", "te": "రుణ వివరాలు"},
    "customer_name": {"en": "Customer name", "te": "కస్టమర్ పేరు"},
    "loan_type": {"en": "Loan type", "te": "రుణ రకం"},
    "loan_amount": {"en": "Loan amount", "te": "రుణ మొత్తం"},
    "total_emi": {"en": "Total EMIs", "te": "మొత్తం EMIలు"},
    "no_of_emi_received": {"en": "EMIs received", "te": "అందిన EMIలు"},
    "emi_due_count": {"en": "EMIs due", "te": "బకాయి EMIలు"},
    "emi_overdue": {"en": "EMI overdue", "te": "EMI బకాయి"},
    "late_charges": {"en": "Late charges", "te": "ఆలస్య ఛార్జీలు"},
    "vas_charges": {"en": "VAS charges", "te": "VAS ఛార్జీలు"},
    "total_due": {"en": "Total due", "te": "మొత్తం బకాయి"},
    "dues_title": {"en": "Current Dues", "te": "ప్రస్తుత బకాయిలు"},
    "due_emi": {"en": "EMI due", "te": "EMI బకాయి"},
    "penal_charges": {"en": "Penal charges (LPI)", "te": "జరిమానా ఛార్జీలు (LPI)"},
    "collection_charges": {"en": "Collection charges", "te": "వసూలు ఛార్జీలు"},
    "total_payable": {"en": "Total payable", "te": "మొత్తం చెల్లించవలసినది"},
    "penal_disclosure": {
        "en": "Penal charges are levied as per your loan agreement and RBI guidelines. The break-up above is disclosed in full before you pay.",
        "te": "జరిమానా ఛార్జీలు మీ రుణ ఒప్పందం మరియు RBI మార్గదర్శకాల ప్రకారం విధించబడతాయి. చెల్లించే ముందు పూర్తి వివరాలు పైన చూపబడ్డాయి.",
    },
    "pay_option": {"en": "How much would you like to pay?", "te": "మీరు ఎంత చెల్లించాలనుకుంటున్నారు?"},
    "pay_total": {"en": "Total due", "te": "మొత్తం బకాయి"},
    "pay_emi": {"en": "EMI amount", "te": "EMI మొత్తం"},
    "pay_part": {"en": "Any other payment", "te": "ఇతర చెల్లింపు"},
    "show_qr": {"en": "Show UPI QR code", "te": "UPI QR కోడ్ చూపించండి"},
    "pay_now": {"en": "Pay Now (UPI / Card / Netbanking)", "te": "ఇప్పుడే చెల్లించండి (UPI / కార్డ్ / నెట్‌బ్యాంకింగ్)"},
    "sms_link": {"en": "Or get payment link by SMS", "te": "లేదా SMS ద్వారా చెల్లింపు లింక్ పొందండి"},
    "payment_success": {"en": "Payment received!", "te": "చెల్లింపు అందింది!"},
    "account_updating": {
        "en": "Your payment will be processed once we get confirmation from the payment gateway.",
        "te": "పేమెంట్ గేట్‌వే నుండి నిర్ధారణ వచ్చిన తర్వాత మీ చెల్లింపు ప్రాసెస్ చేయబడుతుంది.",
    },
    "download_receipt": {"en": "Download receipt (PDF)", "te": "రసీదు డౌన్‌లోడ్ (PDF)"},
    "back_dashboard": {"en": "Back to dashboard", "te": "డాష్‌బోర్డ్‌కు తిరిగి"},
    "helpline": {"en": "Helpline", "te": "హెల్ప్‌లైన్"},
    "grievance": {"en": "Grievance Redressal", "te": "ఫిర్యాదుల పరిష్కారం"},
    "ombudsman": {"en": "RBI Ombudsman", "te": "RBI అంబుడ్స్‌మన్"},
    "fpc": {
        "en": "We follow the RBI Fair Practices Code. All charges are disclosed before payment.",
        "te": "మేము RBI ఫెయిర్ ప్రాక్టీసెస్ కోడ్‌ను పాటిస్తాము. చెల్లింపుకు ముందు అన్ని ఛార్జీలు తెలియజేయబడతాయి.",
    },
    "session_expired": {"en": "Your session expired. Please login again.", "te": "మీ సెషన్ ముగిసింది. దయచేసి మళ్లీ లాగిన్ అవ్వండి."},
    "no_loans": {"en": "No loans found for this account.", "te": "ఈ ఖాతాకు రుణాలు కనబడలేదు."},
    # errors
    "err_mobile_not_found": {"en": "This mobile number is not registered with us.", "te": "ఈ మొబైల్ నంబర్ మా వద్ద నమోదు కాలేదు."},
    "err_invalid_mobile": {"en": "Please enter a valid 10-digit mobile number.", "te": "దయచేసి సరైన 10 అంకెల మొబైల్ నంబర్ నమోదు చేయండి."},
    "err_agreement_not_found": {"en": "Agreement number and date of birth do not match our records.", "te": "అగ్రిమెంట్ నంబర్ మరియు పుట్టిన తేదీ మా రికార్డులతో సరిపోలడం లేదు."},
    "otp_rate_limited": {"en": "Too many OTP requests. Please try again after an hour.", "te": "చాలా OTP అభ్యర్థనలు. గంట తర్వాత మళ్లీ ప్రయత్నించండి."},
    "otp_resend_wait": {"en": "Please wait before requesting another OTP.", "te": "మరో OTP అడగడానికి ముందు కొంచెం వేచి ఉండండి."},
    "otp_expired": {"en": "OTP expired. Please request a new one.", "te": "OTP గడువు ముగిసింది. కొత్తది అడగండి."},
    "otp_attempts_exhausted": {"en": "Too many wrong attempts. Please request a new OTP.", "te": "చాలా తప్పు ప్రయత్నాలు. కొత్త OTP అడగండి."},
    "otp_not_found": {"en": "No active OTP. Please request one.", "te": "యాక్టివ్ OTP లేదు. దయచేసి అడగండి."},
    "otp_wrong": {"en": "Incorrect OTP. Please try again.", "te": "తప్పు OTP. మళ్లీ ప్రయత్నించండి."},
    "pay_min_part": {"en": "Minimum part payment is ₹{amount}.", "te": "కనీస పాక్షిక చెల్లింపు ₹{amount}."},
    "pay_exceeds_max": {"en": "Amount cannot exceed ₹{amount}.", "te": "మొత్తం ₹{amount} మించకూడదు."},
    "pay_bad_option": {"en": "Please choose a payment option.", "te": "దయచేసి చెల్లింపు ఎంపికను ఎంచుకోండి."},
    "err_lms_down": {
        "en": "We are unable to reach the loan system right now. Please try again in a few minutes.",
        "te": "ప్రస్తుతం లోన్ సిస్టమ్‌ను చేరుకోలేకపోతున్నాము. కొన్ని నిమిషాల్లో మళ్లీ ప్రయత్నించండి.",
    },
    "err_forbidden": {"en": "You do not have access to this loan.", "te": "ఈ రుణానికి మీకు యాక్సెస్ లేదు."},
}


def translate(key: str, lang: str = "en") -> str:
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


def make_translator(lang: str):
    return lambda key: translate(key, lang)
