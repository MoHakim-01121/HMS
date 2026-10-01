"""Chart of Accounts — kode akun kanonik + seed.

Kode akun memakai skema bernomor standar (aset 1xxx, liabilitas 2xxx,
ekuitas 3xxx, pendapatan 4xxx, beban 5xxx). Ini satu-satunya tempat daftar
akun didefinisikan; `seed_chart_of_accounts()` menuliskannya ke tabel
`LedgerAccount` (idempotent) dan dipanggil oleh command + data migration.
"""
from hw.models.journal import AccountType

# ── Kode akun (dipakai posting layer & queries) ──────────────────
CASH_SBY = "1000-KAS-SBY"
CASH_JKT = "1000-KAS-JKT"
CASH_PUSAT = "1000-KAS-PUSAT"
AR = "1100-AR"
TRANSIT = "1200-TRANSIT"
FX_CLEARING = "1900-FX-CLR"

AP = "2000-AP"
CUST_CREDIT = "2100-CUST-CREDIT"

OPENING_EQUITY = "3000-OPENING"

INC_HOTEL = "4100-INC-HOTEL"
INC_SERVICE = "4200-INC-SVC"
INC_PENALTY = "4300-INC-PENALTY"
INC_FX_GAIN = "4900-INC-FXGAIN"

EXP_BANKFEE = "5100-EXP-BANKFEE"
EXP_FX_LOSS = "5200-EXP-FXLOSS"
EXP_PENALTY = "5300-EXP-PENALTY"

# Beban operasional cabang (FASE D). Kategori Expense memetakan ke sini.
EXP_UTILITIES     = "5410-EXP-UTIL"
EXP_TELECOM       = "5420-EXP-TELECOM"
EXP_TRANSPORT     = "5430-EXP-TRANSPORT"
EXP_SUPPLIES      = "5440-EXP-SUPPLIES"
EXP_RENT          = "5450-EXP-RENT"
EXP_MEALS         = "5460-EXP-MEALS"
EXP_MAINTENANCE   = "5470-EXP-MAINT"
EXP_MARKETING     = "5480-EXP-MKT"
EXP_MISC          = "5490-EXP-MISC"
# Biaya vendor untuk Services yang dijual cabang (harga beli per pax).
EXP_SVC_VENDOR    = "5500-EXP-SVC-VENDOR"

# Kas fisik yang wajib diremitkan dari cabang ke pusat.
CASH_BRANCH_CODES = (CASH_SBY, CASH_JKT)
# Kas cabang (1000-KAS-<CABANG>) dicatat dalam SAR. Rekening rupiah/dolar
# punya akun anaknya sendiri, 1000-KAS-<CABANG>-<MATA UANG> — satu akun buku
# besar satu mata uang (T4). Saldo kas cabang = akun induk + anak-anaknya.
CASH_ROOTS = (CASH_SBY, CASH_JKT, CASH_PUSAT)


def cash_ledger_for(branch_code, currency):
    """Kode akun buku besar untuk rekening cabang `branch_code` dalam
    `currency`; akun anak mata uang asing dibuat bila belum ada."""
    from ..models.journal import LedgerAccount
    base = f"1000-KAS-{branch_code.upper()}"
    if currency == "SAR":
        return base
    parent = LedgerAccount.objects.get(code=base)
    code = f"{base}-{currency}"
    LedgerAccount.objects.get_or_create(
        code=code,
        defaults={"name": f"{parent.name} {currency}", "type": parent.type, "normal_balance": parent.normal_balance,
                  "parent": parent, "is_postable": True, "is_active": True},
    )
    return code

# HQ owns hotel revenue: a branch books the sale and collects the money as an
# agent, then must remit the full SAR value (IFRS 15 principal vs agent). Its
# own income is the exchange spread, not the booking.
HQ_BRANCH = "pusat"

