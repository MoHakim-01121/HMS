from django.contrib import admin
from django.shortcuts import render

from .models import (
    ActivityLog, Attachment, BankAccount, BankTransaction, Branch, CashAccount, Client, ConfirmationLetter,
    Expense, ExpenseCategory, ExpenseLine, ExpensePayment,
    BankStatement, BankStatementLine, Hotel, Invoice, MealPlan, Pricelist,
    Remittance, RemittanceLine, RemittanceSettlement,
    Reservation, RoleDefinition, Room, RoomType, ServiceItem, TeamMember, UserProfile,
    Currency, DocumentSequence, Vendor,
)


class SuperuserOnlyAdminSite(admin.AdminSite):
    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def login(self, request, extra_context=None):
        return render(request, 'hw/403.html', status=403)


admin.site.__class__ = SuperuserOnlyAdminSite


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ('invoice_number', 'customer_name', 'invoice_type', 'issued_date', 'due_date')
    list_filter   = ('invoice_type',)
    search_fields = ('invoice_number', 'customer_name')
    date_hierarchy = 'issued_date'


@admin.register(ConfirmationLetter)
class ConfirmationLetterAdmin(admin.ModelAdmin):
    list_display  = ('confirmation_number', 'guest_name', 'hotel_name', 'check_in', 'check_out', 'reservation_status')
    list_filter   = ('reservation_status',)
    search_fields = ('confirmation_number', 'guest_name', 'hotel_name')
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
class ActivityLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'action', 'model_name', 'object_ref', 'timestamp')
    list_filter   = ('action',)
    search_fields = ('user__username', 'object_ref')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'action', 'model_name', 'object_ref', 'changes', 'timestamp')


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
    list_display  = ('remittance_number', 'date', 'total_sar', 'note', 'has_proof')
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


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_date', 'account', 'direction', 'amount_sar', 'source_type', 'source_id', 'status')
    list_filter = ('direction', 'status', 'source_type')
    date_hierarchy = 'transaction_date'


class BankStatementLineInline(admin.TabularInline):
    model = BankStatementLine
    extra = 0


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    list_display = ('account', 'currency', 'period_start', 'period_end', 'opening_balance', 'closing_balance')
    inlines = [BankStatementLineInline]


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


@admin.register(RemittanceSettlement)
class RemittanceSettlementAdmin(admin.ModelAdmin):
    list_display = ('remittance', 'received_amount_sar', 'received_date')


admin.site.register(Reservation)
admin.site.register(Room)
admin.site.register(ServiceItem)
admin.site.register(Attachment)
admin.site.register(TeamMember)
admin.site.register(Pricelist)
