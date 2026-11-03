from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.generic import RedirectView

from . import views
from .active_branch import switch_branch

urlpatterns = [
    path('', views.landing, name='landing'),
    path('dashboard/', views.home, name='home'),
    path('properties/', views.public_hotels, name='public_hotels'),

    # Confirmation Letter
    path('cl/', views.cl_list, name='cl_list'),
    path('cl/new/', views.cl_new, name='cl_new'),
    path('cl/export/csv/', views.cl_export_csv, name='cl_export_csv'),
    path('cl/export/pdf/', views.cl_list_pdf, name='cl_list_pdf'),
    path('cl/export/pdf-v2/', views.cl_list_pdf_v2, name='cl_list_pdf_v2'),
    path('cl/<int:pk>/', views.cl_detail, name='cl_detail'),
    path('cl/<int:pk>/edit/', views.cl_edit, name='cl_edit'),
    path('cl/<int:pk>/delete/', views.cl_delete, name='cl_delete'),
    path('cl/<int:pk>/pdf/', views.cl_pdf, name='cl_pdf'),
    path('cl/<int:pk>/duplicate/', views.cl_duplicate, name='cl_duplicate'),
    path('cl/invoice-from-cls/', views.invoice_from_cls, name='invoice_from_cls'),

    # Invoice Hotel
    path('invoice/', views.invoice_list, name='invoice_list'),
    path('invoice/new/', views.invoice_new, name='invoice_new'),
    path('invoice/export/csv/', views.invoice_export_csv, name='invoice_export_csv'),
    path('invoice/export/pdf/', views.invoice_list_pdf, name='invoice_list_pdf'),
    path('invoice/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoice/<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoice/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),


    # Calendar
    path('calendar/', views.calendar_view, name='calendar'),

    # Search
    path('search/', views.global_search, name='global_search'),

    # Attachments
    path('attachments/upload/', views.attachment_upload, name='attachment_upload'),
    path('attachments/<int:pk>/delete/', views.attachment_delete, name='attachment_delete'),

    # AI
    path('ai/chat/', views.ai_chat, name='ai_chat'),
    path('ai/chat/reset/', views.ai_chat_reset, name='ai_chat_reset'),
    path('ai/draft/', views.ai_draft_message, name='ai_draft_message'),

    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/export/csv/', views.client_export_csv, name='client_export_csv'),
    path('clients/new/', views.client_new, name='client_new'),
    path('clients/map/', views.client_map, name='client_map'),
    path('clients/map/data/', views.client_map_data, name='client_map_data'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),
    path('clients/<int:pk>/active/', views.client_toggle_active, name='client_toggle_active'),
    # Client money actions moved to Finance (Client is information only);
    # the old URLs redirect so existing bookmarks and links keep working.
    path('clients/<int:pk>/refund/', RedirectView.as_view(pattern_name='client_refund', query_string=True)),
    path('clients/<int:pk>/statement/pdf/', RedirectView.as_view(pattern_name='client_statement_pdf', query_string=True)),

    # Hotels
    path('hotels/', views.hotel_list, name='hotel_list'),
    path('hotels/new/', views.hotel_new, name='hotel_new'),
    path('hotels/map/', views.hotel_map, name='hotel_map'),
    path('hotels/export/csv/', views.hotel_export_csv, name='hotel_export_csv'),
    path('hotels/map/data/', views.hotel_map_data, name='hotel_map_data'),
    path('hotels/<int:pk>/', views.hotel_detail, name='hotel_detail'),
    path('hotels/<int:pk>/edit/', views.hotel_edit, name='hotel_edit'),
    path('hotels/<int:pk>/delete/', views.hotel_delete, name='hotel_delete'),
    path('hotels/<int:pk>/active/', views.hotel_toggle_active, name='hotel_toggle_active'),
    path('hotels/<int:hotel_pk>/room-types/new/', views.room_type_new, name='room_type_new'),
    path('hotels/<int:hotel_pk>/room-types/bulk/', views.room_type_bulk, name='room_type_bulk'),
    path('hotels/<int:hotel_pk>/room-types/<int:pk>/edit/', views.room_type_edit, name='room_type_edit'),
    path('hotels/<int:hotel_pk>/room-types/<int:pk>/delete/', views.room_type_delete, name='room_type_delete'),
    path('hotels/<int:hotel_pk>/meal-plans/', views.hotel_meal_plans, name='hotel_meal_plans'),

    # Remittance (Konoz only)
    path('remittance/', views.remittance_list, name='remittance_list'),
    path('remittance/new/', views.remittance_new, name='remittance_new'),
    path('remittance/recap/', views.remittance_recap, name='remittance_recap'),
    path('remittance/tracking/', views.remittance_tracking, name='remittance_tracking'),
    path('remittance/export/csv/', views.remittance_export_csv, name='remittance_export_csv'),
    path('remittance/export/pdf/', views.remittance_period_pdf, name='remittance_period_pdf'),
    path('remittance/export/ledger/', views.remittance_ledger_pdf, name='remittance_ledger_pdf'),
    path('remittance/<int:pk>/', views.remittance_detail, name='remittance_detail'),
    path('remittance/<int:pk>/edit/', views.remittance_edit, name='remittance_edit'),
    path('remittance/<int:pk>/pdf/', views.remittance_pdf, name='remittance_pdf'),
    path('remittance/<int:pk>/upload-proof/', views.remittance_upload_proof, name='remittance_upload_proof'),
    path('remittance/<int:pk>/delete/', views.remittance_delete, name='remittance_delete'),
    path('remittance/<int:pk>/receipt/', views.remittance_record_receipt, name='remittance_record_receipt'),
    path('remittance/<int:pk>/receipt/<int:sid>/allocation/', views.remittance_receipt_allocation, name='remittance_receipt_allocation'),
    path('remittance/<int:pk>/receipt/<int:sid>/delete/', views.remittance_receipt_delete, name='remittance_receipt_delete'),
    path('remittance/<int:pk>/close-diff/', views.remittance_close_diff, name='remittance_close_diff'),
    path('remittance/<int:pk>/reopen-diff/', views.remittance_reopen_diff, name='remittance_reopen_diff'),

    # User management (the 'users' module in hw/permissions.py)
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_new, name='user_new'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/credential-card/', views.user_credential_card, name='user_credential_card'),

    # Role & permission matrix editor (same 'users' module gate)
    path('roles/', views.role_list, name='role_list'),
    path('roles/new/', views.role_new, name='role_new'),
    path('roles/<slug:slug>/edit/', views.role_edit, name='role_edit'),
    path('roles/<slug:slug>/delete/', views.role_delete, name='role_delete'),

    # Account / Profile
    path('account/profile/', views.account_profile, name='account_profile'),
    path('account/profile/update/', views.account_profile_update, name='account_profile_update'),
    path('account/avatar/upload/', views.avatar_upload, name='avatar_upload'),
    path('account/avatar/delete/', views.avatar_delete, name='avatar_delete'),
    path('account/language/', views.set_language, name='set_language'),
    path('account/branch/', switch_branch, name='switch_branch'),


    # Cancellation Penalty (accessible through CL)
    path('cl/<int:cl_pk>/penalty/new/', views.penalty_new, name='penalty_new'),
    path('penalty/<int:pk>/', views.penalty_detail, name='penalty_detail'),
    path('penalty/<int:pk>/edit/', views.penalty_edit, name='penalty_edit'),
    path('penalty/<int:pk>/delete/', views.penalty_delete, name='penalty_delete'),
    path('penalty/<int:pk>/pdf/', views.penalty_pdf, name='penalty_pdf'),

    # Landing page management (team members + pricelist)
    path('manage-landing/', views.landing_manage, name='landing_manage'),
    path('manage-landing/team/new/', views.team_new, name='team_new'),
    path('manage-landing/team/<int:pk>/edit/', views.team_edit, name='team_edit'),
    path('manage-landing/team/<int:pk>/delete/', views.team_delete, name='team_delete'),
    path('manage-landing/pricelist/new/', views.pricelist_new, name='pricelist_new'),
    path('manage-landing/pricelist/<int:pk>/edit/', views.pricelist_edit, name='pricelist_edit'),
    path('manage-landing/pricelist/<int:pk>/delete/', views.pricelist_delete, name='pricelist_delete'),

    # Health check
    path('health/', views.health_check, name='health_check'),

    # ── Finance Redesign ──
    # The Finance overview page was removed (2026-10-20); old links land on Home.
    path('finance/', login_required(RedirectView.as_view(url='/dashboard/')), name='finance_hub'),
    path('finance/payments/', views.payment_list, name='payment_list'),
    path('finance/payments/export/csv/', views.payment_export_csv, name='payment_export_csv'),
    path('finance/payments/record/', views.payment_record, name='payment_record'),
    path('finance/payments/<int:pk>/', views.payment_detail, name='payment_detail'),
    path('finance/payments/<int:pk>/confirm/', views.payment_confirm, name='payment_confirm'),
    path('finance/payments/<int:pk>/reallocate/', views.payment_reallocate, name='payment_reallocate'),
    path('finance/payments/<int:pk>/apply/', views.payment_apply, name='payment_apply'),
    path('finance/payments/<int:pk>/void/', views.payment_void, name='payment_void'),
    path('finance/payments/<int:pk>/to-deposit/', views.payment_to_deposit, name='payment_to_deposit'),
    path('finance/payments/<int:pk>/reject/', views.payment_reject, name='payment_reject'),
    path('finance/payments/<int:pk>/reverse/', views.payment_reverse, name='payment_reverse'),
    path('finance/fund-flow/', views.fund_flow_report, name='fund_flow_report'),
    path('finance/branch-report/', views.branch_report_view, name='branch_report'),
    path('finance/branch-report/export/csv/', views.branch_report_csv, name='branch_report_csv'),
    path('finance/fund-flow/export/csv/', views.fund_flow_csv, name='fund_flow_csv'),
    path('finance/ar-aging/', views.ar_aging_report, name='ar_aging_report'),
    path('finance/credit-notes/', views.credit_note_list, name='credit_note_list'),
    path('finance/credit-notes/export/csv/', views.credit_note_export_csv, name='credit_note_export_csv'),
    path('finance/credit-notes/<int:pk>/void/', views.credit_note_void, name='credit_note_void'),
    path('finance/credit-notes/<int:pk>/pdf/', views.credit_note_pdf, name='credit_note_pdf'),
    path('finance/invoices/<int:pk>/void/', views.invoice_void, name='invoice_void'),
    path('finance/invoices/<int:pk>/excess-to-deposit/', views.invoice_excess_to_deposit, name='invoice_excess_to_deposit'),
    path('finance/invoices/<int:pk>/credit-notes/new/', views.credit_note_new, name='credit_note_new'),
    path('finance/ar-aging/export/csv/', views.ar_aging_csv, name='ar_aging_csv'),
    path('finance/exchanges/', views.exchange_list, name='exchange_list'),
    path('finance/exchanges/export/csv/', views.exchange_export_csv, name='exchange_export_csv'),
    path('finance/exchanges/new/', views.exchange_new, name='exchange_new'),
    path('finance/exchanges/<int:pk>/void/', views.exchange_void, name='exchange_void'),
    path('finance/expenses/', views.expense_list, name='expense_list'),
    path('finance/expenses/export/csv/', views.expense_export_csv, name='expense_export_csv'),
    path('finance/expenses/record/', views.expense_record, name='expense_record'),
    path('finance/expenses/<int:pk>/', views.expense_detail, name='expense_detail'),
    path('finance/expenses/<int:pk>/approve/', views.expense_approve, name='expense_approve'),
    path('finance/expenses/<int:pk>/reject/', views.expense_reject, name='expense_reject'),
    path('finance/expenses/<int:pk>/pay/', views.expense_pay, name='expense_pay'),
    path('finance/expenses/<int:pk>/void/', views.expense_void, name='expense_void'),
    path('finance/claims/', views.claim_list, name='claim_list'),
    path('finance/claims/new/', views.claim_new, name='claim_new'),
    path('finance/claims/<int:pk>/', views.claim_detail, name='claim_detail'),
    path('finance/claims/<int:pk>/submit/', views.claim_submit, name='claim_submit'),
    path('finance/claims/<int:pk>/cancel/', views.claim_cancel, name='claim_cancel'),
    path('finance/claims/<int:pk>/reject/', views.claim_reject, name='claim_reject'),
    path('finance/claims/<int:pk>/pay/', views.claim_pay, name='claim_pay'),
    path('finance/claims/<int:pk>/close/', views.claim_close, name='claim_close'),
    path('finance/claims/<int:pk>/unpay/', views.claim_unpay, name='claim_unpay'),
    path('finance/claims/<int:pk>/export/csv/', views.claim_export_csv, name='claim_export_csv'),
    path('finance/claims/<int:pk>/pdf/', views.claim_pdf, name='claim_pdf'),
    path('finance/expenses/categories/', views.expense_categories, name='expense_categories'),
    path('finance/expenses/categories/new/', views.expense_category_new, name='expense_category_new'),
    path('finance/expenses/categories/<str:code>/edit/', views.expense_category_edit, name='expense_category_edit'),
    path('finance/clients/<int:pk>/statement/', views.client_finance_statement, name='client_finance_statement'),
    path('finance/clients/<int:pk>/statement/pdf/', views.client_statement_pdf, name='client_statement_pdf'),
    path('finance/clients/<int:pk>/refund/', views.client_refund, name='client_refund'),
    path('finance/clients/<int:pk>/deposit-transfer/', views.client_deposit_transfer, name='client_deposit_transfer'),
    path('finance/refunds/<int:pk>/confirm/', views.client_refund_confirm, name='client_refund_confirm'),
    path('finance/refunds/<int:pk>/reject/', views.client_refund_reject, name='client_refund_reject'),
    path('finance/deposit-transfers/<int:pk>/confirm/', views.client_deposit_transfer_confirm, name='client_deposit_transfer_confirm'),
    path('finance/deposit-transfers/<int:pk>/reject/', views.client_deposit_transfer_reject, name='client_deposit_transfer_reject'),
    path('finance/periods/', views.period_list, name='period_list'),
    path('finance/periods/create/', views.period_create, name='period_create'),
    path('finance/periods/<int:pk>/', views.period_detail, name='period_detail'),
    path('finance/periods/<int:pk>/close/', views.period_close, name='period_close'),
    path('finance/periods/<int:pk>/lock/', views.period_lock, name='period_lock'),
    path('finance/seasons/create/', views.season_save, name='season_create'),
    path('finance/seasons/<int:pk>/edit/', views.season_save, name='season_edit'),
    path('finance/seasons/<int:pk>/delete/', views.season_delete, name='season_delete'),

    # ── Finance: Journal & Reports (read-only) ──
    path('finance/journal/', views.journal_list, name='journal_list'),
    path('finance/journal/<int:pk>/', views.journal_detail, name='journal_detail'),
    path('finance/trial-balance/', views.trial_balance, name='trial_balance'),
    path('finance/statements/', views.statements_list, name='statements_list'),
    path('finance/bank-accounts/', views.bank_account_list, name='bank_account_list'),
    path('finance/bank-accounts/export/csv/', views.bank_account_export_csv, name='bank_account_export_csv'),
    path('finance/bank-accounts/new/', views.bank_account_new, name='bank_account_new'),
    path('finance/bank-accounts/<int:pk>/edit/', views.bank_account_edit, name='bank_account_edit'),
    path('finance/bank-accounts/<str:kind>/<int:pk>/', views.bank_account_transactions, name='bank_account_transactions'),
    path('finance/reconciliation/', views.reconciliation_list, name='reconciliation_list'),
    path('finance/reconciliation/new/', views.reconciliation_new, name='reconciliation_new'),
    path('finance/reconciliation/import/', views.reconciliation_import, name='reconciliation_import'),
    path('finance/reconciliation/<int:pk>/match-suggested/', views.reconciliation_match_suggested, name='reconciliation_match_suggested'),
    path('finance/reconciliation/<int:pk>/match-group/', views.reconciliation_match_group, name='reconciliation_match_group'),
    path('finance/reconciliation/<int:pk>/', views.reconciliation_detail, name='reconciliation_detail'),
    path('finance/reconciliation/lines/<int:pk>/match/', views.reconciliation_match, name='reconciliation_match'),
    path('finance/reconciliation/lines/<int:pk>/unmatch/', views.reconciliation_unmatch, name='reconciliation_unmatch'),
    path('finance/penalties/', views.penalty_list, name='penalty_list'),

    # ── Receipts (Kwitansi) ──
    path('receipts/<int:pk>/pdf/', views.receipt_pdf, name='receipt_pdf'),
    path('receipts/<int:pk>/void/', views.receipt_void, name='receipt_void'),
  ]