ACCOUNTS = [
    {"code": CASH_SBY, "name": "Kas Surabaya", "type": AccountType.ASSET},
    {"code": CASH_JKT, "name": "Kas Jakarta", "type": AccountType.ASSET},
    {"code": CASH_PUSAT, "name": "Kas Pusat (HQ)", "type": AccountType.ASSET},
    {"code": AR, "name": "Piutang Client", "type": AccountType.ASSET},
    {"code": TRANSIT, "name": "Kas Dalam Perjalanan (Remittance)", "type": AccountType.ASSET},
    {"code": FX_CLEARING, "name": "Kliring Selisih Kurs", "type": AccountType.ASSET},
    {"code": AP, "name": "Utang Usaha (Accounts Payable)", "type": AccountType.LIABILITY},
    {"code": CUST_CREDIT, "name": "Titipan / Saldo Dana Client", "type": AccountType.LIABILITY},
    {"code": OPENING_EQUITY, "name": "Ekuitas Saldo Awal", "type": AccountType.EQUITY},
    {"code": INC_HOTEL, "name": "Pendapatan Hotel", "type": AccountType.INCOME},
    {"code": INC_SERVICE, "name": "Pendapatan Visa/Services", "type": AccountType.INCOME},
    {"code": INC_PENALTY, "name": "Pendapatan Penalty", "type": AccountType.INCOME},
    {"code": INC_FX_GAIN, "name": "Laba Selisih Kurs", "type": AccountType.INCOME},
    {"code": EXP_BANKFEE, "name": "Beban Biaya Transfer/Bank", "type": AccountType.EXPENSE},
    {"code": EXP_FX_LOSS, "name": "Rugi Selisih Kurs", "type": AccountType.EXPENSE},
    {"code": EXP_PENALTY, "name": "Beban Penalty", "type": AccountType.EXPENSE},
    {"code": EXP_UTILITIES, "name": "Beban Listrik & Air", "type": AccountType.EXPENSE},
    {"code": EXP_TELECOM, "name": "Beban Internet & Telepon", "type": AccountType.EXPENSE},
    {"code": EXP_TRANSPORT, "name": "Beban Transportasi", "type": AccountType.EXPENSE},
    {"code": EXP_SUPPLIES, "name": "Beban ATK & Perlengkapan", "type": AccountType.EXPENSE},
    {"code": EXP_RENT, "name": "Beban Sewa Kantor", "type": AccountType.EXPENSE},
    {"code": EXP_MEALS, "name": "Beban Konsumsi & Rapat", "type": AccountType.EXPENSE},
    {"code": EXP_MAINTENANCE, "name": "Beban Pemeliharaan", "type": AccountType.EXPENSE},
    {"code": EXP_MARKETING, "name": "Beban Marketing", "type": AccountType.EXPENSE},
    {"code": EXP_MISC, "name": "Beban Lain-lain", "type": AccountType.EXPENSE},
    {"code": EXP_SVC_VENDOR, "name": "Biaya Vendor Services", "type": AccountType.EXPENSE},
]

# Kategori Expense default (code → (nama, ledger account code)). Di-seed ke
# ExpenseCategory oleh migrasi; bisa ditambah lewat admin.
DEFAULT_EXPENSE_CATEGORIES = [
    ("UTIL",      "Listrik & Air",        EXP_UTILITIES),
    ("TELECOM",   "Internet & Telepon",   EXP_TELECOM),
    ("TRANSPORT", "Transportasi",         EXP_TRANSPORT),
    ("SUPPLIES",  "ATK & Perlengkapan",   EXP_SUPPLIES),
    ("RENT",      "Sewa Kantor",          EXP_RENT),
    ("MEALS",     "Konsumsi & Rapat",     EXP_MEALS),
    ("MAINT",     "Pemeliharaan",         EXP_MAINTENANCE),
    ("MARKETING", "Marketing",            EXP_MARKETING),
    ("BANKFEE",   "Biaya Bank",           EXP_BANKFEE),
    ("MISC",      "Lain-lain",            EXP_MISC),
    ("SVC-VENDOR", "Biaya vendor Services", EXP_SVC_VENDOR),
]

# Peta kode akun v1 (enum Account lama) → kode v2. Dipakai adapter
# create_journal_entry() selama posting v1 (penalty_views, confirm_payment)
# belum dirombak ke posting layer baru (Fase 5).
V1_ACCOUNT_MAP = {
    "cash_sby": CASH_SBY,
    "cash_jkt": CASH_JKT,
    "cash_pusat": CASH_PUSAT,
    "fx": FX_CLEARING,
    "receivable": AR,
    "income_hotel": INC_HOTEL,
    "income_service": INC_SERVICE,
    "income_penalty": INC_PENALTY,
    "expense_penalty": EXP_PENALTY,
    "equity": OPENING_EQUITY,
}


def resolve_account_code(code):
    """Terima kode v2 apa adanya, atau terjemahkan kode enum v1."""
    if code in V1_ACCOUNT_MAP:
        return V1_ACCOUNT_MAP[code]
    return code

_DEBIT_NORMAL_TYPES = {AccountType.ASSET, AccountType.EXPENSE}

NORMAL_DEBIT = "debit"
NORMAL_CREDIT = "credit"


def normal_balance_for(account_type):
    """asset/expense → 'debit'; liability/income/equity → 'credit'."""
    return NORMAL_DEBIT if account_type in _DEBIT_NORMAL_TYPES else NORMAL_CREDIT


def seed_chart_of_accounts():
    """Buat/perbarui semua akun di ACCOUNTS. Idempotent. Return jumlah baris."""
    from hw.models.journal import LedgerAccount

    for spec in ACCOUNTS:
        LedgerAccount.objects.update_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "type": spec["type"],
                "normal_balance": normal_balance_for(spec["type"]),
                "is_postable": spec.get("is_postable", True),
                "is_active": True,
            },
        )
    return len(ACCOUNTS)
