from django.contrib import admin
from .models import Payment, PaymentInstallment, PenaltyAdjustment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'loan', 'amount', 'payment_method', 'collector', 'payment_date', 'status']
    list_filter = ['status', 'payment_method', 'payment_date', 'company']
    search_fields = ['client__dni', 'client__first_name', 'client__last_name', 'reference_number']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Información General', {
            'fields': ('company', 'client', 'loan', 'collector')
        }),
        ('Pago', {
            'fields': ('amount', 'payment_method', 'payment_date', 'reference_number', 'status')
        }),
        ('Observaciones', {
            'fields': ('observations',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(PaymentInstallment)
class PaymentInstallmentAdmin(admin.ModelAdmin):
    list_display = ['payment', 'installment', 'amount_applied', 'created_at']
    list_filter = ['created_at']
    readonly_fields = ['created_at']

@admin.register(PenaltyAdjustment)
class PenaltyAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'loan', 'adjustment_type', 'previous_penalty', 'new_penalty', 'adjusted_by', 'created_at']
    list_filter = ['adjustment_type', 'created_at']
    search_fields = ['loan__client__dni', 'loan__client__first_name', 'reason']
    readonly_fields = ['created_at']
