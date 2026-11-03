"""Penomoran dokumen berurutan (INV-001, CL-003, PAY-0001, JE-000123, …).

Semua jenis nomor bertumpu pada satu baris ``DocumentSequence`` per kunci:

* ``generate_sequential_number`` / ``next_number(allocate=True)`` — mengunci
  baris counter (SELECT … FOR UPDATE), menaikkannya, dan mengembalikan nomor
  baru. **Wajib dipanggil di dalam transaksi yang juga meng-INSERT dokumennya**,
  supaya kunci baru lepas setelah dokumen tersimpan. Dipanggil di luar
  transaksi → ``NumberingError`` (salah pakai ketahuan, bukan bentrok diam-diam).
* ``peek_number`` — nomor usulan untuk form (GET). Tidak mengunci, tidak memakai
  nomor.
* ``advance_number`` — dipanggil setelah menyimpan dokumen bernomor ketikan
  user (CL, Invoice, Penalty), supaya counter tidak tertinggal di belakang
  nomor yang sudah dipakai.

Nomor yang sudah terpakai (misalnya diketik manual) selalu dilompati.
Baris counter dibuat saat pertama dibutuhkan, dengan nilai awal = angka
terbesar yang sudah ada untuk prefiks itu (satu kali pindai).
"""
import re

from django.db import IntegrityError, connection, transaction

_TAIL = re.compile(r'(\d+)$')


class NumberingError(RuntimeError):
    """Nomor dialokasikan di luar transaksi."""


def _prefix(prefix):
    return prefix if prefix.endswith('-') else f'{prefix}-'


def _key(prefix, key):
    return key or _prefix(prefix).rstrip('-')


def _fmt(prefix, n, padding):
    return f'{_prefix(prefix)}{n:0{padding}d}'


def _field(model, field):
    return field or f'{model._meta.model_name}_number'


def _tail(number, prefix):
    number = str(number)
    if not number.startswith(_prefix(prefix)):
        return None
    m = _TAIL.search(number[len(_prefix(prefix)):])
    return int(m.group(1)) if m else None


def _max_existing(model, prefix, field, extra_filter, legacy_prefixes=()):
    best = 0
    for candidate in dict.fromkeys((prefix, *legacy_prefixes)):
        qs = model.objects.filter(**{f'{field}__startswith': _prefix(candidate)}, **(extra_filter or {}))
        for value in qs.values_list(field, flat=True).iterator():
            n = _tail(value, candidate)
            if n is not None and n > best:
                best = n
    return best


def _first_free(model, prefix, field, padding, extra_filter, start):
    qs = model.objects.filter(**(extra_filter or {}))
    n = start
    while True:
        n += 1
        number = _fmt(prefix, n, padding)
        if not qs.filter(**{field: number}).exists():
            return n, number


def _locked_sequence(key, model, prefix, field, extra_filter, legacy_prefixes=()):
    from .models.sequence import DocumentSequence

    legacy_keys = [
        _key(candidate, None) for candidate in legacy_prefixes
        if _key(candidate, None) != key
    ]
    seq = DocumentSequence.objects.select_for_update().filter(key=key).first()
    if seq is None:
        start = _max_existing(model, prefix, field, extra_filter, legacy_prefixes)
        if legacy_keys:
            start = max(start, max(
                DocumentSequence.objects.filter(key__in=legacy_keys).values_list('last_value', flat=True),
                default=0,
            ))
        try:
            with transaction.atomic():
                DocumentSequence.objects.create(key=key, last_value=start)
        except IntegrityError:
            pass  # transaksi lain membuatnya lebih dulu; kita tunggu kuncinya di bawah
        seq = DocumentSequence.objects.select_for_update().get(key=key)
    elif legacy_prefixes:
        start = _max_existing(model, prefix, field, extra_filter, legacy_prefixes)
        if legacy_keys:
            start = max(start, max(
                DocumentSequence.objects.filter(key__in=legacy_keys).values_list('last_value', flat=True),
                default=0,
            ))
        if start > seq.last_value:
            seq.last_value = start
            seq.save(update_fields=['last_value'])
    return seq


def next_number(model, prefix, *, field=None, padding=3, extra_filter=None, key=None, allocate=True,
                legacy_prefixes=()):
    field = _field(model, field)
    key = _key(prefix, key)
    if not allocate:
        return peek_number(
            model, prefix, field=field, padding=padding, extra_filter=extra_filter, key=key,
            legacy_prefixes=legacy_prefixes,
        )
    if not connection.in_atomic_block:
        raise NumberingError(
            f"Nomor {key} harus dialokasikan di dalam transaction.atomic() "
            "yang juga menyimpan dokumennya."
        )
    with transaction.atomic():
        seq = _locked_sequence(key, model, prefix, field, extra_filter, legacy_prefixes)
        n, number = _first_free(model, prefix, field, padding, extra_filter, seq.last_value)
        seq.last_value = n
        seq.save(update_fields=['last_value'])
    return number


def generate_sequential_number(model, prefix, field=None, padding=3, extra_filter=None, key=None,
                               legacy_prefixes=()):
    """Alokasikan nomor berikutnya (lihat docstring modul)."""
    return next_number(
        model, prefix, field=field, padding=padding, extra_filter=extra_filter, key=key,
        legacy_prefixes=legacy_prefixes,
    )


def peek_number(model, prefix, *, field=None, padding=3, extra_filter=None, key=None,
                legacy_prefixes=()):
    """Nomor usulan tanpa mengunci atau memakai counter."""
    from .models.sequence import DocumentSequence
    field = _field(model, field)
    seq = DocumentSequence.objects.filter(key=_key(prefix, key)).first()
    start = seq.last_value if seq else 0
    start = max(start, _max_existing(model, prefix, field, extra_filter, legacy_prefixes))
    legacy_keys = [
        _key(candidate, None) for candidate in legacy_prefixes
        if _key(candidate, None) != _key(prefix, key)
    ]
    if legacy_keys:
        start = max(start, max(
            DocumentSequence.objects.filter(key__in=legacy_keys).values_list('last_value', flat=True),
            default=0,
        ))
    return _first_free(model, prefix, field, padding, extra_filter, start)[1]


def advance_number(model, prefix, number, *, field=None, extra_filter=None, key=None,
                   legacy_prefixes=()):
    """Naikkan counter ke `number` bila nomor itu (ketikan user) melampauinya."""
    n = _tail(number, prefix)
    if n is None:
        return
    field = _field(model, field)
    with transaction.atomic():
        seq = _locked_sequence(
            _key(prefix, key), model, prefix, field, extra_filter, legacy_prefixes,
        )
        if n > seq.last_value:
            seq.last_value = n
            seq.save(update_fields=['last_value'])
