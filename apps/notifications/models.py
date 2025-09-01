from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.conf import settings


User = get_user_model()


class Notification(models.Model):
    """Individual notification instance"""
    
    NOTIFICATION_TYPES = [
        ('lead_received', 'Lead Received'),
        ('subscription_expiry', 'Subscription Expiry'),
        ('package_approved', 'Package Approved'),
        ('package_rejected', 'Package Rejected'),
        ('services_approved','Service Approved'),
        ('services_rejected', 'Service Rejected'),
        ('new_review', 'New Review'),
        ('payment_success', 'Payment Success'),
        ('payment_failed', 'Payment Failed'),
        ('subscription_reminder', 'Subscription Reminder'),
        ('package_upload_reminder', 'Package Upload Reminder'),
        ('verification_complete', 'Verification Complete'),
        ('welcome', 'Welcome'),
        ('password_reset', 'Password Reset'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='lead_received')
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Generic foreign key for related objects
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Template data for rendering
    data = models.JSONField(default=dict, blank=True)
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # Channel settings - determined by user preferences and notification type
    send_email = models.BooleanField(default=True)
    send_sms = models.BooleanField(default=False)
    send_app = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Delivery tracking
    email_sent = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    app_sent = models.BooleanField(default=False)
    
    # Retry mechanism
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['notification_type', 'status']),
            models.Index(fields=['status', 'next_retry_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.recipient.email}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if self.status != 'read':
            self.status = 'read'
            self.read_at = timezone.now()
            self.save(update_fields=['status', 'read_at'])
    
    def mark_as_sent(self):
        """Mark notification as sent"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])
    
    def mark_as_failed(self):
        """Mark notification as failed"""
        self.status = 'failed'
        self.save(update_fields=['status'])
    
    def can_retry(self):
        """Check if notification can be retried"""
        return self.retry_count < self.max_retries and self.status == 'failed'
    
    def increment_retry(self):
        """Increment retry count and schedule next retry"""
        self.retry_count += 1
        if self.retry_count >= self.max_retries:
            self.status = 'failed'
            self.next_retry_at = None
        else:
            # Schedule next retry (exponential backoff: 5 min, 15 min, 45 min)
            delay_minutes = 5 * (3 ** (self.retry_count - 1))
            self.next_retry_at = timezone.now() + timezone.timedelta(minutes=delay_minutes)
        self.save(update_fields=['retry_count', 'status', 'next_retry_at'])


class NotificationPreference(models.Model):
    """User notification preferences"""
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    
    # Email preferences
    email_lead_notifications = models.BooleanField(default=True)
    email_subscription_notifications = models.BooleanField(default=True)
    email_package_notifications = models.BooleanField(default=True)
    email_services_notifications = models.BooleanField(default=True)
    email_review_notifications = models.BooleanField(default=True)
    email_pay_notifications = models.BooleanField(default=True)
    email_verification_notifications = models.BooleanField(default=True)
    email_marketing = models.BooleanField(default=False)
    
    # SMS preferences
    sms_lead_notifications = models.BooleanField(default=True)
    sms_subscription_notifications = models.BooleanField(default=True)
    sms_package_notifications = models.BooleanField(default=False)
    sms_services_notifications = models.BooleanField(default=False)
    sms_review_notifications = models.BooleanField(default=False)
    sms_payment_notifications = models.BooleanField(default=True)
    sms_verification_notifications = models.BooleanField(default=False)
    sms_marketing = models.BooleanField(default=False)
    
    # App preferences
    app_lead_notifications = models.BooleanField(default=True)
    app_subscription_notifications = models.BooleanField(default=True)
    app_package_notifications = models.BooleanField(default=True)
    app_services_notifications = models.BooleanField(default=True)
    app_review_notifications = models.BooleanField(default=True)
    app_payment_notifications = models.BooleanField(default=True)
    app_verification_notifications = models.BooleanField(default=True)
    app_marketing = models.BooleanField(default=False)
    
    # Frequency settings
    digest_frequency = models.CharField(
        max_length=20,
        choices=[
            ('immediate', 'Immediate'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        default='immediate'
    )
    
    # Quiet hours
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_preferences'
    
    def __str__(self):
        return f"Preferences for {self.user.email}"
    
    def get_channel_preference(self, notification_type, channel):
        """Get user preference for specific notification type and channel"""
        preference_map = {
            'lead_received': {
                'email': self.email_lead_notifications,
                'sms': self.sms_lead_notifications,
                'app': self.app_lead_notifications,
            },
            'subscription_expiry': {
                'email': self.email_subscription_notifications,
                'sms': self.sms_subscription_notifications,
                'app': self.app_subscription_notifications,
            },
            'subscription_reminder': {
                'email': self.email_subscription_notifications,
                'sms': self.sms_subscription_notifications,
                'app': self.app_subscription_notifications,
            },
            'package_approved': {
                'email': self.email_package_notifications,
                'sms': self.sms_package_notifications,
                'app': self.app_package_notifications,
            },
            'package_rejected': {
                'email': self.email_package_notifications,
                'sms': self.sms_package_notifications,
                'app': self.app_package_notifications,
            },
            'services_approved': {
                'email': self.email_services_notifications,
                'sms': self.sms_services_notifications,
                'app': self.app_services_notifications,
            },
            'services_rejected': {
                'email': self.email_services_notifications,
                'sms': self.sms_services_notifications,
                'app': self.app_services_notifications,
            },
            'services_upload_reminder': {
                'email': self.email_package_notifications,
                'sms': self.sms_package_notifications,
                'app': self.app_package_notifications,
            },
            'new_review': {
                'email': self.email_review_notifications,
                'sms': self.sms_review_notifications,
                'app': self.app_review_notifications,
            },
            'payment_success': {
                'email': self.email_pay_notifications,
                'sms': self.sms_payment_notifications,
                'app': self.app_payment_notifications,
            },
            'payment_failed': {
                'email': self.email_pay_notifications,
                'sms': self.sms_payment_notifications,
                'app': self.app_payment_notifications,
            },
            'verification_complete': {
                'email': self.email_verification_notifications,
                'sms': self.sms_verification_notifications,
                'app': self.app_verification_notifications,
            },
            'welcome': {
                'email': True,  # Welcome emails are always sent
                'sms': False,
                'app': True,
            },
            'password_reset': {
                'email': True,  # Password reset emails are always sent
                'sms': False,
                'app': False,
            },
        }
        
        return preference_map.get(notification_type, {}).get(channel, False)


class NotificationLog(models.Model):
    """Log of all notification attempts"""
    
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('app', 'App'),
    ]
    
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='logs')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    
    # Delivery details
    sent_at = models.DateTimeField(auto_now_add=True)
    delivered = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Provider details
    provider = models.CharField(max_length=100, blank=True)  # e.g., 'twilio', 'smtp'
    provider_response = models.JSONField(default=dict, blank=True)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    
    class Meta:
        db_table = 'notification_logs'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['notification', 'channel']),
            models.Index(fields=['sent_at']),
        ]
    
    def __str__(self):
        return f"{self.notification.title} - {self.channel} - {self.sent_at}"


class BulkNotification(models.Model):
    """For bulk notification campaigns"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=Notification.NOTIFICATION_TYPES,default='lead_received')
    
    # Targeting
    target_user_type = models.CharField(
        max_length=20,
        choices=[
            ('all', 'All Users'),
            ('pilgrim', 'Pilgrims'),
            ('provider', 'Service Providers'),
        ],
        default='all'
    )
    
    # Filters for targeting
    target_filters = models.JSONField(default=dict, blank=True)
    
    # Channels
    send_email = models.BooleanField(default=True)
    send_sms = models.BooleanField(default=False)
    send_app = models.BooleanField(default=True)
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Stats
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    
    # Metadata
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'bulk_notifications'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.status}"