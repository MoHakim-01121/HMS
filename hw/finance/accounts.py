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

CUST_CREDIT = "2100-CUST-CREDIT"

OPENING_EQUITY = "3000-OPENING"

INC_HOTEL = "4100-INC-HOTEL"
INC_SERVICE = "4200-INC-SVC"
INC_PENALTY = "4300-INC-PENALTY"
INC_FX_GAIN = "4900-INC-FXGAIN"

EXP_BANKFEE = "5100-EXP-BANKFEE"
EXP_FX_LOSS = "5200-EXP-FXLOSS"
EXP_PENALTY = "5300-EXP-PENALTY"

# Kas fisik yang wajib diremitkan dari cabang ke pusat.
CASH_BRANCH_CODES = (CASH_SBY, CASH_JKT)

ACCOUNTS = [
    {"code": CASH_SBY, "name": "Kas Surabaya", "type": AccountType.ASSET},
    {"code": CASH_JKT, "name": "Kas Jakarta", "type": AccountType.ASSET},
    {"code": CASH_PUSAT, "name": "Kas Pusat (HQ)", "type": AccountType.ASSET},
    {"code": AR, "name": "Piutang Client", "type": AccountType.ASSET},
    {"code": TRANSIT, "name": "Kas Dalam Perjalanan (Remittance)", "type": AccountType.ASSET},
    {"code": FX_CLEARING, "name": "Kliring Selisih Kurs", "type": AccountType.ASSET},
    {"code": CUST_CREDIT, "name": "Titipan / Saldo Dana Client", "type": AccountType.LIABILITY},
    {"code": OPENING_EQUITY, "name": "Ekuitas Saldo Awal", "type": AccountType.EQUITY},
    {"code": INC_HOTEL, "name": "Pendapatan Hotel", "type": AccountType.INCOME},
    {"code": INC_SERVICE, "name": "Pendapatan Visa/Services", "type": AccountType.INCOME},
    {"code": INC_PENALTY, "name": "Pendapatan Penalty", "type": AccountType.INCOME},
    {"code": INC_FX_GAIN, "name": "Laba Selisih Kurs", "type": AccountType.INCOME},
    {"code": EXP_BANKFEE, "name": "Beban Biaya Transfer/Bank", "type": AccountType.EXPENSE},
    {"code": EXP_FX_LOSS, "name": "Rugi Selisih Kurs", "type": AccountType.EXPENSE},
    {"code": EXP_PENALTY, "name": "Beban Penalty", "type": AccountType.EXPENSE},
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
