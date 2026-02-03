from django.contrib import admin
from .models import Loan, Installment, Refinancing

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'company', 'initial_amount', 'interest_rate', 'status', 'start_date', 'end_date']
    list_filter = ['status', 'company', 'periodicity', 'created_at']
    search_fields = ['client__dni', 'client__first_name', 'client__last_name']
    readonly_fields = ['total_amount', 'pending_amount', 'paid_amount', 'penalty_applied', 'created_at', 'updated_at']
    fieldsets = (
        ('Información General', {
            'fields': ('company', 'client', 'loan_type', 'created_by')
        }),
        ('Monto y Tasa', {
            'fields': ('initial_amount', 'interest_rate', 'total_amount')
        }),
        ('Plazo', {
            'fields': ('number_of_installments', 'periodicity', 'start_date', 'end_date')
        }),
        ('Estado', {
            'fields': ('status', 'paid_amount', 'pending_amount')
        }),
        ('Mora', {
            'fields': ('penalty_type', 'penalty_amount', 'penalty_percentage', 'penalty_applied')
        }),
        ('Refinanciamiento', {
            'fields': ('original_loan', 'is_refinanced')
        }),
        ('Observaciones', {
            'fields': ('observations',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ['loan', 'installment_number', 'due_date', 'total_amount', 'paid_amount', 'status']
    list_filter = ['status', 'due_date']
    search_fields = ['loan__client__dni', 'loan__client__first_name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Refinancing)
class RefinancingAdmin(admin.ModelAdmin):
    list_display = ['id', 'original_loan', 'new_loan', 'refinanced_amount', 'interest_rate', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
