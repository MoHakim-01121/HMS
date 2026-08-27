"""Tamper-evidence untuk journal: hash kanonik per entry + verifikasi rantai.

Setiap JournalEntry menyimpan `entry_hash` = sha256 dari isi kanoniknya
(entry + lines) digabung `prev_hash` (entry_hash dari entry ber-seq
sebelumnya di company yang sama). Mengubah baris mana pun secara retroaktif
memutus rantai — `verify_chain()` mendeteksinya.
"""
import hashlib
import json


_ENTRY_FIELDS = (
    "entry_number", "entry_type", "entry_date", "company", "seq",
    "is_reversal", "reverses_id", "reference_type", "reference_id", "description",
)
_LINE_FIELDS = (
    "line_no", "account_id", "debit", "credit", "currency",
    "client_id", "invoice_id", "reservation_id", "service_item_id",
    "penalty_id", "remittance_id", "note",
)


def _entry_payload(entry, line_dicts, prev_hash):
    return {
        "entry": {f: _s(getattr(entry, f, None)) for f in _ENTRY_FIELDS},
        "lines": [
            {f: _s(d.get(f)) for f in _LINE_FIELDS}
            for d in sorted(line_dicts, key=lambda d: d.get("line_no") or 0)
        ],
        "prev_hash": prev_hash or "",
    }


def _s(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def entry_hash(entry, line_dicts, prev_hash):
    blob = json.dumps(
        _entry_payload(entry, line_dicts, prev_hash),
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _line_dict_from_obj(line):
    return {f: getattr(line, f, None) for f in _LINE_FIELDS}


def recompute_entry_hash(entry, prev_hash):
    """Hash ulang sebuah entry tersimpan dari baris-barisnya di DB."""
    return entry_hash(
        entry, [_line_dict_from_obj(l) for l in entry.lines.all()], prev_hash,
    )


def verify_chain(company):
    """Return daftar masalah (kosong = rantai utuh) untuk satu company."""
    from hw.models.journal import JournalEntry

    problems = []
    prev_seq, prev_hash = 0, ""
    entries = (
        JournalEntry.objects.filter(company=company, seq__isnull=False)
        .order_by("seq").prefetch_related("lines")
    )
    for e in entries:
        if e.seq != prev_seq + 1:
            problems.append(f"{e.entry_number}: seq gap ({prev_seq} → {e.seq})")
        if e.prev_hash != prev_hash:
            problems.append(f"{e.entry_number}: prev_hash tidak cocok rantai")
        recomputed = recompute_entry_hash(e, prev_hash)
        if recomputed != e.entry_hash:
            problems.append(f"{e.entry_number}: entry_hash tidak cocok (tampered?)")
        prev_seq, prev_hash = e.seq, e.entry_hash
    return problems
