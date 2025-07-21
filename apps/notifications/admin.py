from django.contrib import admin
from .models import (
    NotificationTemplate,
    Notification,
    NotificationPreference,
    NotificationLog,
    BulkNotification
)

@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('notification_type', 'title', 'send_email', 'send_sms', 'send_app', 'is_active')
    list_filter = ('send_email', 'send_sms', 'send_app', 'is_active')
    search_fields = ('notification_type', 'title', 'email_subject', 'email_body', 'sms_body', 'app_body')
    ordering = ('notification_type',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'recipient', 'template', 'status', 'priority',
        'created_at', 'sent_at', 'read_at', 'retry_count'
    )
    list_filter = ('status', 'priority', 'email_sent', 'sms_sent', 'app_sent')
    search_fields = ('title', 'recipient__email', 'message')
    readonly_fields = ('created_at', 'sent_at', 'read_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'digest_frequency', 'email_marketing', 'sms_marketing', 'app_marketing')
    list_filter = ('digest_frequency', 'email_marketing', 'sms_marketing', 'app_marketing')
    search_fields = ('user__email',)
    ordering = ('user__email',)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        'notification', 'channel', 'provider', 'delivered',
        'sent_at', 'delivered_at', 'error_code'
    )
    list_filter = ('channel', 'delivered', 'provider')
    search_fields = ('notification__title', 'provider', 'error_message', 'error_code')
    ordering = ('-sent_at',)


@admin.register(BulkNotification)
class BulkNotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'target_user_type', 'status', 'send_email', 'send_sms', 'send_app',
        'total_recipients', 'sent_count', 'failed_count', 'created_by', 'created_at'
    )
    list_filter = ('status', 'send_email', 'send_sms', 'send_app', 'target_user_type')
    search_fields = ('title', 'message', 'created_by__email')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'completed_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
