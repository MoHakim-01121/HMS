"""AI endpoints: draft-message generation and the assistant chat.

JSON endpoints (not Inertia pages), rate-limited per user. The model calls
themselves live in hw/ai.py — this module only handles request parsing,
scoping, and activity logging.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from ..ai import CHAT_MODULES, generate_draft_message, get_chat_reply
from ..models import ActivityLog, Invoice, log_activity
from ..branch_scope import scope
from ..permissions import can


@login_required
@require_POST
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def ai_draft_message(request):
    try:
        data = json.loads(request.body)
        invoice_type = data.get("type", "invoice")
        pk = int(data.get("pk"))
    except Exception:
        return JsonResponse({"error": "Invalid request."}, status=400)
    if invoice_type not in ("invoice", "invoice_lunas"):
        return JsonResponse({"error": "Invalid request."}, status=400)

    invoice = scope(Invoice.objects.all(), request.user).filter(pk=pk).first()
    # A user who may not view this kind of invoice, or another branch's, gets
    # the same answer as for one that does not exist.
    if not invoice or not can(request.user, 'invoice', 'view'):
        return JsonResponse({"error": "Invoice not found."}, status=404)

    result = generate_draft_message(invoice_type, invoice)
    log_activity(request.user, ActivityLog.ACTION_PDF, f'AI Draft: {invoice_type}', invoice.invoice_number)
    return JsonResponse({"message": result or "Failed to generate message."})


@login_required
@require_POST
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def ai_chat(request):
    try:
        data = json.loads(request.body)
        message = data.get("message", "").strip()
    except Exception:
        return JsonResponse({"reply": "Invalid request."}, status=400)

    if not message:
        return JsonResponse({"reply": "Question cannot be empty."})

    # The assistant only reads modules the user may view.
    modules = tuple(m for m in CHAT_MODULES if can(request.user, m, 'view'))
    if not modules:
        return JsonResponse({"reply": "You have no access to the data this assistant answers from."}, status=403)

    history = request.session.get("ai_history", [])

    reply = get_chat_reply(message, history=history, user=request.user, modules=modules)

    if reply:
        history = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": reply},
        ]
        request.session["ai_history"] = history[-6:]  # keep last 3 exchanges
        log_activity(request.user, ActivityLog.ACTION_PDF, 'AI Chat', message[:100])

    return JsonResponse({"reply": reply or "Sorry, unable to process your question right now."})


@login_required
@require_POST
def ai_chat_reset(request):
    """'New chat': forget the remembered exchanges, so the next question
    starts without the earlier ones as context."""
    request.session.pop("ai_history", None)
    return JsonResponse({"ok": True})
