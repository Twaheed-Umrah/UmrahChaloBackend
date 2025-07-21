from django.contrib import admin
from .models import (
    PaymentMethod,
    Payment,
    PaymentRefund,
    PaymentTransaction,
    PaymentWebhook
)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'is_active', 'processing_fee_percentage', 'processing_fee_fixed', 'created_at')
    list_filter = ('type', 'is_active')
    search_fields = ('name', 'type')
    ordering = ('-created_at',)


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    readonly_fields = ('created_at',)
    can_delete = False


class PaymentRefundInline(admin.TabularInline):
    model = PaymentRefund
    extra = 0
    readonly_fields = ('requested_at', 'status')
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'currency', 'status', 'purpose', 'created_at')
    list_filter = ('status', 'purpose', 'currency', 'payment_method')
    search_fields = ('id', 'user__email', 'gateway_payment_id', 'gateway_order_id')
    ordering = ('-created_at',)
    inlines = [PaymentTransactionInline, PaymentRefundInline]
    readonly_fields = ('created_at', 'updated_at', 'initiated_at', 'completed_at', 'failed_at')


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'amount', 'reason', 'status', 'requested_at', 'completed_at')
    list_filter = ('status', 'reason')
    search_fields = ('id', 'payment__user__email')
    ordering = ('-created_at',)
    readonly_fields = ('requested_at', 'created_at', 'updated_at')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'transaction_type', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'currency')
    search_fields = ('id', 'payment__user__email', 'gateway_transaction_id')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)


@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment_method', 'event_type', 'gateway_event_id', 'status', 'created_at')
    list_filter = ('status', 'event_type')
    search_fields = ('gateway_event_id', 'event_type')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'processed_at')
