from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

User = get_user_model()

class SubscriptionPlan(models.Model):
    """Different subscription tiers for service providers"""
    
    PLAN_TYPES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
    ]
    
    DURATION_CHOICES = [
        (1, '1 Month'),
        (3, '3 Months'),
        (6, '6 Months'),
        (12, '12 Months'),
    ]
    
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    duration_months = models.IntegerField(choices=DURATION_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Features
    can_upload_packages = models.BooleanField(default=True)
    priority_listing = models.BooleanField(default=False)
    badge_display = models.BooleanField(default=False)
    lead_notifications = models.BooleanField(default=True)
    analytics_access = models.BooleanField(default=False)
    max_packages = models.IntegerField(default=10)
    
    # Plan details
    description = models.TextField(blank=True)
    features = models.JSONField(default=list)  # Store list of features
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscription_plans'
        ordering = ['price']
        unique_together = ['plan_type', 'duration_months']
    
    def __str__(self):
        return f"{self.name} - {self.duration_months} months"


class Subscription(models.Model):
    """User subscription records"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('pending', 'Pending Payment'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    
    # Subscription period
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    
    # Status and payment
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_id = models.CharField(max_length=100, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Auto-renewal
    auto_renew = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.plan.name}"
    
    @property
    def is_active(self):
        """Check if subscription is currently active"""
        return (
            self.status == 'active' and 
            self.start_date <= timezone.now() <= self.end_date
        )
    
    @property
    def days_remaining(self):
        """Calculate days remaining in subscription"""
        if self.is_active:
            return (self.end_date - timezone.now()).days
        return 0
    
    @property
    def is_expired(self):
        """Check if subscription has expired"""
        return timezone.now() > self.end_date
    
    def extend_subscription(self, months):
        """Extend subscription by given months"""
        if self.is_active:
            self.end_date += timedelta(days=30 * months)
        else:
            self.start_date = timezone.now()
            self.end_date = timezone.now() + timedelta(days=30 * months)
        self.save()
    
    def cancel_subscription(self):
        """Cancel the subscription"""
        self.status = 'cancelled'
        self.auto_renew = False
        self.save()


class SubscriptionHistory(models.Model):
    """Track subscription changes and renewals"""
    
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('renewed', 'Renewed'),
        ('upgraded', 'Upgraded'),
        ('downgraded', 'Downgraded'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    previous_plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='previous_subscriptions'
    )
    new_plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='new_subscriptions'
    )
    
    # Additional details
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'subscription_history'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subscription.user.email} - {self.action}"


class SubscriptionFeature(models.Model):
    """Track feature usage for subscriptions"""
    
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='feature_usage')
    feature_name = models.CharField(max_length=100)  # e.g., 'packages_uploaded', 'leads_received'
    usage_count = models.IntegerField(default=0)
    limit = models.IntegerField(null=True, blank=True)  # null means unlimited
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscription_features'
        unique_together = ['subscription', 'feature_name']
    
    def __str__(self):
        return f"{self.subscription.user.email} - {self.feature_name}: {self.usage_count}"
    
    @property
    def is_limit_reached(self):
        """Check if usage limit is reached"""
        if self.limit is None:
            return False
        return self.usage_count >= self.limit
    
    def increment_usage(self):
        """Increment usage count"""
        self.usage_count += 1
        self.save()


class SubscriptionAlert(models.Model):
    """Alerts for subscription-related events"""
    
    ALERT_TYPES = [
        ('renewal_reminder', 'Renewal Reminder'),
        ('expiry_warning', 'Expiry Warning'),
        ('plan_upgrade', 'Plan Upgrade Available'),
        ('payment_failed', 'Payment Failed'),
        ('feature_limit', 'Feature Limit Reached'),
    ]
    
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    message = models.TextField()
    
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'subscription_alerts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subscription.user.email} - {self.alert_type}"
    
    def mark_as_sent(self):
        """Mark alert as sent"""
        self.is_sent = True
        self.sent_at = timezone.now()
        self.save()