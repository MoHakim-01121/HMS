from django.contrib import admin

from .models import (
    ActivityLog, Attachment, Client, ConfirmationLetter,
    Hotel, Invoice, Payment, Reservation, Room, ServiceItem, UserProfile,
)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ('invoice_number', 'customer_name', 'company', 'invoice_type', 'issued_date', 'due_date')
    list_filter   = ('company', 'invoice_type')
    search_fields = ('invoice_number', 'customer_name')
    date_hierarchy = 'issued_date'


@admin.register(ConfirmationLetter)
class ConfirmationLetterAdmin(admin.ModelAdmin):
    list_display  = ('confirmation_number', 'guest_name', 'hotel_name', 'company', 'check_in', 'check_out', 'reservation_status')
    list_filter   = ('company', 'reservation_status')
    search_fields = ('confirmation_number', 'guest_name', 'hotel_name')
    date_hierarchy = 'check_in'


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display  = ('name', 'company', 'city', 'province', 'pic', 'is_active')
    list_filter   = ('company', 'is_active')
    search_fields = ('name', 'city', 'pic', 'email')


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display  = ('name', 'company', 'city', 'stars', 'area', 'is_active')
    list_filter   = ('company', 'city', 'stars', 'is_active')
    search_fields = ('name', 'area')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ('invoice', 'payment_date', 'amount', 'currency', 'method', 'linked_number')
    list_filter   = ('currency', 'method')
    search_fields = ('linked_number', 'invoice__invoice_number')
    date_hierarchy = 'payment_date'


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'action', 'model_name', 'object_ref', 'company', 'timestamp')
    list_filter   = ('action', 'company')
    search_fields = ('user__username', 'object_ref')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'action', 'model_name', 'object_ref', 'company', 'changes', 'timestamp')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ('user__username',)


admin.site.register(Reservation)
admin.site.register(Room)
admin.site.register(ServiceItem)
admin.site.register(Attachment)
