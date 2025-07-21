import django_filters
from django_filters import rest_framework as filters
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import (
    Notification, NotificationTemplate, NotificationPreference,
    NotificationLog, BulkNotification
)

User = get_user_model()


class NotificationFilter(filters.FilterSet):
    """Filter for notifications"""
    
    # Status filters
    status = filters.ChoiceFilter(
        choices=[
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('failed', 'Failed'),
            ('read', 'Read'),
        ]
    )
    
    # Priority filters
    priority = filters.ChoiceFilter(
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ]
    )
    
    # Read status filters
    is_read = filters.BooleanFilter(
        method='filter_is_read',
        label='Is Read'
    )
    
    # Template type filter
    template_type = filters.CharFilter(
        field_name='template__notification_type',
        lookup_expr='icontains'
    )
    
    # Date range filters
    created_after = filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    
    created_before = filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte'
    )
    
    # Date filters (for convenience)
    created_date = filters.DateFilter(
        field_name='created_at',
        lookup_expr='date'
    )
    
    sent_after = filters.DateTimeFilter(
        field_name='sent_at',
        lookup_expr='gte'
    )
    
    sent_before = filters.DateTimeFilter(
        field_name='sent_at',
        lookup_expr='lte'
    )
    
    # Channel filters
    email_sent = filters.BooleanFilter()
    sms_sent = filters.BooleanFilter()
    app_sent = filters.BooleanFilter()
    
    # Recipient filters (for admin views)
    recipient = filters.ModelChoiceFilter(
        queryset=User.objects.all()
    )
    
    recipient_email = filters.CharFilter(
        field_name='recipient__email',
        lookup_expr='icontains'
    )
    
    recipient_name = filters.CharFilter(
        method='filter_recipient_name',
        label='Recipient Name'
    )
    
    # Retry filters
    has_retries = filters.BooleanFilter(
        method='filter_has_retries',
        label='Has Retries'
    )
    
    retry_count = filters.NumberFilter()
    retry_count_gte = filters.NumberFilter(
        field_name='retry_count',
        lookup_expr='gte'
    )
    
    # Time-based convenience filters
    today = filters.BooleanFilter(
        method='filter_today',
        label='Today'
    )
    
    this_week = filters.BooleanFilter(
        method='filter_this_week',
        label='This Week'
    )
    
    this_month = filters.BooleanFilter(
        method='filter_this_month',
        label='This Month'
    )
    
    # Unread notifications
    unread_only = filters.BooleanFilter(
        method='filter_unread_only',
        label='Unread Only'
    )
    
    class Meta:
        model = Notification
        fields = [
            'status', 'priority', 'template_type', 'email_sent', 'sms_sent',
            'app_sent', 'recipient', 'retry_count'
        ]
    
    def filter_is_read(self, queryset, name, value):
        """Filter by read status"""
        if value:
            return queryset.filter(status='read')
        return queryset.exclude(status='read')
    
    def filter_recipient_name(self, queryset, name, value):
        """Filter by recipient name"""
        return queryset.filter(
            models.Q(recipient__first_name__icontains=value) |
            models.Q(recipient__last_name__icontains=value)
        )
    
    def filter_has_retries(self, queryset, name, value):
        """Filter notifications with retries"""
        if value:
            return queryset.filter(retry_count__gt=0)
        return queryset.filter(retry_count=0)
    
    def filter_today(self, queryset, name, value):
        """Filter notifications from today"""
        if value:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today)
        return queryset
    
    def filter_this_week(self, queryset, name, value):
        """Filter notifications from this week"""
        if value:
            week_ago = timezone.now() - timezone.timedelta(days=7)
            return queryset.filter(created_at__gte=week_ago)
        return queryset
    
    def filter_this_month(self, queryset, name, value):
        """Filter notifications from this month"""
        if value:
            month_ago = timezone.now() - timezone.timedelta(days=30)
            return queryset.filter(created_at__gte=month_ago)
        return queryset
    
    def filter_unread_only(self, queryset, name, value):
        """Filter only unread notifications"""
        if value:
            return queryset.filter(status__in=['pending', 'sent'])
        return queryset


