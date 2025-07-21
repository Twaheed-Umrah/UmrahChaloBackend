from rest_framework import serializers
from django.utils import timezone
from .models import PaymentMethod, Payment, PaymentRefund, PaymentTransaction, PaymentWebhook
from apps.subscriptions.models import Subscription

class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment methods"""
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'name', 'type', 'is_active', 
            'processing_fee_percentage', 'processing_fee_fixed'
        ]
        read_only_fields = ['id']

class PaymentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payments"""
    
    class Meta:
        model = Payment
        fields = [
            'subscription', 'payment_method', 'amount', 
            'currency', 'purpose', 'description', 'metadata'
        ]
    
    def validate_amount(self, value):
        """Validate payment amount"""
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than 0")
        return value
    
    def validate_subscription(self, value):
        """Validate subscription belongs to user"""
        request = self.context.get('request')
        if request and value.user != request.user:
            raise serializers.ValidationError("You can only pay for your own subscriptions")
        return value
    
    def create(self, validated_data):
        """Create payment with calculated fees"""
        request = self.context.get('request')
        payment_method = validated_data['payment_method']
        
        # Calculate processing fee
        amount = validated_data['amount']
        processing_fee = (amount * payment_method.processing_fee_percentage / 100) + payment_method.processing_fee_fixed
        total_amount = amount + processing_fee
        
        # Create payment
        payment = Payment.objects.create(
            user=request.user,
            processing_fee=processing_fee,
            total_amount=total_amount,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            **validated_data
        )
        
        return payment

class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payment details"""
    payment_method = PaymentMethodSerializer(read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    subscription_plan = serializers.CharField(source='subscription.plan.name', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'user_email', 'subscription', 'subscription_plan',
            'payment_method', 'amount', 'currency', 'processing_fee',
            'total_amount', 'gateway_payment_id', 'gateway_order_id',
            'status', 'purpose', 'description', 'initiated_at',
            'completed_at', 'failed_at', 'metadata'
        ]
        read_only_fields = [
            'id', 'user_email', 'subscription_plan', 'processing_fee',
            'total_amount', 'gateway_payment_id', 'gateway_order_id',
            'status', 'initiated_at', 'completed_at', 'failed_at'
        ]

class PaymentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating payment status"""
    
    class Meta:
        model = Payment
        fields = [
            'gateway_payment_id', 'gateway_order_id', 'gateway_signature',
            'gateway_response', 'status', 'completed_at', 'failed_at'
        ]
    
    def update(self, instance, validated_data):
        """Update payment status with timestamp"""
        status = validated_data.get('status')
        
        if status == 'completed' and not instance.completed_at:
            validated_data['completed_at'] = timezone.now()
        elif status in ['failed', 'cancelled'] and not instance.failed_at:
            validated_data['failed_at'] = timezone.now()
        
        return super().update(instance, validated_data)

class PaymentRefundCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating refund requests"""
    
    class Meta:
        model = PaymentRefund
        fields = ['payment', 'amount', 'reason', 'description']
    
    def validate_payment(self, value):
        """Validate payment can be refunded"""
        request = self.context.get('request')
        
        # Check if user owns the payment
        if value.user != request.user:
            raise serializers.ValidationError("You can only request refunds for your own payments")
        
        # Check if payment is completed
        if value.status != 'completed':
            raise serializers.ValidationError("Only completed payments can be refunded")
        
        return value
    
    def validate_amount(self, value):
        """Validate refund amount"""
        if value <= 0:
            raise serializers.ValidationError("Refund amount must be greater than 0")
        return value
    
    def validate(self, data):
        """Validate refund amount doesn't exceed payment amount"""
        payment = data['payment']
        amount = data['amount']
        
        # Calculate already refunded amount
        already_refunded = payment.refunds.filter(
            status__in=['completed', 'approved', 'processing']
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        if amount > (payment.amount - already_refunded):
            raise serializers.ValidationError("Refund amount exceeds available refund amount")
        
        return data

class PaymentRefundSerializer(serializers.ModelSerializer):
    """Serializer for refund details"""
    payment_id = serializers.UUIDField(source='payment.id', read_only=True)
    user_email = serializers.EmailField(source='payment.user.email', read_only=True)
    approved_by_email = serializers.EmailField(source='approved_by.email', read_only=True)
    
    class Meta:
        model = PaymentRefund
        fields = [
            'id', 'payment_id', 'user_email', 'amount', 'reason',
            'description', 'status', 'gateway_refund_id', 'approved_by_email',
            'approved_at', 'rejected_reason', 'requested_at',
            'processed_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'payment_id', 'user_email', 'gateway_refund_id',
            'approved_by_email', 'approved_at', 'requested_at',
            'processed_at', 'completed_at'
        ]

class PaymentRefundUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating refund status"""
    
    class Meta:
        model = PaymentRefund
        fields = [
            'status', 'approved_by', 'approved_at', 'rejected_reason',
            'gateway_refund_id', 'gateway_response', 'processed_at', 'completed_at'
        ]
    
    def update(self, instance, validated_data):
        """Update refund with appropriate timestamps"""
        status = validated_data.get('status')
        request = self.context.get('request')
        
        if status == 'approved' and not instance.approved_at:
            validated_data['approved_at'] = timezone.now()
            validated_data['approved_by'] = request.user
        elif status == 'processing' and not instance.processed_at:
            validated_data['processed_at'] = timezone.now()
        elif status == 'completed' and not instance.completed_at:
            validated_data['completed_at'] = timezone.now()
        
        return super().update(instance, validated_data)

class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Serializer for payment transactions"""
    payment_id = serializers.UUIDField(source='payment.id', read_only=True)
    
    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'payment_id', 'transaction_type', 'amount',
            'currency', 'gateway_transaction_id', 'status',
            'description', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'payment_id', 'created_at']

class PaymentWebhookSerializer(serializers.ModelSerializer):
    """Serializer for payment webhooks"""
    
    class Meta:
        model = PaymentWebhook
        fields = [
            'id', 'payment_method', 'event_type', 'gateway_event_id',
            'payload', 'headers', 'status', 'processed_at',
            'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class PaymentAnalyticsSerializer(serializers.Serializer):
    """Serializer for payment analytics"""
    total_payments = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    successful_payments = serializers.IntegerField()
    failed_payments = serializers.IntegerField()
    refund_requests = serializers.IntegerField()
    total_refunded = serializers.DecimalField(max_digits=15, decimal_places=2)
    
    # Monthly breakdown
    monthly_data = serializers.ListField(
        child=serializers.DictField(), 
        read_only=True
    )
    
    # Payment method breakdown
    payment_method_stats = serializers.ListField(
        child=serializers.DictField(), 
        read_only=True
    )

class PaymentDashboardSerializer(serializers.Serializer):
    """Serializer for payment dashboard data"""
    recent_payments = PaymentSerializer(many=True, read_only=True)
    pending_refunds = PaymentRefundSerializer(many=True, read_only=True)
    analytics = PaymentAnalyticsSerializer(read_only=True)
    
    # Quick stats
    today_payments = serializers.IntegerField()
    today_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    this_month_payments = serializers.IntegerField()
    this_month_amount = serializers.DecimalField(max_digits=15, decimal_places=2)