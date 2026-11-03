"""View-layer package.

This module is a router surface only: `hw/urls.py` does `from . import views`
and references `views.<name>`, so every view is re-exported here. Feature logic
lives in the sibling `*_views.py` modules — nothing is defined in this file.
"""
from .ai_views import ai_chat, ai_chat_reset, ai_draft_message
from .attachment_views import attachment_delete, attachment_upload
from .calendar_views import calendar_checkin_pdf, calendar_view
from .cl_views import (
    cl_delete,
    cl_detail,
    cl_duplicate,
    cl_edit,
    cl_export_csv,
    cl_list,
    cl_list_pdf,
    cl_list_pdf_v2,
    cl_new,
    cl_pdf,
    invoice_from_cls,
)
from .claim_views import (
    claim_cancel,
    claim_close,
    claim_detail,
    claim_export_csv,
    claim_list,
    claim_new,
    claim_pay,
    claim_pdf,
    claim_reject,
    claim_submit,
    claim_unpay,
)
from .client_views import (
    client_delete,
    client_deposit_transfer,
    client_deposit_transfer_confirm,
    client_deposit_transfer_reject,
    client_detail,
    client_edit,
    client_export_csv,
    client_list,
    client_map,
    client_map_data,
    client_new,
    client_refund,
    client_refund_confirm,
    client_refund_reject,
    client_statement_pdf,
    client_toggle_active,
)
from .credit_note_views import (
    credit_note_export_csv,
    credit_note_list,
    credit_note_new,
    credit_note_pdf,
    credit_note_void,
    invoice_excess_to_deposit,
    invoice_void,
)
from .dev_views import health_check
from .exchange_views import exchange_export_csv, exchange_list, exchange_new, exchange_void
from .expense_views import (
    expense_approve,
    expense_categories,
    expense_category_edit,
    expense_category_new,
    expense_detail,
    expense_export_csv,
    expense_list,
    expense_pay,
    expense_record,
    expense_reject,
    expense_void,
)
from .finance_views import (
    ar_aging_csv,
    ar_aging_report,
    bank_account_edit,
    bank_account_export_csv,
    bank_account_list,
    bank_account_new,
    bank_account_transactions,
    branch_report_csv,
    branch_report_view,
    client_finance_statement,
    fund_flow_csv,
    fund_flow_report,
    journal_detail,
    journal_list,
    statements_list,
    trial_balance,
)
from .home_views import home
from .hotel_views import (
    hotel_delete,
    hotel_detail,
    hotel_edit,
    hotel_export_csv,
    hotel_list,
    hotel_map,
    hotel_map_data,
    hotel_meal_plans,
    hotel_new,
    hotel_toggle_active,
    room_type_bulk,
    room_type_delete,
    room_type_edit,
    room_type_new,
)
from .invoice_views import (
    invoice_delete,
    invoice_detail,
    invoice_edit,
    invoice_export_csv,
    invoice_list,
    invoice_list_pdf,
    invoice_new,
    invoice_pdf,
)
from .landing_views import (
    landing,
    landing_manage,
    pricelist_delete,
    pricelist_edit,
    pricelist_new,
    team_delete,
    team_edit,
    team_new,
)
from .payment_views import (
    payment_apply,
    payment_confirm,
    payment_detail,
    payment_export_csv,
    payment_list,
    payment_reallocate,
    payment_record,
    payment_reject,
    payment_reverse,
    payment_to_deposit,
    payment_void,
)
from .penalty_views import (
    penalty_delete,
    penalty_detail,
    penalty_edit,
    penalty_list,
    penalty_new,
    penalty_pdf,
)
from .period_views import (
    period_close,
    period_create,
    period_detail,
    period_list,
    period_lock,
    season_delete,
    season_save,
)
from .receipt_views import (
    receipt_pdf,
    receipt_void,
)
from .reconciliation_views import (
    reconciliation_detail,
    reconciliation_import,
    reconciliation_list,
    reconciliation_match,
    reconciliation_match_group,
    reconciliation_match_suggested,
    reconciliation_new,
    reconciliation_unmatch,
)
from .remittance_views import (
    remittance_delete,
    remittance_detail,
    remittance_draft_pdf,
    remittance_edit,
    remittance_export_csv,
    remittance_ledger_pdf,
    remittance_list,
    remittance_new,
    remittance_pdf,
    remittance_period_pdf,
    remittance_recap,
    remittance_tracking,
    remittance_upload_proof,
)
from .role_views import role_delete, role_edit, role_list, role_new
from .search_views import global_search
from .settlement_views import (
    remittance_close_diff,
    remittance_receipt_allocation,
    remittance_receipt_delete,
    remittance_record_receipt,
    remittance_reopen_diff,
)
from .user_views import (
    account_profile,
    account_profile_update,
    avatar_delete,
    avatar_upload,
    set_language,
    user_credential_card,
    user_delete,
    user_edit,
    user_list,
    user_new,
)
