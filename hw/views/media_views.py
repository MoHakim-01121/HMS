"""Uploaded files, served only to users allowed to see what they belong to.

Proofs of transfer, refund slips and CL/invoice attachments carry account
numbers and guest documents, so /media/ is no longer a public folder. Every
request reaches this view; the folder decides which permission is needed
(MEDIA_RULES), and a folder without a rule is not served at all.

Production (nginx): /media/ is proxied to Django like any page, and Django
answers with X-Accel-Redirect so nginx still sends the bytes:

    location /media/ { proxy_pass http://<app>; ... }        # no alias any more
    location /protected-media/ { internal; alias <MEDIA_ROOT>/; }

with MEDIA_ACCEL_REDIRECT=/protected-media/ in the environment.
"""
import mimetypes
import os
import posixpath
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join

from ..branch_scope import covers_all, scope
from ..permissions import can

PUBLIC = 'public'
LOGGED_IN = 'logged_in'


def _proof_of(model_name, *modules):
    """A proof file: the user views one of `modules` and the record holding
    the file belongs to the user's branches."""
    def rule(user, path):
        from django.apps import apps
        model = apps.get_model('hw', model_name)
        return (any(can(user, m, 'view') for m in modules)
                and scope(model.objects.filter(proof=path), user).exists())
    return rule


def _expense_receipt(user, path):
    """expenses/receipts/… — a receipt on a line of an expense of the user's
    branches, with expenses.view."""
    from ..models import Expense
    return (can(user, 'expenses', 'view')
            and scope(Expense.objects.filter(lines__receipts__file=path), user).exists())


def _ledger_proof(user, path):
    """Proof attached to a journal entry: head office's ledger."""
    return covers_all(user) and any(can(user, m, 'view') for m in ('journal', 'statements'))


def _owner_pk(path):
    """<id> of attachments/<kind>/<id>/…, or None."""
    try:
        return int(path.split('/')[2])
    except (IndexError, ValueError):
        return None


def _invoice_attachment(user, path):
    """attachments/invoice/<id>/… — an invoice of the user's branches, with
    invoice.view."""
    from ..models import Invoice
    return (can(user, 'invoice', 'view')
            and scope(Invoice.objects.filter(pk=_owner_pk(path)), user).exists())


def _cl_attachment(user, path):
    """attachments/cl/<id>/… — a CL of the user's branches, with cl.view."""
    from ..models import ConfirmationLetter
    return (can(user, 'cl', 'view')
            and scope(ConfirmationLetter.objects.filter(pk=_owner_pk(path)), user).exists())


# Folder prefix → who may read it. A proof is readable from every screen that
# links it (e.g. a payment proof from the invoice page).
MEDIA_RULES = (
    ('landing/', PUBLIC),                       # public landing page images
    ('avatars/', LOGGED_IN),
    ('attachments/invoice/', _invoice_attachment),
    ('attachments/cl/', _cl_attachment),
    ('payments/proof/', _proof_of('PaymentRecord', 'payments', 'invoice', 'statements')),
    ('refunds/proof/', _proof_of('ClientRefund', 'payments', 'statements')),
    ('exchange/proof/', _proof_of('CurrencyExchange', 'bank')),
    ('expenses/proof/', _proof_of('Expense', 'expenses')),
    ('expenses/receipts/', _expense_receipt),
    ('remittance/proof/', _proof_of('Remittance', 'remittance')),
    ('ledger/proof/', _ledger_proof),
)

# Shown in the browser; anything else (spreadsheets, text) is downloaded.
_INLINE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'}


def _rule_for(path):
    for prefix, rule in MEDIA_RULES:
        if path.startswith(prefix):
            return rule
    return None


def protected_media(request, path):
    path = posixpath.normpath(path).lstrip('/')
    if path.startswith('..') or '\x00' in path:
        raise Http404
    rule = _rule_for(path)
    if rule is None:
        raise Http404
    if rule != PUBLIC:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        # 404, not 403: a file the user may not see does not exist for them.
        if rule != LOGGED_IN and not rule(request.user, path):
            raise Http404
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except Exception:
        raise Http404 from None
    if not os.path.isfile(full):
        raise Http404

    content_type = mimetypes.guess_type(full)[0] or 'application/octet-stream'
    if settings.MEDIA_ACCEL_REDIRECT:
        response = HttpResponse(content_type=content_type)
        response['X-Accel-Redirect'] = settings.MEDIA_ACCEL_REDIRECT.rstrip('/') + '/' + quote(path)
    else:
        response = FileResponse(open(full, 'rb'), content_type=content_type)
    disposition = 'inline' if content_type in _INLINE_TYPES else 'attachment'
    response['Content-Disposition'] = f"{disposition}; filename*=UTF-8''{quote(os.path.basename(full))}"
    response['Cache-Control'] = 'public, max-age=86400' if rule == PUBLIC else 'private, max-age=3600'
    return response


protected_media.access_guard = ('media', 'MEDIA_RULES')
