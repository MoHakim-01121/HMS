from django.contrib import admin
from django.shortcuts import render

from .models import (
    ActivityLog, Attachment, BankAccount, Branch, CashAccount, Client, ConfirmationLetter,
    Expense, ExpenseCategory, ExpenseLine, ExpensePayment,
    HQObligation, Hotel, Invoice, MealPlan, Payment, Pricelist, Remittance, RemittanceAllocation,
    RemittanceLine, RemittanceSettlement,
    Reservation, RoleDefinition, Room, RoomType, ServiceItem, TeamMember, UserProfile,
)


class SuperuserOnlyAdminSite(admin.AdminSite):
    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def login(self, request, extra_context=None):
        return render(request, 'hw/403.html', status=403)


admin.site.__class__ = SuperuserOnlyAdminSite


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


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display  = ('name', 'hotel', 'capacity', 'occupancy', 'view', 'is_active')
    list_filter   = ('is_active', 'occupancy', 'view', 'hotel__company')
    search_fields = ('name', 'hotel__name')


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)


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


class RemittanceLineInline(admin.TabularInline):
    model = RemittanceLine
    extra = 0
    readonly_fields = ('linked_number', 'invoice', 'amount_sar')


@admin.register(Remittance)
class RemittanceAdmin(admin.ModelAdmin):
    list_display  = ('remittance_number', 'date', 'company', 'total_sar', 'note', 'has_proof')
    list_filter   = ('company',)
    search_fields = ('note',)
    date_hierarchy = 'date'
    inlines       = [RemittanceLineInline]

    @admin.display(boolean=True, description='Kwitansi')
    def has_proof(self, obj):
        return bool(obj.proof)


@admin.register(RoleDefinition)
class RoleDefinitionAdmin(admin.ModelAdmin):
    """Break-glass access to the matrix; /roles/ is the normal way in."""
    list_display  = ('label', 'slug', 'is_system', 'grants_django_staff', 'order')
    list_filter   = ('is_system', 'grants_django_staff')
    search_fields = ('slug', 'label')
    readonly_fields = ('is_system',)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('bank_name', 'name', 'branch', 'currency', 'is_active')
    list_filter = ('branch', 'currency', 'is_active')


@admin.register(CashAccount)
class CashAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'currency', 'is_active')
    list_filter = ('branch', 'currency', 'is_active')


class ExpenseLineInline(admin.TabularInline):
    model = ExpenseLine
    extra = 0


class ExpensePaymentInline(admin.TabularInline):
    model = ExpensePayment
    extra = 0


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('expense_number', 'branch', 'expense_date', 'vendor',
                    'total_amount_sar', 'status')
    list_filter = ('branch', 'status', 'expense_date')
    search_fields = ('expense_number', 'vendor', 'description')
    inlines = [ExpenseLineInline, ExpensePaymentInline]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'ledger_account', 'is_active')
    list_filter = ('is_active',)


@admin.register(HQObligation)
class HQObligationAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'amount_sar', 'status', 'due_date')
    list_filter = ('branch', 'status')


class RemittanceAllocationInline(admin.TabularInline):
    model = RemittanceAllocation
    extra = 0


@admin.register(RemittanceSettlement)
class RemittanceSettlementAdmin(admin.ModelAdmin):
    list_display = ('remittance', 'received_amount_sar', 'received_date')
    inlines = [RemittanceAllocationInline]


admin.site.register(Reservation)
admin.site.register(Room)
admin.site.register(ServiceItem)
admin.site.register(Attachment)
admin.site.register(TeamMember)
admin.site.register(Pricelist)
