from django.contrib import admin
from django.shortcuts import render

from .models import (
    ActivityLog, Attachment, BankAccount, BankTransaction, Branch, CashAccount, Client, ConfirmationLetter,
    Expense, ExpenseCategory, ExpenseLine, ExpensePayment,
    BankStatement, BankStatementLine, Hotel, Invoice, MealPlan, Pricelist,
    Remittance, RemittanceSettlement,
    InvoiceLine, InvoiceRevision, RoleDefinition, Room, RoomType, TeamMember, UserProfile,
    Currency, DocumentSequence, Vendor,
)


class SuperuserOnlyAdminSite(admin.AdminSite):
    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def login(self, request, extra_context=None):
        return render(request, 'hw/403.html', status=403)


admin.site.__class__ = SuperuserOnlyAdminSite


class ReadOnlyAdmin(admin.ModelAdmin):
    """Money and audit records change only through the app — journal, cash
    book, maker-checker, period lock, activity log. Here they are read, never
    added, edited or deleted, not even by a superuser."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyInline(admin.TabularInline):
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display  = ('invoice_number', 'customer_name', 'invoice_type', 'issued_date', 'due_date')
    list_filter   = ('invoice_type',)
    search_fields = ('invoice_number', 'client__name', 'client__brand')
    list_select_related = ('client',)
    date_hierarchy = 'issued_date'


@admin.register(ConfirmationLetter)
class ConfirmationLetterAdmin(admin.ModelAdmin):
    list_display  = ('confirmation_number', 'guest_name', 'hotel_name', 'check_in', 'check_out', 'reservation_status')
    list_filter   = ('reservation_status',)
    search_fields = ('confirmation_number', 'client__name', 'client__brand', 'hotel__name')
    list_select_related = ('client', 'hotel')
    date_hierarchy = 'check_in'


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display  = ('name', 'city', 'province', 'pic', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('name', 'city', 'pic', 'email')


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display  = ('name', 'city', 'stars', 'area', 'is_active')
    list_filter   = ('city', 'stars', 'is_active')
    search_fields = ('name', 'area')


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display  = ('name', 'hotel', 'capacity', 'occupancy', 'view', 'is_active')
    list_filter   = ('is_active', 'capacity', 'view')
    search_fields = ('name', 'hotel__name')
    readonly_fields = ('occupancy',)  # derived from capacity (RoomType.occupancy property)


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact', 'phone', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact')


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'minor_digits')


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ('key', 'last_value')
    readonly_fields = ('key', 'last_value')  # counter hanya bergerak lewat hw.numbering


@admin.register(ActivityLog)
class ActivityLogAdmin(ReadOnlyAdmin):
    list_display  = ('user', 'action', 'model_name', 'object_ref', 'timestamp')
    list_filter   = ('action',)
    search_fields = ('user__username', 'object_ref')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'action', 'model_name', 'object_ref', 'changes', 'timestamp')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ('user__username',)



@admin.register(Remittance)
class RemittanceAdmin(ReadOnlyAdmin):
    list_display  = ('remittance_number', 'date', 'total_sar', 'note', 'has_proof')
    search_fields = ('note',)
    date_hierarchy = 'date'

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
class BankAccountAdmin(ReadOnlyAdmin):
    list_display = ('bank_name', 'name', 'branch', 'currency', 'is_active')
    list_filter = ('branch', 'currency', 'is_active')


@admin.register(CashAccount)
class CashAccountAdmin(ReadOnlyAdmin):
    list_display = ('name', 'branch', 'currency', 'is_active')
    list_filter = ('branch', 'currency', 'is_active')


@admin.register(BankTransaction)
class BankTransactionAdmin(ReadOnlyAdmin):
    list_display = ('transaction_date', 'account', 'direction', 'amount_sar', 'source_type', 'source_id', 'status')
    list_filter = ('direction', 'status', 'source_type')
    date_hierarchy = 'transaction_date'


class BankStatementLineInline(ReadOnlyInline):
    model = BankStatementLine
    extra = 0


@admin.register(BankStatement)
class BankStatementAdmin(ReadOnlyAdmin):
    list_display = ('account', 'currency', 'period_start', 'period_end', 'opening_balance', 'closing_balance')
    inlines = [BankStatementLineInline]


class ExpenseLineInline(ReadOnlyInline):
    model = ExpenseLine
    extra = 0


class ExpensePaymentInline(ReadOnlyInline):
    model = ExpensePayment
    extra = 0


@admin.register(Expense)
class ExpenseAdmin(ReadOnlyAdmin):
    list_display = ('expense_number', 'branch', 'expense_date', 'vendor',
                    'total_amount_sar', 'status')
    list_filter = ('branch', 'status', 'expense_date')
    search_fields = ('expense_number', 'vendor', 'description')
    inlines = [ExpenseLineInline, ExpensePaymentInline]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'ledger_account', 'is_active')
    list_filter = ('is_active',)


@admin.register(RemittanceSettlement)
class RemittanceSettlementAdmin(ReadOnlyAdmin):
    list_display = ('remittance', 'received_amount_sar', 'received_date')


admin.site.register(InvoiceLine, ReadOnlyAdmin)
admin.site.register(InvoiceRevision, ReadOnlyAdmin)
admin.site.register(Room)
admin.site.register(Attachment)
admin.site.register(TeamMember)
admin.site.register(Pricelist)
