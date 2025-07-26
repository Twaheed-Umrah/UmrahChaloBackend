from django.db import models
from django.contrib.auth import get_user_model
from apps.subscriptions.models import Subscription
from django.conf import settings

User = get_user_model()

class PaymentMethod(models.Model):
    """Payment methods available on the platform"""
    PAYMENT_TYPES = (
        ('razorpay', 'Razorpay'),
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('upi', 'UPI'),
        ('wallet', 'Wallet'),
    )
    
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    is_active = models.BooleanField(default=True)
    gateway_config = models.JSONField(default=dict, blank=True)
    processing_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    processing_fee_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_methods'
        verbose_name = 'Payment Method'
        verbose_name_plural = 'Payment Methods'
    
    def __str__(self):
        return f"{self.name} ({self.type})"

class Payment(models.Model):
    """Payment transactions for subscriptions"""
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded'),
    )
    
    PAYMENT_PURPOSE = (
        ('subscription', 'Subscription'),
        ('renewal', 'Renewal'),
        ('upgrade', 'Upgrade'),
        ('addon', 'Add-on'),
    )
    
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment gateway details
    gateway_payment_id = models.CharField(max_length=255, blank=True, null=True)
    gateway_order_id = models.CharField(max_length=255, blank=True, null=True)
    gateway_signature = models.CharField(max_length=255, blank=True, null=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Payment status and tracking
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    purpose = models.CharField(max_length=20, choices=PAYMENT_PURPOSE, default='subscription')
    description = models.TextField(blank=True)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['gateway_payment_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Payment {self.id} - {self.user.email} - {self.amount}"
    
    @property
    def is_successful(self):
        return self.status == 'completed'
    
    @property
    def is_failed(self):
        return self.status in ['failed', 'cancelled']
    
    @property
    def is_refunded(self):
        return self.status in ['refunded', 'partially_refunded']

class PaymentRefund(models.Model):
    """Refund requests and transactions"""
    REFUND_STATUS = (
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )
    
    REFUND_REASON = (
        ('user_request', 'User Request'),
        ('service_issue', 'Service Issue'),
        ('technical_issue', 'Technical Issue'),
        ('duplicate_payment', 'Duplicate Payment'),
        ('admin_action', 'Admin Action'),
    )
    
    id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    
    # Refund details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REFUND_REASON)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=REFUND_STATUS, default='requested')
    
    # Gateway details
    gateway_refund_id = models.CharField(max_length=255, blank=True, null=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Approval details
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_refunds')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    
    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_refunds'
        verbose_name = 'Payment Refund'
        verbose_name_plural = 'Payment Refunds'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Refund {self.id} - {self.payment.user.email} - {self.amount}"

class PaymentTransaction(models.Model):
    """Payment transaction log for audit trail"""
    TRANSACTION_TYPE = (
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('partial_refund', 'Partial Refund'),
        ('chargeback', 'Chargeback'),
        ('fee', 'Fee'),
    )
    
    id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='transactions')
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    
    # Gateway details
    gateway_transaction_id = models.CharField(max_length=255, blank=True, null=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Status and metadata
    status = models.CharField(max_length=20, default='pending')
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_transactions'
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Transaction {self.id} - {self.transaction_type} - {self.amount}"

class PaymentWebhook(models.Model):
    """Store webhook events from payment gateways"""
    WEBHOOK_STATUS = (
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('ignored', 'Ignored'),
    )
    
    id = models.AutoField(primary_key=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    
    # Webhook details
    event_type = models.CharField(max_length=100)
    gateway_event_id = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()
    headers = models.JSONField(default=dict, blank=True)
    
    # Processing details
    status = models.CharField(max_length=20, choices=WEBHOOK_STATUS, default='received')
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_webhooks'
        verbose_name = 'Payment Webhook'
        verbose_name_plural = 'Payment Webhooks'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Webhook {self.gateway_event_id} - {self.event_type}"