class NotificationTemplateFilter(filters.FilterSet):
    """Filter for notification templates"""
    
    notification_type = filters.CharFilter(lookup_expr='icontains')
    is_active = filters.BooleanFilter()
    
    # Channel filters
    send_email = filters.BooleanFilter()
    send_sms = filters.BooleanFilter()
    send_app = filters.BooleanFilter()
    
    # Date filters
    created_after = filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    
    created_before = filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte'
    )
    
    # Search in content
    has_email_body = filters.BooleanFilter(
        method='filter_has_email_body',
        label='Has Email Body'
    )
    
    has_sms_body = filters.BooleanFilter(
        method='filter_has_sms_body',
        label='Has SMS Body'
    )
    
    has_app_body = filters.BooleanFilter(
        method='filter_has_app_body',
        label='Has App Body'
    )
    
    class Meta:
        model = NotificationTemplate
        fields = [
            'notification_type', 'is_active', 'send_email', 'send_sms', 'send_app'
        ]
    
    def filter_has_email_body(self, queryset, name, value):
        """Filter templates with email body"""
        if value:
            return queryset.exclude(
                models.Q(email_body__isnull=True) | models.Q(email_body='')
            )
        return queryset.filter(
            models.Q(email_body__isnull=True) | models.Q(email_body='')
        )
    
    def filter_has_sms_body(self, queryset, name, value):
        """Filter templates with SMS body"""
        if value:
            return queryset.exclude(
                models.Q(sms_body__isnull=True) | models.Q(sms_body='')
            )
        return queryset.filter(
            models.Q(sms_body__isnull=True) | models.Q(sms_body='')
        )
    
    def filter_has_app_body(self, queryset, name, value):
        """Filter templates with app body"""
        if value:
            return queryset.exclude(
                models.Q(app_body__isnull=True) | models.Q(app_body='')
            )
        return queryset.filter(
            models.Q(app_body__isnull=True) | models.Q(app_body='')
        )


class NotificationLogFilter(filters.FilterSet):
    """Filter for notification logs"""
    
    # Channel filter
    channel = filters.ChoiceFilter(
        choices=[
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('app', 'App'),
        ]
    )
    
    # Delivery status
    delivered = filters.BooleanFilter()
    
    # Provider filter
    provider = filters.CharFilter(lookup_expr='icontains')
    
    # Date filters
    sent_after = filters.DateTimeFilter(
        field_name='sent_at',
        lookup_expr='gte'
    )
    
    sent_before = filters.DateTimeFilter(
        field_name='sent_at',
        lookup_expr='lte'
    )
    
    delivered_after = filters.DateTimeFilter(
        field_name='delivered_at',
        lookup_expr='gte'
    )
    
    delivered_before = filters.DateTimeFilter(
        field_name='delivered_at',
        lookup_expr='lte'
    )
    
    # Error filters
    has_error = filters.BooleanFilter(
        method='filter_has_error',
        label='Has Error'
    )
    
    error_code = filters.CharFilter(lookup_expr='icontains')
    
    # Notification filters
    notification_status = filters.CharFilter(
        field_name='notification__status'
    )
    
    notification_priority = filters.CharFilter(
        field_name='notification__priority'
    )
    
    recipient_email = filters.CharFilter(
        field_name='notification__recipient__email',
        lookup_expr='icontains'
    )
    
    # Time-based filters
    today = filters.BooleanFilter(
        method='filter_today',
        label='Today'
    )
    
    failed_only = filters.BooleanFilter(
        method='filter_failed_only',
        label='Failed Only'
    )
    
    class Meta:
        model = NotificationLog
        fields = [
            'channel', 'delivered', 'provider', 'error_code',
            'notification_status', 'notification_priority'
        ]
    
    def filter_has_error(self, queryset, name, value):
        """Filter logs with errors"""
        if value:
            return queryset.exclude(
                models.Q(error_message__isnull=True) | models.Q(error_message='')
            )
        return queryset.filter(
            models.Q(error_message__isnull=True) | models.Q(error_message='')
        )
    
    def filter_today(self, queryset, name, value):
        """Filter logs from today"""
        if value:
            today = timezone.now().date()
            return queryset.filter(sent_at__date=today)
        return queryset
    
    def filter_failed_only(self, queryset, name, value):
        """Filter only failed deliveries"""
        if value:
            return queryset.filter(delivered=False)
        return queryset


