from django.contrib import admin
from .models import Loan, Installment, Refinancing


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    can_delete = False
    readonly_fields = [
        'installment_number', 'due_date',
        'capital_amount', 'interest_amount', 'total_amount',
        'paid_amount', 'status', 'created_at',
    ]
    fields = ['installment_number', 'due_date', 'total_amount', 'paid_amount', 'status']
    ordering = ['installment_number']
    verbose_name = 'Cuota'
    verbose_name_plural = 'Cuotas del prestamo'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display  = ['id', 'cliente', 'company', 'initial_amount', 'total_amount', 'paid_amount', 'pendiente', 'status', 'periodicity', 'start_date', 'end_date']
    list_filter   = ['status', 'company', 'periodicity', 'is_refinanced', 'created_at']
    search_fields = ['client__dni', 'client__first_name', 'client__last_name', 'id']
    readonly_fields = ['total_amount', 'pending_amount', 'paid_amount', 'penalty_applied', 'created_at', 'updated_at']
    list_per_page = 30
    list_select_related = ['client', 'company', 'loan_type']
    inlines = [InstallmentInline]
    actions = ['marcar_completado', 'marcar_activo', 'marcar_moroso']

    fieldsets = (
        ('General', {
            'fields': ('company', 'client', 'loan_type', 'created_by')
        }),
        ('Monto y Tasa', {
            'fields': ('initial_amount', 'interest_rate', 'total_amount')
        }),
        ('Plazo', {
            'fields': ('number_of_installments', 'periodicity', 'start_date', 'end_date')
        }),
        ('Estado de Pago', {
            'fields': ('status', 'paid_amount', 'pending_amount')
        }),
        ('Mora', {
            'fields': ('penalty_type', 'penalty_amount', 'penalty_percentage', 'penalty_applied'),
            'classes': ('collapse',)
        }),
        ('Refinanciamiento', {
            'fields': ('original_loan', 'is_refinanced'),
            'classes': ('collapse',)
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

    @admin.display(description='Pendiente')
    def pendiente(self, obj):
        return f"S/ {obj.pending_amount:.2f}"

    @admin.action(description='Marcar como Completado')
    def marcar_completado(self, request, queryset):
        n = queryset.update(status='COMPLETED')
        self.message_user(request, f'{n} prestamo(s) marcado(s) como Completado.')

    @admin.action(description='Marcar como Activo')
    def marcar_activo(self, request, queryset):
        n = queryset.update(status='ACTIVE')
        self.message_user(request, f'{n} prestamo(s) marcado(s) como Activo.')

    @admin.action(description='Marcar como Moroso')
    def marcar_moroso(self, request, queryset):
        n = queryset.update(status='DEFAULTING')
        self.message_user(request, f'{n} prestamo(s) marcado(s) como Moroso.')


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display  = ['prestamo', 'installment_number', 'due_date', 'total_amount', 'paid_amount', 'pendiente_cuota', 'status']
    list_filter   = ['status', 'due_date', 'loan__company', 'loan__status']
    search_fields = ['loan__client__dni', 'loan__client__first_name', 'loan__client__last_name', 'loan__id']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50
    list_select_related = ['loan', 'loan__client']

    @admin.display(description='Prestamo')
    def prestamo(self, obj):
        return f"#{obj.loan.id} - {obj.loan.client.full_name}"

    @admin.display(description='Pendiente')
    def pendiente_cuota(self, obj):
        return f"S/ {(obj.total_amount - obj.paid_amount):.2f}"


@admin.register(Refinancing)
class RefinancingAdmin(admin.ModelAdmin):
    list_display  = ['id', 'prestamo_original', 'prestamo_nuevo', 'refinanced_amount', 'interest_rate', 'status', 'created_at']
    list_filter   = ['status', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    search_fields = ['original_loan__client__dni', 'original_loan__client__first_name']

    @admin.display(description='Prestamo original')
    def prestamo_original(self, obj):
        return f"#{obj.original_loan.id}" if obj.original_loan else '-'

    @admin.display(description='Prestamo nuevo')
    def prestamo_nuevo(self, obj):
        return f"#{obj.new_loan.id}" if obj.new_loan else '-'
