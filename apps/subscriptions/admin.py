from django.contrib import admin
from .models import (
    SubscriptionPlan,
    Subscription,
    SubscriptionHistory,
    SubscriptionFeature,
    SubscriptionAlert
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_type', 'duration_months', 'price', 'is_active')
    list_filter = ('plan_type', 'duration_months', 'is_active')
    search_fields = ('name',)
    ordering = ('price',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'start_date', 'end_date', 'amount_paid', 'auto_renew')
    list_filter = ('status', 'auto_renew', 'plan__plan_type')
    search_fields = ('user__email', 'plan__name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'action', 'previous_plan', 'new_plan', 'amount', 'created_by', 'created_at')
    list_filter = ('action',)
    search_fields = ('subscription__user__email', 'notes')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)


@admin.register(SubscriptionFeature)
class SubscriptionFeatureAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'feature_name', 'usage_count', 'limit', 'is_limit_reached_display')
    search_fields = ('subscription__user__email', 'feature_name')
    ordering = ('-updated_at',)
    readonly_fields = ('created_at', 'updated_at')

    def is_limit_reached_display(self, obj):
        return obj.is_limit_reached
    is_limit_reached_display.boolean = True
    is_limit_reached_display.short_description = 'Limit Reached?'


@admin.register(SubscriptionAlert)
class SubscriptionAlertAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'alert_type', 'is_sent', 'sent_at', 'created_at')
    list_filter = ('alert_type', 'is_sent')
    search_fields = ('subscription__user__email', 'message')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'sent_at')
