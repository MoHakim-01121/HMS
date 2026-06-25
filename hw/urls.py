from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('company/set/', views.company_quick_set, name='company_quick_set'),

    # Confirmation Letter
    path('cl/', views.cl_list, name='cl_list'),
    path('cl/new/', views.cl_new, name='cl_new'),
    path('cl/export/csv/', views.cl_export_csv, name='cl_export_csv'),
    path('cl/export/pdf/', views.cl_list_pdf, name='cl_list_pdf'),
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
    path('invoice/<int:pk>/duplicate/', views.invoice_duplicate, name='invoice_duplicate'),

    # Invoice Services / Visa
    path('services/', views.services_list, name='services_list'),
    path('services/new/', views.services_new, name='services_new'),
    path('services/export/csv/', views.services_export_csv, name='services_export_csv'),
    path('services/export/pdf/', views.services_list_pdf, name='services_list_pdf'),
    path('services/<int:pk>/', views.services_detail, name='services_detail'),
    path('services/<int:pk>/edit/', views.services_edit, name='services_edit'),
    path('services/<int:pk>/delete/', views.services_delete, name='services_delete'),
    path('services/<int:pk>/pdf/', views.services_pdf, name='services_pdf'),
    path('services/<int:pk>/duplicate/', views.services_duplicate, name='services_duplicate'),

    # Calendar
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/cl/<int:pk>/estimasi/', views.cl_estimasi_save, name='cl_estimasi_save'),
    path('calendar/send-recap/', views.calendar_send_recap, name='calendar_send_recap'),
    path('calendar/send-reminder/<int:pk>/', views.calendar_send_reminder, name='calendar_send_reminder'),
    path('calendar/wa-targets/', views.wa_target_add, name='wa_target_add'),
    path('calendar/wa-targets/<int:pk>/toggle/', views.wa_target_toggle, name='wa_target_toggle'),
    path('calendar/wa-targets/<int:pk>/delete/', views.wa_target_delete, name='wa_target_delete'),
    path('calendar/message-templates/', views.message_template_save, name='message_template_save'),
    path('calendar/recap-settings/', views.calendar_recap_settings, name='calendar_recap_settings'),

    # Search
    path('search/', views.global_search, name='global_search'),

    # Attachments
    path('attachments/upload/', views.attachment_upload, name='attachment_upload'),
    path('attachments/<int:pk>/delete/', views.attachment_delete, name='attachment_delete'),

    # AI
    path('ai/chat/', views.ai_chat, name='ai_chat'),
    path('ai/draft/', views.ai_draft_message, name='ai_draft_message'),

    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/new/', views.client_new, name='client_new'),
    path('clients/map/', views.client_map, name='client_map'),
    path('clients/map/data/', views.client_map_data, name='client_map_data'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),

    # Hotels
    path('hotels/', views.hotel_list, name='hotel_list'),
    path('hotels/new/', views.hotel_new, name='hotel_new'),
    path('hotels/map/', views.hotel_map, name='hotel_map'),
    path('hotels/map/data/', views.hotel_map_data, name='hotel_map_data'),
    path('hotels/<int:pk>/', views.hotel_detail, name='hotel_detail'),
    path('hotels/<int:pk>/edit/', views.hotel_edit, name='hotel_edit'),
    path('hotels/<int:pk>/delete/', views.hotel_delete, name='hotel_delete'),

    # Remittance (Konoz only)
    path('remittance/', views.remittance_list, name='remittance_list'),
    path('remittance/new/', views.remittance_new, name='remittance_new'),
    path('remittance/recap/', views.remittance_recap, name='remittance_recap'),
    path('remittance/export/csv/', views.remittance_export_csv, name='remittance_export_csv'),
    path('remittance/export/pdf/', views.remittance_period_pdf, name='remittance_period_pdf'),
    path('remittance/<int:pk>/', views.remittance_detail, name='remittance_detail'),
    path('remittance/<int:pk>/edit/', views.remittance_edit, name='remittance_edit'),
    path('remittance/<int:pk>/pdf/', views.remittance_pdf, name='remittance_pdf'),
    path('remittance/<int:pk>/mark-received/', views.remittance_mark_received, name='remittance_mark_received'),
    path('remittance/<int:pk>/upload-proof/', views.remittance_upload_proof, name='remittance_upload_proof'),
    path('remittance/<int:pk>/delete/', views.remittance_delete, name='remittance_delete'),

    # User management (superuser only)
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_new, name='user_new'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),

    # Account / Profile
    path('account/profile/', views.account_profile, name='account_profile'),
    path('account/avatar/upload/', views.avatar_upload, name='avatar_upload'),
    path('account/avatar/delete/', views.avatar_delete, name='avatar_delete'),


    # Cancellation Penalty (accessible through CL)
    path('cl/<int:cl_pk>/penalty/new/', views.penalty_new, name='penalty_new'),
    path('penalty/<int:pk>/', views.penalty_detail, name='penalty_detail'),
    path('penalty/<int:pk>/edit/', views.penalty_edit, name='penalty_edit'),
    path('penalty/<int:pk>/delete/', views.penalty_delete, name='penalty_delete'),
    path('penalty/<int:pk>/pdf/', views.penalty_pdf, name='penalty_pdf'),

    # Health check
    path('health/', views.health_check, name='health_check'),
]
