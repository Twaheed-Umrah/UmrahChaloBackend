from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.conf import settings


class NotificationTemplate(models.Model):
    """Template for different types of notifications"""
    
    NOTIFICATION_TYPES = [
        ('lead_received', 'Lead Received'),
        ('subscription_expiry', 'Subscription Expiry'),
        ('package_approved', 'Package Approved'),
        ('package_rejected', 'Package Rejected'),
        ('new_review', 'New Review'),
        ('payment_success', 'Payment Success'),
        ('payment_failed', 'Payment Failed'),
        ('subscription_reminder', 'Subscription Reminder'),
        ('package_upload_reminder', 'Package Upload Reminder'),
        ('verification_complete', 'Verification Complete'),
        ('welcome', 'Welcome'),
        ('password_reset', 'Password Reset'),
    ]
    
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, unique=True)
    title = models.CharField(max_length=200)
    
    # Templates for different channels
    email_subject = models.CharField(max_length=200, blank=True)
    email_body = models.TextField(blank=True)
    sms_body = models.TextField(blank=True)
    app_body = models.TextField(blank=True)
    
    # Channel settings
    send_email = models.BooleanField(default=True)
    send_sms = models.BooleanField(default=False)
    send_app = models.BooleanField(default=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_templates'
        ordering = ['notification_type']
    
    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.title}"


class Notification(models.Model):
    """Individual notification instance"""
    
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
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE)
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Generic foreign key for related objects
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Metadata
    data = models.JSONField(default=dict, blank=True)  # Additional data for template rendering
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
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
            models.Index(fields=['template', 'status']),
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
    
    def can_retry(self):
        """Check if notification can be retried"""
        return self.retry_count < self.max_retries and self.status == 'failed'
    
    def increment_retry(self):
        """Increment retry count"""
        self.retry_count += 1
        if self.retry_count >= self.max_retries:
            self.status = 'failed'
        self.save(update_fields=['retry_count', 'status'])


class NotificationPreference(models.Model):
    """User notification preferences"""
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    
    # Email preferences
    email_lead_notifications = models.BooleanField(default=True)
    email_subscription_notifications = models.BooleanField(default=True)
    email_package_notifications = models.BooleanField(default=True)
    email_review_notifications = models.BooleanField(default=True)
    email_marketing = models.BooleanField(default=False)
    
    # SMS preferences
    sms_lead_notifications = models.BooleanField(default=True)
    sms_subscription_notifications = models.BooleanField(default=True)
    sms_package_notifications = models.BooleanField(default=False)
    sms_review_notifications = models.BooleanField(default=False)
    sms_marketing = models.BooleanField(default=False)
    
    # App preferences
    app_lead_notifications = models.BooleanField(default=True)
    app_subscription_notifications = models.BooleanField(default=True)
    app_package_notifications = models.BooleanField(default=True)
    app_review_notifications = models.BooleanField(default=True)
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
    
    # Targeting
    target_user_type = models.CharField(
        max_length=20,
        choices=[
            ('all', 'All Users'),
            ('pilgrims', 'Pilgrims'),
            ('providers', 'Service Providers'),
            ('premium_providers', 'Premium Providers'),
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