class BulkNotificationFilter(filters.FilterSet):
    """Filter for bulk notifications"""
    
    # Status filter
    status = filters.ChoiceFilter(
        choices=[
            ('draft', 'Draft'),
            ('scheduled', 'Scheduled'),
            ('sending', 'Sending'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ]
    )
    
    # Target user type
    target_user_type = filters.ChoiceFilter(
        choices=[
            ('all', 'All Users'),
            ('active', 'Active Users'),
            ('inactive', 'Inactive Users'),
            ('providers', 'Providers'),
            ('customers', 'Customers'),
        ]
    )
    
    # Creator filter
    created_by = filters.ModelChoiceFilter(
        queryset=User.objects.all()
    )
    
    created_by_email = filters.CharFilter(
        field_name='created_by__email',
        lookup_expr='icontains'
    )
    
    # Date filters
    created_after = filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    
    created_before = filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte'
    )
    
    scheduled_after = filters.DateTimeFilter(
        field_name='scheduled_at',
        lookup_expr='gte'
    )
    
    scheduled_before = filters.DateTimeFilter(
        field_name='scheduled_at',
        lookup_expr='lte'
    )
    
    # Channel filters
    send_email = filters.BooleanFilter()
    send_sms = filters.BooleanFilter()
    send_app = filters.BooleanFilter()
    
    # Recipients count filters
    min_recipients = filters.NumberFilter(
        field_name='total_recipients',
        lookup_expr='gte'
    )
    
    max_recipients = filters.NumberFilter(
        field_name='total_recipients',
        lookup_expr='lte'
    )
    
    # Success rate filters
    min_success_rate = filters.NumberFilter(
        method='filter_min_success_rate',
        label='Min Success Rate'
    )
    
    # Status filters
    is_scheduled = filters.BooleanFilter(
        method='filter_is_scheduled',
        label='Is Scheduled'
    )
    
    is_active = filters.BooleanFilter(
        method='filter_is_active',
        label='Is Active'
    )
    
    # Time-based filters
    today = filters.BooleanFilter(
        method='filter_today',
        label='Today'
    )
    
    this_week = filters.BooleanFilter(
        method='filter_this_week',
        label='This Week'
    )
    
    class Meta:
        model = BulkNotification
        fields = [
            'status', 'target_user_type', 'created_by', 'send_email',
            'send_sms', 'send_app', 'total_recipients'
        ]
    
    def filter_min_success_rate(self, queryset, name, value):
        """Filter by minimum success rate"""
        if value is not None:
            return queryset.extra(
                where=[
                    "CASE WHEN total_recipients > 0 THEN (sent_count * 100.0 / total_recipients) ELSE 0 END >= %s"
                ],
                params=[value]
            )
        return queryset
    
    def filter_is_scheduled(self, queryset, name, value):
        """Filter scheduled notifications"""
        if value:
            return queryset.filter(
                scheduled_at__isnull=False,
                scheduled_at__gt=timezone.now()
            )
        return queryset.filter(
            models.Q(scheduled_at__isnull=True) | models.Q(scheduled_at__lte=timezone.now())
        )
    
    def filter_is_active(self, queryset, name, value):
        """Filter active bulk notifications"""
        if value:
            return queryset.filter(status__in=['draft', 'scheduled', 'sending'])
        return queryset.filter(status__in=['completed', 'failed', 'cancelled'])
    
    def filter_today(self, queryset, name, value):
        """Filter bulk notifications from today"""
        if value:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today)
        return queryset
    
    def filter_this_week(self, queryset, name, value):
        """Filter bulk notifications from this week"""
        if value:
            week_ago = timezone.now() - timezone.timedelta(days=7)
            return queryset.filter(created_at__gte=week_ago)
        return queryset


