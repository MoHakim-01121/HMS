"""View-layer package.

This module is a router surface only: `hw/urls.py` does `from . import views`
and references `views.<name>`, so every view is re-exported here. Feature logic
lives in the sibling `*_views.py` modules — nothing is defined in this file.
"""
from .home_views import home
from .landing_views import (
    landing, public_hotels,
    landing_manage, team_new, team_edit, team_delete,
    pricelist_new, pricelist_edit, pricelist_delete,
)
from .ai_views import ai_draft_message, ai_chat, ai_chat_reset
from .cl_views import (
    cl_delete, cl_detail, cl_duplicate, cl_edit, cl_export_csv, cl_list,
    cl_list_pdf, cl_list_pdf_v2, cl_new, cl_pdf, invoice_from_cls,
)
from .invoice_views import (
    invoice_delete, invoice_detail, invoice_edit,
    invoice_export_csv, invoice_list, invoice_list_pdf, invoice_new, invoice_pdf,
)
from .calendar_views import calendar_view
from .search_views import global_search
from .attachment_views import attachment_delete, attachment_upload
from .user_views import account_profile, account_profile_update, avatar_delete, avatar_upload, user_credential_card, user_delete, user_edit, user_list, user_new, set_language
from .role_views import role_delete, role_edit, role_list, role_new
from .client_views import (
    client_list, client_new, client_edit, client_delete,
    client_detail, client_map, client_map_data,
    client_refund, client_deposit_transfer,
    client_refund_confirm, client_refund_reject, client_deposit_transfer_confirm, client_deposit_transfer_reject, client_statement_pdf, client_export_csv,
)
from .hotel_views import (
    hotel_list, hotel_new, hotel_edit, hotel_delete,
    hotel_detail, hotel_map, hotel_map_data, hotel_export_csv,
    room_type_new, room_type_edit, room_type_bulk, room_type_delete, hotel_meal_plans,
)
from .remittance_views import (
    remittance_list, remittance_new, remittance_detail, remittance_edit,
    remittance_pdf, remittance_delete, remittance_upload_proof, remittance_export_csv,
    remittance_recap, remittance_period_pdf,
    remittance_ledger_pdf, remittance_tracking,
)
from .exchange_views import exchange_export_csv, exchange_list, exchange_new, exchange_void
from .claim_views import (
    claim_cancel, claim_detail, claim_export_csv, claim_list, claim_new, claim_pay, claim_pdf,
    claim_reject, claim_submit, claim_unpay,
)
from .credit_note_views import (
    invoice_void, invoice_excess_to_deposit, credit_note_new, credit_note_list, credit_note_void, credit_note_pdf, credit_note_export_csv,
)
from .settlement_views import (
    remittance_record_receipt, remittance_receipt_allocation, remittance_receipt_delete,
    remittance_close_diff, remittance_reopen_diff,
)
from .reconciliation_views import (
    reconciliation_list, reconciliation_new, reconciliation_detail,
    reconciliation_match, reconciliation_unmatch, reconciliation_import, reconciliation_match_suggested,
)
from .penalty_views import (
    penalty_new, penalty_detail, penalty_edit, penalty_delete, penalty_pdf,
    penalty_list,
)
from .finance_views import (
    journal_list, journal_detail, trial_balance, statements_list,
    client_finance_statement, bank_account_list, bank_account_transactions,
    bank_account_new, bank_account_edit,
    fund_flow_report, fund_flow_csv, ar_aging_report, ar_aging_csv, bank_account_export_csv,
    branch_report_view, branch_report_csv,
)
from .period_views import (
    period_list, period_detail, period_close, period_lock, period_create,
    season_save, season_delete,
)
from .receipt_views import (
    receipt_void, receipt_pdf,
)
from .payment_views import (
    payment_list, payment_detail, payment_record,
    payment_confirm, payment_reject, payment_reverse, payment_reallocate,
    payment_apply, payment_void, payment_to_deposit, payment_export_csv,
)
from .expense_views import (
    expense_list, expense_detail, expense_record, expense_pay, expense_void,
    expense_export_csv, expense_approve, expense_reject,
    expense_categories, expense_category_new, expense_category_edit,
)
from .dev_views import style_guide, health_check
