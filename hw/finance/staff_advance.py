"""Uang operasional yang dipegang staf (uang muka staf).

Kantor memberi seorang staf uang lewat Transfer (rekening kantor -> uang muka
staf); staf membelanjakannya lewat Expense yang "dibayar dengan" uang muka
itu, dan mengembalikan sisanya lewat Transfer ke arah sebaliknya.

Aturan (keputusan 2026-10-17):
* Setiap user aktif yang punya akses ke cabang itu boleh memegang uang muka.
* Saldonya boleh minus: staf menalangi, kantor berutang kepadanya, dan
  transfer berikutnya ke staf menutupnya.

Satu staf punya satu MoneyAccount kind='staff' per cabang dan mata uang,
dibuat saat pertama kali ia diberi uang. Semua uang muka satu cabang dan mata
uang memakai satu akun buku besar (accounts.advance_ledger_for); saldo per
staf dibaca dari buku kas (BankTransaction) rekeningnya.
"""
from django.contrib.auth.models import User
from django.db.models import Case, F, Q, Sum, When

from ..models.bank import MoneyAccount
from ..models.bank_transaction import BankTransaction
from ..models.role import ADMIN_SLUG
from .accounts import advance_ledger_for


def display_name(user):
    return user.get_full_name() or user.username


def branch_holders(branch_code):
    """Users who may hold an advance at `branch_code`: active, and covering
    that branch (every branch for superusers, admins and all-branch users)."""
    return (
        User.objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True) | Q(profile__role=ADMIN_SLUG) | Q(profile__all_branches=True)
            | Q(profile__branch_access__branch_id=branch_code)
        )
        .distinct().order_by('first_name', 'last_name', 'username')
    )


def advance_account(holder, branch_code, currency, *, create=False):
    """The advance `holder` keeps at `branch_code` in `currency`, or None.
    With `create`, it is opened when missing (the first transfer to them)."""
    acc = MoneyAccount.objects.filter(
        kind=MoneyAccount.KIND_STAFF, holder=holder, branch_id=branch_code, currency=currency,
    ).first()
    if acc is None and create:
        acc = MoneyAccount.objects.create(
            kind=MoneyAccount.KIND_STAFF, holder=holder, branch_id=branch_code, currency=currency,
            name=display_name(holder), ledger_account_id=advance_ledger_for(branch_code, currency),
        )
    return acc


def balances(accounts):
    """{account pk: money held, in the account's own currency} from the cash
    book. Negative = the office owes that staff member."""
    ids = [a.pk for a in accounts]
    rows = (
        BankTransaction.objects.filter(account_id__in=ids)
        .exclude(status=BankTransaction.STATUS_VOIDED)
        .values('account_id')
        .annotate(net=Sum(Case(When(direction='in', then=F('amount')), default=-F('amount'))))
    )
    out = {pk: 0 for pk in ids}
    for r in rows:
        out[r['account_id']] = int(r['net'] or 0)
    return out


def balance(account):
    return balances([account])[account.pk]