class NotificationPreferenceFilter(filters.FilterSet):
    """Filter for notification preferences"""
    
    # User filter
    user = filters.ModelChoiceFilter(
        queryset=User.objects.all()
    )
    
    user_email = filters.CharFilter(
        field_name='user__email',
        lookup_expr='icontains'
    )
    
    # Email preferences
    email_notifications_enabled = filters.BooleanFilter(
        method='filter_email_notifications_enabled',
        label='Email Notifications Enabled'
    )
    
    # SMS preferences
    sms_notifications_enabled = filters.BooleanFilter(
        method='filter_sms_notifications_enabled',
        label='SMS Notifications Enabled'
    )
    
    # App preferences
    app_notifications_enabled = filters.BooleanFilter(
        method='filter_app_notifications_enabled',
        label='App Notifications Enabled'
    )
    
    # Marketing preferences
    marketing_enabled = filters.BooleanFilter(
        method='filter_marketing_enabled',
        label='Marketing Enabled'
    )
    
    # Digest frequency
    digest_frequency = filters.ChoiceFilter(
        choices=[
            ('instant', 'Instant'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('never', 'Never'),
        ]
    )
    
    # Quiet hours
    has_quiet_hours = filters.BooleanFilter(
        method='filter_has_quiet_hours',
        label='Has Quiet Hours'
    )
    
    class Meta:
        model = NotificationPreference
        fields = ['user', 'digest_frequency']
    
    def filter_email_notifications_enabled(self, queryset, name, value):
        """Filter users with email notifications enabled"""
        if value:
            return queryset.filter(
                models.Q(email_lead_notifications=True) |
                models.Q(email_subscription_notifications=True) |
                models.Q(email_package_notifications=True) |
                models.Q(email_review_notifications=True)
            )
        return queryset.filter(
            email_lead_notifications=False,
            email_subscription_notifications=False,
            email_package_notifications=False,
            email_review_notifications=False
        )
    
    def filter_sms_notifications_enabled(self, queryset, name, value):
        """Filter users with SMS notifications enabled"""
        if value:
            return queryset.filter(
                models.Q(sms_lead_notifications=True) |
                models.Q(sms_subscription_notifications=True) |
                models.Q(sms_package_notifications=True) |
                models.Q(sms_review_notifications=True)
            )
        return queryset.filter(
            sms_lead_notifications=False,
            sms_subscription_notifications=False,
            sms_package_notifications=False,
            sms_review_notifications=False
        )
    
    def filter_app_notifications_enabled(self, queryset, name, value):
        """Filter users with app notifications enabled"""
        if value:
            return queryset.filter(
                models.Q(app_lead_notifications=True) |
                models.Q(app_subscription_notifications=True) |
                models.Q(app_package_notifications=True) |
                models.Q(app_review_notifications=True)
            )
        return queryset.filter(
            app_lead_notifications=False,
            app_subscription_notifications=False,
            app_package_notifications=False,
            app_review_notifications=False
        )
    
    def filter_marketing_enabled(self, queryset, name, value):
        """Filter users with marketing enabled"""
        if value:
            return queryset.filter(
                models.Q(email_marketing=True) |
                models.Q(sms_marketing=True) |
                models.Q(app_marketing=True)
            )
        return queryset.filter(
            email_marketing=False,
            sms_marketing=False,
            app_marketing=False
        )
    
    def filter_has_quiet_hours(self, queryset, name, value):
        """Filter users with quiet hours configured"""
        if value:
            return queryset.filter(
                quiet_hours_start__isnull=False,
                quiet_hours_end__isnull=False
            )
        return queryset.filter(
            models.Q(quiet_hours_start__isnull=True) |
            models.Q(quiet_hours_end__isnull=True)
        )