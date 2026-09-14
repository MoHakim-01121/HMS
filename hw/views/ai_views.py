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

from ..ai import generate_draft_message, get_chat_reply
from ..models import ActivityLog, Invoice, log_activity


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

    invoice = Invoice.objects.filter(pk=pk).first()
    if not invoice:
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

    history = request.session.get("ai_history", [])

    reply = get_chat_reply(message, history=history)

    if reply:
        history = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": reply},
        ]
        request.session["ai_history"] = history[-6:]  # keep last 3 exchanges
        log_activity(request.user, ActivityLog.ACTION_PDF, 'AI Chat', message[:100])

    return JsonResponse({"reply": reply or "Sorry, unable to process your question right now."})
