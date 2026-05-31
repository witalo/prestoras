from django.contrib import admin
from .models import Payment, PaymentInstallment, PenaltyAdjustment


class PaymentInstallmentInline(admin.TabularInline):
    model = PaymentInstallment
    extra = 0
    can_delete = False
    readonly_fields = ['installment', 'amount_applied', 'created_at']
    fields = ['installment', 'amount_applied', 'created_at']
    verbose_name = 'Cuota aplicada'
    verbose_name_plural = 'Cuotas a las que se aplico el pago'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ['id', 'cliente', 'prestamo_id', 'monto', 'payment_method', 'cobrador', 'payment_date', 'status', 'created_at']
    list_filter   = ['status', 'payment_method', 'payment_date', 'company', 'created_at']
    search_fields = ['client__dni', 'client__first_name', 'client__last_name', 'reference_number', 'id']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 40
    list_select_related = ['client', 'loan', 'collector', 'company']
    inlines = [PaymentInstallmentInline]
    date_hierarchy = 'payment_date'

    fieldsets = (
        ('Datos del Pago', {
            'fields': ('company', 'client', 'loan', 'collector')
        }),
        ('Monto y Metodo', {
            'fields': ('amount', 'payment_method', 'payment_date', 'reference_number', 'status')
        }),
        ('Observaciones', {
            'fields': ('observations',)
        }),
        ('Auditoria', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Cliente')
    def cliente(self, obj):
        return f"{obj.client.full_name} ({obj.client.dni})"

    @admin.display(description='Prestamo #')
    def prestamo_id(self, obj):
        return f"#{obj.loan.id}"

    @admin.display(description='Monto')
    def monto(self, obj):
        return f"S/ {obj.amount:.2f}"

    @admin.display(description='Cobrador')
    def cobrador(self, obj):
        return obj.collector.full_name if obj.collector else '-'


@admin.register(PaymentInstallment)
class PaymentInstallmentAdmin(admin.ModelAdmin):
    list_display  = ['pago', 'cuota', 'amount_applied', 'created_at']
    list_filter   = ['created_at', 'payment__company']
    readonly_fields = ['created_at']
    list_select_related = ['payment', 'installment', 'payment__client']

    @admin.display(description='Pago')
    def pago(self, obj):
        return f"Pago #{obj.payment.id} - {obj.payment.client.full_name}"

    @admin.display(description='Cuota')
    def cuota(self, obj):
        return f"Cuota #{obj.installment.installment_number}"


@admin.register(PenaltyAdjustment)
class PenaltyAdjustmentAdmin(admin.ModelAdmin):
    list_display  = ['id', 'prestamo', 'adjustment_type', 'previous_penalty', 'new_penalty', 'ajustado_por', 'created_at']
    list_filter   = ['adjustment_type', 'created_at']
    search_fields = ['loan__client__dni', 'loan__client__first_name', 'loan__client__last_name', 'reason']
    readonly_fields = ['created_at']
    list_select_related = ['loan', 'loan__client', 'adjusted_by']

    @admin.display(description='Prestamo')
    def prestamo(self, obj):
        return f"#{obj.loan.id} - {obj.loan.client.full_name}"

    @admin.display(description='Ajustado por')
    def ajustado_por(self, obj):
        return obj.adjusted_by.full_name if obj.adjusted_by else '-'
