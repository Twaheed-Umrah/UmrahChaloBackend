from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import (
    Notification, 
    NotificationPreference, 
    NotificationLog, 
    BulkNotification
)
from .services import NotificationService


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'recipient_email', 'notification_type', 'status', 
        'priority', 'channels_display', 'created_at', 'sent_at'
    ]
    list_filter = [
        'notification_type', 'status', 'priority', 'send_email', 
        'send_sms', 'send_app', 'created_at'
    ]
    search_fields = ['title', 'message', 'recipient__email', 'recipient__full_name']
    readonly_fields = ['created_at', 'sent_at', 'read_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('recipient', 'notification_type', 'title', 'message', 'priority')
        }),
        ('Content & Data', {
            'fields': ('data', 'content_type', 'object_id'),
            'classes': ('collapse',)
        }),
        ('Channel Settings', {
            'fields': ('send_email', 'send_sms', 'send_app')
        }),
        ('Delivery Status', {
            'fields': ('status', 'email_sent', 'sms_sent', 'app_sent')
        }),
        ('Retry Settings', {
            'fields': ('retry_count', 'max_retries', 'next_retry_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'sent_at', 'read_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['retry_failed_notifications', 'mark_as_read', 'resend_notifications']
    
    def recipient_email(self, obj):
        return obj.recipient.email
    recipient_email.short_description = 'Recipient'
    recipient_email.admin_order_field = 'recipient__email'
    
    def channels_display(self, obj):
        channels = []
        if obj.send_email:
            color = 'green' if obj.email_sent else 'red'
            channels.append(f'<span style="color: {color};">📧</span>')
        if obj.send_sms:
            color = 'green' if obj.sms_sent else 'red'
            channels.append(f'<span style="color: {color};">📱</span>')
        if obj.send_app:
            color = 'green' if obj.app_sent else 'red'
            channels.append(f'<span style="color: {color};">📲</span>')
        return format_html(' '.join(channels))
    channels_display.short_description = 'Channels'
    
    def retry_failed_notifications(self, request, queryset):
        """Admin action to retry failed notifications"""
        failed_notifications = queryset.filter(status='failed')
        count = 0
        
        for notification in failed_notifications:
            if notification.can_retry():
                from .tasks import send_notification_task
                send_notification_task.delay(notification.id)
                count += 1
        
        self.message_user(request, f'{count} notifications queued for retry.')
    retry_failed_notifications.short_description = 'Retry failed notifications'
    
    def mark_as_read(self, request, queryset):
        """Admin action to mark notifications as read"""
        count = queryset.filter(status='sent').count()
        queryset.filter(status='sent').update(
            status='read',
            read_at=timezone.now()
        )
        self.message_user(request, f'{count} notifications marked as read.')
    mark_as_read.short_description = 'Mark as read'
    
    def resend_notifications(self, request, queryset):
        """Admin action to resend notifications"""
        count = 0
        for notification in queryset:
            notification.status = 'pending'
            notification.retry_count = 0
            notification.next_retry_at = None
            notification.save()
            
            from .tasks import send_notification_task
            send_notification_task.delay(notification.id)
            count += 1
        
        self.message_user(request, f'{count} notifications queued for resending.')
    resend_notifications.short_description = 'Resend notifications'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'user_type', 'digest_frequency', 'updated_at']
    list_filter = ['digest_frequency', 'user__user_type', 'updated_at']
    search_fields = ['user__email', 'user__full_name']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Email Preferences', {
            'fields': (
                'email_lead_notifications', 'email_subscription_notifications',
                'email_package_notifications', 'email_review_notifications',
                'email_pay_notifications', 'email_verification_notifications',
                'email_marketing'
            )
        }),
        ('SMS Preferences', {
            'fields': (
                'sms_lead_notifications', 'sms_subscription_notifications',
                'sms_package_notifications', 'sms_review_notifications',
                'sms_payment_notifications', 'sms_verification_notifications',
                'sms_marketing'
            )
        }),
        ('App Preferences', {
            'fields': (
                'app_lead_notifications', 'app_subscription_notifications',
                'app_package_notifications', 'app_review_notifications',
                'app_payment_notifications', 'app_verification_notifications',
                'app_marketing'
            )
        }),
        ('Settings', {
            'fields': ('digest_frequency', 'quiet_hours_start', 'quiet_hours_end')
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'
    
    def user_type(self, obj):
        return obj.user.get_user_type_display()
    user_type.short_description = 'User Type'
    user_type.admin_order_field = 'user__user_type'


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = [
        'notification_title', 'channel', 'delivered', 'provider', 
        'sent_at', 'delivered_at', 'error_message_short'
    ]
    list_filter = ['channel', 'delivered', 'provider', 'sent_at']
    search_fields = [
        'notification__title', 'notification__recipient__email', 
        'error_message', 'provider'
    ]
    readonly_fields = ['sent_at', 'delivered_at']
    date_hierarchy = 'sent_at'
    
    def notification_title(self, obj):
        return obj.notification.title
    notification_title.short_description = 'Notification'
    notification_title.admin_order_field = 'notification__title'
    
    def error_message_short(self, obj):
        if obj.error_message:
            return obj.error_message[:50] + ('...' if len(obj.error_message) > 50 else '')
        return '-'
    error_message_short.short_description = 'Error'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('notification')


@admin.register(BulkNotification)
class BulkNotificationAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'notification_type', 'target_user_type', 'status',
        'total_recipients', 'sent_count', 'failed_count', 'created_at'
    ]
    list_filter = ['status', 'target_user_type', 'notification_type', 'created_at']
    search_fields = ['title', 'message', 'created_by__email']
    readonly_fields = [
        'total_recipients', 'sent_count', 'failed_count',
        'created_at', 'updated_at', 'started_at', 'completed_at'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'message', 'notification_type', 'created_by')
        }),
        ('Targeting', {
            'fields': ('target_user_type', 'target_filters')
        }),
        ('Channels', {
            'fields': ('send_email', 'send_sms', 'send_app')
        }),
        ('Scheduling', {
            'fields': ('scheduled_at',)
        }),
        ('Status & Stats', {
            'fields': (
                'status', 'total_recipients', 'sent_count', 'failed_count'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['send_bulk_notifications', 'cancel_bulk_notifications']
    
    def send_bulk_notifications(self, request, queryset):
        """Admin action to send bulk notifications"""
        draft_notifications = queryset.filter(status='draft')
        count = 0
        
        for bulk_notification in draft_notifications:
            from .tasks import send_bulk_notification_task
            send_bulk_notification_task.delay(bulk_notification.id)
            count += 1
        
        self.message_user(request, f'{count} bulk notifications queued for sending.')
    send_bulk_notifications.short_description = 'Send bulk notifications'
    
    def cancel_bulk_notifications(self, request, queryset):
        """Admin action to cancel bulk notifications"""
        count = queryset.filter(
            status__in=['draft', 'scheduled']
        ).update(status='cancelled')
        
        self.message_user(request, f'{count} bulk notifications cancelled.')
    cancel_bulk_notifications.short_description = 'Cancel bulk notifications'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


# Custom admin views for dashboard
class NotificationDashboard:
    """Custom dashboard views for notification statistics"""
    
    @staticmethod
    def get_stats():
        """Get notification statistics for dashboard"""
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        stats = {
            'today': {
                'total': Notification.objects.filter(created_at__date=today).count(),
                'sent': Notification.objects.filter(created_at__date=today, status='sent').count(),
                'failed': Notification.objects.filter(created_at__date=today, status='failed').count(),
                'pending': Notification.objects.filter(created_at__date=today, status='pending').count(),
            },
            'week': {
                'total': Notification.objects.filter(created_at__gte=week_ago).count(),
                'sent': Notification.objects.filter(created_at__gte=week_ago, status='sent').count(),
                'failed': Notification.objects.filter(created_at__gte=week_ago, status='failed').count(),
                'pending': Notification.objects.filter(created_at__gte=week_ago, status='pending').count(),
            },
            'month': {
                'total': Notification.objects.filter(created_at__gte=month_ago).count(),
                'sent': Notification.objects.filter(created_at__gte=month_ago, status='sent').count(),
                'failed': Notification.objects.filter(created_at__gte=month_ago, status='failed').count(),
                'pending': Notification.objects.filter(created_at__gte=month_ago, status='pending').count(),
            }
        }
        
        return stats