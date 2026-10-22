"""Parse a bank's CSV statement export into statement lines.

Indonesian internet-banking exports differ per bank and per channel, so the
parser guesses a column mapping from the header row and lets the user correct
it on the preview before anything is saved:

  Mandiri (Livin'/MCM): ... Date | Description | Reference | Debit | Credit | Balance
  BCA (KlikBCA):        Tanggal Transaksi | Keterangan | Cabang | Jumlah ("1,500,000.00 CR") | Saldo

Amounts come back as whole units of the account currency (rupiah, dollars),
the same unit as the cash book. Nothing here touches the database.
"""
import csv
import io
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

FIELDS = ('date', 'description', 'reference', 'debit', 'credit', 'amount', 'drcr', 'balance')

# Header keywords per field, checked in order (first hit wins per column).
_KEYWORDS = {
    'date': ('tanggal transaksi', 'tanggal', 'tgl', 'posting date', 'postdate', 'post date',
             'transaction date', 'date'),
    'description': ('keterangan', 'description', 'uraian', 'remark', 'berita', 'narrative'),
    'reference': ('reference', 'referensi', 'no. ref', 'ref no', 'ref'),
    'debit': ('debit', 'debet', 'mutasi debet', 'withdrawal', 'db'),
    'credit': ('credit', 'kredit', 'mutasi kredit', 'deposit', 'cr'),
    'amount': ('jumlah', 'amount', 'nominal', 'mutasi'),
    'drcr': ('db/cr', 'd/k', 'dr/cr', 'type', 'jenis'),
    'balance': ('saldo', 'balance'),
}

_MONTHS = {m: i for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), start=1)}
_MONTHS.update({'mei': 5, 'agu': 8, 'agt': 8, 'okt': 10, 'des': 12})


class ImportError_(ValueError):
    """The file can't be read as a statement at all."""


