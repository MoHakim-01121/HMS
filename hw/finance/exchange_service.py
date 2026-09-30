"""Currency exchange (Penukaran Valas) — see hw/models/currency_exchange.py.

No journal entry: the exchange stays inside the organisation and does not
change what the branch owes HQ in SAR. What it changes is which currency the
branch holds, recorded as two cash-book rows with their real amounts.
"""
from decimal import Decimal

from django.db import transaction

from ..models.currency_exchange import CurrencyExchange
from .bank_ledger import record_bank_transaction, void_bank_transactions
from .errors import FinanceError
from .posting import check_period_postable, get_period_for_date

SOURCE_OUT = 'CurrencyExchangeOut'
SOURCE_IN = 'CurrencyExchangeIn'

# A rate this far from the previous exchange of the same pair is worth a second
# look (a typo in one of the two amounts), but it is only a warning.
RATE_WARNING_PCT = Decimal('3')


def previous_rate(from_currency, to_currency, *, exclude_pk=None):
    """Rate of the latest active exchange for the same currency pair, or None."""
    qs = CurrencyExchange.objects.filter(status=CurrencyExchange.STATUS_ACTIVE)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for ex in qs.order_by('-exchange_date', '-pk').select_related('from_account', 'to_account')[:50]:
        if ex.from_currency == from_currency and ex.to_currency == to_currency:
            return ex.rate
    return None


def rate_warning(rate, prev):
    """Deviation in percent when it exceeds RATE_WARNING_PCT, else None."""
    if prev is None or not prev:
        return None
    pct = abs(Decimal(rate) - prev) / prev * 100
    return pct.quantize(Decimal('0.1')) if pct > RATE_WARNING_PCT else None


@transaction.atomic
def record_exchange(*, from_account, amount_out, to_account, amount_in, exchange_date,
                    created_by, reference='', note='', proof=None):
    if from_account is None or to_account is None:
        raise FinanceError('Pilih rekening asal dan rekening tujuan.')
    if from_account == to_account:
        raise FinanceError('Rekening asal dan tujuan harus berbeda.')
    if from_account.currency == to_account.currency:
        raise FinanceError('Penukaran valas harus antar mata uang yang berbeda.')
    if not amount_out or amount_out <= 0 or not amount_in or amount_in <= 0:
        raise FinanceError('Nominal keluar dan masuk harus lebih dari 0.')
    check_period_postable(get_period_for_date(exchange_date))

    ex = CurrencyExchange.objects.create(
        exchange_number=CurrencyExchange.generate_number(),
        exchange_date=exchange_date,
        amount_out=amount_out, amount_in=amount_in,
        reference=reference, note=note, created_by=created_by,
        from_account=from_account, to_account=to_account,
    )
    if proof:
        ex.proof = proof
        ex.save(update_fields=['proof'])
    # amount_sar = 0: the SAR value held does not change, only its currency.
    record_bank_transaction(
        account=from_account, direction='out', amount_sar=0, currency=from_account.currency,
        amount=amount_out, source_type=SOURCE_OUT, source_id=ex.pk,
        transaction_date=exchange_date, reference=reference or ex.exchange_number,
    )
    record_bank_transaction(
        account=to_account, direction='in', amount_sar=0, currency=to_account.currency,
        amount=amount_in, source_type=SOURCE_IN, source_id=ex.pk,
        transaction_date=exchange_date, reference=reference or ex.exchange_number,
    )
    return ex


@transaction.atomic
def void_exchange(ex, *, reason=''):
    ex = CurrencyExchange.objects.select_for_update().get(pk=ex.pk)
    if ex.status == CurrencyExchange.STATUS_VOIDED:
        raise FinanceError(f'{ex.exchange_number} sudah dibatalkan.')
    check_period_postable(get_period_for_date(ex.exchange_date))
    void_bank_transactions(SOURCE_OUT, ex.pk)
    void_bank_transactions(SOURCE_IN, ex.pk)
    ex.status = CurrencyExchange.STATUS_VOIDED
    ex.voided_reason = reason
    ex.save(update_fields=['status', 'voided_reason'])
    return ex
