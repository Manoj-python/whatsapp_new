"""Login gate for internal pages and APIs (8 Nov 2026).

A crawl found these answering anyone on the internet without a login, among them the full
WhatsApp contact lists (/api/contacts/ 13.8 MB, /messaging2/api/contacts2/ 6 MB), employee
lists and search, the bulk SMS / notice / batch / email screens, case APIs and the DB schema.

Any existing login passes: Django auth (admin panel) or the legacy session keys the chat apps
and FinanceHub set. Left open on purpose: /customer/ (the SMSquare portal calls it server to
server), webhooks, the DRF token APIs (/sms/api/, /email/api/) and /sms/download/ (customers'
document links in SMS).
"""
from django.http import JsonResponse
from django.shortcuts import redirect

PROTECTED = (
    "/api/", "/employees/", "/batch/", "/notice/", "/sms/", "/email/", "/meghaai/",
    "/adminpanel/api/", "/messaging2/api/", "/splcases_app/api/",
    "/financehub/employees/", "/financehub/api/",
    "/messaging2/chat/", "/splcases_app/chat3/",
)
OPEN = ("/sms/api/", "/email/api/", "/sms/download/")
SESSION_KEYS = ("messaging_user", "messaging2_user", "messaging3_user", "financehub_user")


class LoginGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        p = request.path
        if p.startswith(PROTECTED) and not p.startswith(OPEN):
            user = getattr(request, "user", None)
            ok = (user is not None and user.is_authenticated) or any(
                request.session.get(k) for k in SESSION_KEYS)
            if not ok:
                if "/api/" in p or request.headers.get("x-requested-with") == "XMLHttpRequest" \
                        or "application/json" in request.headers.get("accept", ""):
                    return JsonResponse({"success": False, "error": "Login required"}, status=401)
                return redirect("/financehub/login/" if p.startswith("/financehub/") else "/adminpanel/login/")
        return self.get_response(request)
