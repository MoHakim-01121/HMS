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
from .ai_views import ai_draft_message, ai_chat
from .cl_views import (
    cl_delete, cl_detail, cl_duplicate, cl_edit, cl_export_csv, cl_list,
    cl_list_pdf, cl_list_pdf_v2, cl_new, cl_pdf, invoice_from_cls,
)
from .invoice_views import (
    invoice_delete, invoice_detail, invoice_duplicate, invoice_edit,
    invoice_export_csv, invoice_list, invoice_list_pdf, invoice_new, invoice_pdf,
)
from .services_views import (
    services_delete, services_detail, services_duplicate, services_edit,
    services_export_csv, services_list, services_list_pdf, services_new, services_pdf,
)
from .calendar_views import (
    calendar_view, cl_estimasi_save,
    calendar_checkin_pdf,
)
from .reminder_views import (
    calendar_send_recap,
    calendar_send_reminder_group,
    wa_target_add, wa_target_toggle, wa_target_delete,
    message_template_save, calendar_recap_settings,
)
from .search_views import global_search
from .attachment_views import attachment_delete, attachment_upload
from .user_views import account_profile, account_profile_update, avatar_delete, avatar_upload, user_credential_card, user_delete, user_edit, user_list, user_new, set_language
from .role_views import role_delete, role_edit, role_list, role_new
from .client_views import (
    client_list, client_new, client_edit, client_delete,
    client_detail, client_map, client_map_data,
    client_transfer, client_refund, client_statement_pdf,
)
from .hotel_views import (
    hotel_list, hotel_new, hotel_edit, hotel_delete,
    hotel_detail, hotel_map, hotel_map_data,
)
from .remittance_views import (
    remittance_list, remittance_new, remittance_detail, remittance_edit,
    remittance_pdf, remittance_delete, remittance_upload_proof, remittance_export_csv,
    remittance_mark_received, remittance_recap, remittance_period_pdf,
    remittance_ledger_pdf, remittance_tracking,
)
from .settlement_views import (
    settlement_list, obligation_new, settlement_new, settlement_allocate,
    remittance_close_diff,
)
from .reconciliation_views import (
    reconciliation_list, reconciliation_new, reconciliation_detail,
    reconciliation_match, reconciliation_unmatch,
)
from .penalty_views import (
    penalty_new, penalty_detail, penalty_edit, penalty_delete, penalty_pdf,
    penalty_list,
)
from .finance_views import (
    journal_list, journal_detail, trial_balance, statements_list,
    client_finance_statement, bank_account_list, bank_account_transactions,
)
from .period_views import (
    period_list, period_detail, period_close, period_lock, period_create,
)
from .receipt_views import (
    receipt_void, receipt_pdf,
)
from .payment_views import (
    payment_list, payment_detail, payment_record_new, payment_record,
    payment_confirm, payment_reject, payment_reverse, payment_reallocate,
    payment_apply, payment_void, payment_export_csv,
)
from .expense_views import (
    expense_list, expense_detail, expense_record, expense_pay, expense_void,
    expense_export_csv,
)
from .dev_views import style_guide, health_check
from .visit_views import (
    visit_cancel, visit_complete, visit_detail, visit_edit, visit_list,
    visit_new, visit_pdf, visit_photo_delete, visit_photo_upload, visit_recap,
)