def read_rows(text):
    """CSV text → list of rows (lists of stripped cells), delimiter sniffed."""
    text = (text or '').lstrip('﻿')
    if not text.strip():
        raise ImportError_('File kosong.')
    sample = '\n'.join(text.splitlines()[:30])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ','
    # KlikBCA prefixes cells with ' so spreadsheets keep them as text.
    rows = [[c.strip().lstrip("'").strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return [r for r in rows if any(r)]


def _norm(cell):
    return re.sub(r'\s+', ' ', (cell or '').strip().lower().strip('"\''))


def find_header(rows):
    """Index of the header row: the first of the top 20 rows naming a date
    column and at least one amount column."""
    for i, row in enumerate(rows[:20]):
        cells = [_norm(c) for c in row]
        has_date = any(_header_hit('date', k, c) for c in cells for k in _KEYWORDS['date'])
        has_amount = any(
            _header_hit(f, k, c) for c in cells for f in ('debit', 'credit', 'amount') for k in _KEYWORDS[f]
        )
        if has_date and has_amount:
            return i
    raise ImportError_('Baris judul kolom (tanggal, debit/kredit atau jumlah) tidak ditemukan.')


def _header_hit(field, keyword, cell):
    if field == 'date':
        return cell == keyword or cell.startswith(keyword)
    if len(keyword) <= 3 or '/' in keyword:
        # Short codes (db, cr, ref, d/k) only as a whole word, never inside one.
        return keyword in re.split(r'[^a-z/.]+', cell)
    return keyword in cell


def guess_mapping(header):
    """{field: column index} from header names; unknown fields omitted."""
    cells = [_norm(c) for c in header]
    mapping = {}
    for field in ('date', 'drcr', 'debit', 'credit', 'amount', 'balance', 'description', 'reference'):
        for idx, cell in enumerate(cells):
            if idx in mapping.values() or not cell:
                continue
            if any(_header_hit(field, k, cell) for k in _KEYWORDS[field]):
                mapping[field] = idx
                break
    if 'debit' in mapping and 'credit' in mapping:
        mapping.pop('amount', None)
    return mapping


def parse_amount(raw):
    """'1.500.000,00' / '1,500,000.00' / '1500000' / '2,500.00 CR' →
    (Decimal magnitude, 'in'|'out'|None, sign from the text). None if empty."""
    s = (raw or '').strip().upper()
    if not s or s in ('-', '0', '0.00', '0,00'):
        return None
    hint = None
    m = re.search(r'\b(CR|DB|DR|K|D)\s*$', s)
    if m:
        hint = 'in' if m.group(1) in ('CR', 'K') else 'out'
        s = s[:m.start()].strip()
    negative = s.startswith('-') or (s.startswith('(') and s.endswith(')'))
    s = re.sub(r'[^\d.,]', '', s)
    if not s:
        return None
    if '.' in s and ',' in s:
        dec = '.' if s.rfind('.') > s.rfind(',') else ','
        s = s.replace(',' if dec == '.' else '.', '').replace(dec, '.')
    elif ',' in s or '.' in s:
        sep = ',' if ',' in s else '.'
        parts = s.split(sep)
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = parts[0] + '.' + parts[1]          # decimal separator
        else:
            s = s.replace(sep, '')                 # thousands separator
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    if value == 0:
        return None
    return value, hint, negative


def parse_date(raw, *, default_year=None):
    s = (raw or '').strip()
    if not s:
        return None
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y', '%d.%m.%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s.split(' ')[0], fmt).date()
        except ValueError:
            pass
    m = re.match(r'^(\d{1,2})[ \-/]([A-Za-z]{3})[a-z]*[ \-/](\d{2,4})', s)
    if m and m.group(2).lower()[:3] in _MONTHS:
        year = int(m.group(3))
        year = year + 2000 if year < 100 else year
        try:
            return date(year, _MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', s)     # BCA: dd/mm, year from the period
    if m and default_year:
        try:
            return date(default_year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _cell(row, mapping, field):
    idx = mapping.get(field)
    return row[idx] if idx is not None and idx < len(row) else ''


def _whole(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def parse(text, *, mapping=None, default_year=None):
    """→ {headers, mapping, lines, skipped, opening_balance, closing_balance,
    period_start, period_end}. `mapping` overrides the guess ({field: index})."""
    rows = read_rows(text)
    header_idx = find_header(rows)
    headers = rows[header_idx]
    if mapping is None:
        mapping = guess_mapping(headers)
    mapping = {k: int(v) for k, v in mapping.items() if k in FIELDS and v not in (None, '') and 0 <= int(v) < len(headers)}
    if 'date' not in mapping:
        raise ImportError_('Pilih kolom tanggal.')
    if not ({'debit', 'credit'} & mapping.keys() or 'amount' in mapping):
        raise ImportError_('Pilih kolom debit/kredit atau kolom jumlah.')

    lines, skipped, balances = [], [], []
    for n, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        raw_date = _cell(row, mapping, 'date')
        line_date = parse_date(raw_date, default_year=default_year)
        if line_date is None:
            skipped.append({'row': n, 'reason': 'no date', 'text': ' | '.join(c for c in row if c)[:120]})
            continue
        direction, value = None, None
        if {'debit', 'credit'} & mapping.keys():
            debit = parse_amount(_cell(row, mapping, 'debit'))
            credit = parse_amount(_cell(row, mapping, 'credit'))
            if debit and credit:
                skipped.append({'row': n, 'reason': 'both debit and credit', 'text': ' | '.join(row)[:120]})
                continue
            if debit:
                direction, value = 'out', debit[0]
            elif credit:
                direction, value = 'in', credit[0]
        else:
            parsed = parse_amount(_cell(row, mapping, 'amount'))
            if parsed:
                value, hint, negative = parsed
                flag = _norm(_cell(row, mapping, 'drcr'))
                if flag in ('cr', 'k', 'c', 'kredit', 'credit'):
                    hint = 'in'
                elif flag in ('db', 'dr', 'd', 'debet', 'debit'):
                    hint = 'out'
                direction = hint or ('out' if negative else 'in')
        if value is None:
            skipped.append({'row': n, 'reason': 'no amount', 'text': ' | '.join(c for c in row if c)[:120]})
            continue
        amount = _whole(value)
        if amount <= 0:
            continue
        lines.append({
            'line_date': line_date,
            'description': _cell(row, mapping, 'description')[:255],
            'reference': _cell(row, mapping, 'reference')[:200],
            'direction': direction,
            'amount': amount,
        })
        bal = parse_amount(_cell(row, mapping, 'balance'))
        if bal:
            balances.append((len(lines) - 1, _whole(bal[0]) * (-1 if bal[2] else 1)))

    opening = closing = None
    if balances and lines:
        # Exports list oldest→newest or newest→oldest; the balance after the
        # chronologically first line minus that line's movement is the opening.
        first_i, first_bal = balances[0]
        last_i, last_bal = balances[-1]
        if lines[0]['line_date'] > lines[-1]['line_date']:
            first_i, first_bal, last_i, last_bal = last_i, last_bal, first_i, first_bal
        signed = lines[first_i]['amount'] * (1 if lines[first_i]['direction'] == 'in' else -1)
        opening, closing = first_bal - signed, last_bal
    dates = [l['line_date'] for l in lines]
    return {
        'headers': headers,
        'mapping': mapping,
        'lines': sorted(lines, key=lambda l: l['line_date']),
        'skipped': skipped,
        'opening_balance': opening,
        'closing_balance': closing,
        'period_start': min(dates) if dates else None,
        'period_end': max(dates) if dates else None,
    }
