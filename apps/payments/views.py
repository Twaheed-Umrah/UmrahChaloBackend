from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.db import transaction
from django.conf import settings
import json
import hmac
import hashlib
import logging
from apps.core.pagination import LargeResultsSetPagination
from apps.core.permissions import IsOwnerOrReadOnly
from .models import PaymentMethod, Payment, PaymentRefund, PaymentTransaction, PaymentWebhook
from .serializers import (
    PaymentMethodSerializer, PaymentCreateSerializer, PaymentSerializer,
    PaymentUpdateSerializer, PaymentRefundCreateSerializer, PaymentRefundSerializer,
    PaymentRefundUpdateSerializer, PaymentTransactionSerializer,
    PaymentWebhookSerializer, PaymentAnalyticsSerializer, PaymentDashboardSerializer
)
from apps.subscriptions.models import SubscriptionPlan,Subscription,SubscriptionHistory,SubscriptionFeature,SubscriptionAlert
from .utils import PaymentGatewayManager
import logging

logger = logging.getLogger(__name__)

class PaymentMethodListView(generics.ListAPIView):
    """List all active payment methods"""
    serializer_class = PaymentMethodSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        return PaymentMethod.objects.filter(is_active=True)

class PaymentCreateView(generics.CreateAPIView):
    """Create a new payment"""
    serializer_class = PaymentCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        payment = serializer.save()
        
        # Initialize payment with gateway
        gateway_manager = PaymentGatewayManager(payment.payment_method)
        try:
            gateway_order = gateway_manager.create_order(payment)
            payment.gateway_order_id = gateway_order.get('id')
            payment.save()
            
            # Return order details in response
            self.gateway_order = gateway_order
        except Exception as e:
            logger.error(f"Error creating payment order: {str(e)}")
            payment.status = 'failed'
            payment.failed_at = timezone.now()
            payment.save()
            raise
    
    def create(self, request, *args, **kwargs):
        """Override create to return gateway order details"""
        response = super().create(request, *args, **kwargs)
        
        if hasattr(self, 'gateway_order'):
            response.data['gateway_order'] = self.gateway_order
            response.data['razorpay_key'] = settings.RAZORPAY_KEY_ID or 'rzp_test_ZI5G0k0dQJfr79'
        
        return response

class PaymentListView(generics.ListAPIView):
    """List user's payments"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        queryset = Payment.objects.filter(user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by purpose
        purpose_filter = self.request.query_params.get('purpose')
        if purpose_filter:
            queryset = queryset.filter(purpose=purpose_filter)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__gte=start_date)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__lte=end_date)
            except ValueError:
                pass
        
        return queryset.select_related('payment_method', 'subscription').order_by('-created_at')


class PaymentDetailView(generics.RetrieveAPIView):
    """Retrieve payment details"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).select_related('payment_method', 'subscription')


class PaymentUpdateView(generics.UpdateAPIView):
    """Update payment status (for gateway callbacks)"""
    serializer_class = PaymentUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)
    
    def perform_update(self, serializer):
        payment = serializer.save()
        
        # If payment is completed, activate subscription
        if payment.status == 'completed' and payment.subscription:
            payment.subscription.activate()
            logger.info(f"Subscription {payment.subscription.id} activated for payment {payment.id}")

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verify_payment(request, payment_id):
    """
    Verify payment with gateway and update subscription status
    """
    try:
        # Get payment object
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        
        # Check if payment is already processed
        if payment.status in ['completed', 'failed', 'cancelled']:
            return Response({
                'success': False,
                'message': f'Payment already {payment.status}',
                'payment': PaymentSerializer(payment).data
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Initialize gateway manager
        gateway_manager = PaymentGatewayManager(payment.payment_method)
        
        # Verify payment with gateway
        verification_result = gateway_manager.verify_payment(
            payment_id=request.data.get('razorpay_payment_id'),
            order_id=request.data.get('razorpay_order_id'),
            signature=request.data.get('razorpay_signature')
        )
        
        # Use database transaction for consistency
        with transaction.atomic():
            if verification_result['success']:
                # Update payment status
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.gateway_payment_id = verification_result.get('payment_id')
                payment.gateway_signature = verification_result.get('signature')
                payment.gateway_response = verification_result
                payment.save()
                
                # Create payment transaction record
                PaymentTransaction.objects.create(
                    payment=payment,
                    transaction_type='payment',
                    amount=payment.total_amount,
                    currency=payment.currency,
                    gateway_transaction_id=verification_result.get('payment_id'),
                    gateway_response=verification_result,
                    status='completed',
                    description=f'Payment verification successful for {payment.purpose}'
                )
                
                # Handle subscription activation/creation
                subscription_result = handle_subscription_update(payment, request.user)
                
                logger.info(f"Payment {payment.id} verified successfully for user {request.user.email}")
                
                return Response({
                    'success': True,
                    'message': 'Payment verified successfully',
                    'payment': PaymentSerializer(payment).data,
                    'subscription': subscription_result
                }, status=status.HTTP_200_OK)
            
            else:
                # Payment verification failed
                payment.status = 'failed'
                payment.failed_at = timezone.now()
                payment.gateway_response = verification_result
                payment.save()
                
                # Create failed transaction record
                PaymentTransaction.objects.create(
                    payment=payment,
                    transaction_type='payment',
                    amount=payment.total_amount,
                    currency=payment.currency,
                    gateway_transaction_id=request.data.get('razorpay_payment_id'),
                    gateway_response=verification_result,
                    status='failed',
                    description=f'Payment verification failed: {verification_result.get("message", "Unknown error")}'
                )
                
                logger.warning(f"Payment {payment.id} verification failed for user {request.user.email}")
                
                return Response({
                    'success': False,
                    'message': verification_result.get('message', 'Payment verification failed'),
                    'payment': PaymentSerializer(payment).data
                }, status=status.HTTP_400_BAD_REQUEST)
            
    except Payment.DoesNotExist:
        logger.error(f"Payment {payment_id} not found for user {request.user.email}")
        return Response({
            'success': False,
            'message': 'Payment not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Payment verification error for payment {payment_id}: {str(e)}")
        return Response({
            'success': False,
            'message': 'Payment verification failed due to system error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def handle_subscription_update(payment, user):
    """
    Handle subscription creation/update based on payment purpose
    """
    try:
        if payment.purpose == 'subscription':
            # Create new subscription
            return create_new_subscription(payment, user)
        
        elif payment.purpose == 'renewal':
            # Renew existing subscription
            return renew_subscription(payment, user)
        
        elif payment.purpose == 'upgrade':
            # Upgrade existing subscription
            return upgrade_subscription(payment, user)
        
        elif payment.purpose == 'addon':
            # Handle add-on purchase
            return handle_addon_purchase(payment, user)
        
        else:
            logger.warning(f"Unknown payment purpose: {payment.purpose}")
            return {'message': 'Payment processed but subscription not updated'}
    
    except Exception as e:
        logger.error(f"Subscription update error: {str(e)}")
        raise


def create_new_subscription(payment, user):
    """Create new subscription from payment"""
    # Get subscription plan from payment metadata or related subscription
    if payment.subscription and payment.subscription.plan:
        plan = payment.subscription.plan
    else:
        # Try to get plan from payment metadata
        plan_id = payment.metadata.get('plan_id')
        if not plan_id:
            raise ValueError("No subscription plan found in payment")
        plan = SubscriptionPlan.objects.get(id=plan_id)
    
    # Calculate subscription dates
    start_date = timezone.now()
    end_date = start_date + timedelta(days=30 * plan.duration_months)
    
    # Create or update subscription
    if payment.subscription:
        subscription = payment.subscription
        subscription.start_date = start_date
        subscription.end_date = end_date
        subscription.status = 'active'
        subscription.payment_id = payment.gateway_payment_id
        subscription.amount_paid = payment.total_amount
        subscription.save()
    else:
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            start_date=start_date,
            end_date=end_date,
            status='active',
            payment_id=payment.gateway_payment_id,
            amount_paid=payment.total_amount,
            auto_renew=payment.metadata.get('auto_renew', False)
        )
        
        # Link payment to subscription
        payment.subscription = subscription
        payment.save()
    
    # Create subscription history
    SubscriptionHistory.objects.create(
        subscription=subscription,
        action='created',
        new_plan=plan,
        amount=payment.total_amount,
        notes=f'Subscription created via payment {payment.id}',
        created_by=user
    )
    
    # Initialize subscription features
    initialize_subscription_features(subscription)
    
    # Create welcome alert
    SubscriptionAlert.objects.create(
        subscription=subscription,
        alert_type='plan_upgrade',
        message=f'Welcome! Your {plan.name} subscription is now active until {end_date.strftime("%B %d, %Y")}.'
    )
    
    logger.info(f"New subscription created for user {user.email} with plan {plan.name}")
    
    return {
        'subscription_id': subscription.id,
        'plan_name': plan.name,
        'status': subscription.status,
        'end_date': subscription.end_date.isoformat(),
        'message': 'New subscription activated successfully'
    }


def renew_subscription(payment, user):
    """Renew existing subscription"""
    if not payment.subscription:
        raise ValueError("No subscription found for renewal payment")
    
    subscription = payment.subscription
    plan = subscription.plan
    
    # Extend subscription period
    if subscription.is_active:
        # If still active, extend from current end date
        subscription.end_date += timedelta(days=30 * plan.duration_months)
    else:
        # If expired, start fresh
        subscription.start_date = timezone.now()
        subscription.end_date = timezone.now() + timedelta(days=30 * plan.duration_months)
    
    subscription.status = 'active'
    subscription.payment_id = payment.gateway_payment_id
    subscription.amount_paid = payment.total_amount
    subscription.save()
    
    # Create subscription history
    SubscriptionHistory.objects.create(
        subscription=subscription,
        action='renewed',
        new_plan=plan,
        amount=payment.total_amount,
        notes=f'Subscription renewed via payment {payment.id}',
        created_by=user
    )
    
    # Reset feature usage for new period
    reset_subscription_features(subscription)
    
    logger.info(f"Subscription renewed for user {user.email}")
    
    return {
        'subscription_id': subscription.id,
        'plan_name': plan.name,
        'status': subscription.status,
        'end_date': subscription.end_date.isoformat(),
        'message': 'Subscription renewed successfully'
    }


def upgrade_subscription(payment, user):
    """Upgrade existing subscription to new plan"""
    if not payment.subscription:
        raise ValueError("No subscription found for upgrade payment")
    
    subscription = payment.subscription
    old_plan = subscription.plan
    
    # Get new plan from payment metadata
    new_plan_id = payment.metadata.get('new_plan_id')
    if not new_plan_id:
        raise ValueError("No new plan specified for upgrade")
    
    new_plan = SubscriptionPlan.objects.get(id=new_plan_id)
    
    # Update subscription
    subscription.plan = new_plan
    subscription.status = 'active'
    subscription.payment_id = payment.gateway_payment_id
    subscription.amount_paid = payment.total_amount
    
    # Adjust end date if different plan duration
    remaining_days = subscription.days_remaining
    if remaining_days > 0:
        # Prorate the upgrade
        subscription.end_date = timezone.now() + timedelta(days=30 * new_plan.duration_months)
    
    subscription.save()
    
    # Create subscription history
    SubscriptionHistory.objects.create(
        subscription=subscription,
        action='upgraded',
        previous_plan=old_plan,
        new_plan=new_plan,
        amount=payment.total_amount,
        notes=f'Plan upgraded from {old_plan.name} to {new_plan.name} via payment {payment.id}',
        created_by=user
    )
    
    # Update subscription features for new plan
    update_subscription_features(subscription, new_plan)
    
    logger.info(f"Subscription upgraded for user {user.email} from {old_plan.name} to {new_plan.name}")
    
    return {
        'subscription_id': subscription.id,
        'old_plan': old_plan.name,
        'new_plan': new_plan.name,
        'status': subscription.status,
        'end_date': subscription.end_date.isoformat(),
        'message': f'Subscription upgraded from {old_plan.name} to {new_plan.name}'
    }


def handle_addon_purchase(payment, user):
    """Handle add-on purchase"""
    # Implementation depends on your add-on system
    # This is a placeholder implementation
    
    addon_type = payment.metadata.get('addon_type')
    addon_value = payment.metadata.get('addon_value', 0)
    
    logger.info(f"Add-on purchased: {addon_type} for user {user.email}")
    
    return {
        'addon_type': addon_type,
        'addon_value': addon_value,
        'message': f'Add-on {addon_type} purchased successfully'
    }


def initialize_subscription_features(subscription):
    """Initialize feature usage tracking for new subscription"""
    plan = subscription.plan
    
    # Create feature usage records based on plan
    features = {
        'packages_uploaded': plan.max_packages,
        'leads_received': None,  # Usually unlimited
        'analytics_views': 100 if plan.analytics_access else 0,
    }
    
    for feature_name, limit in features.items():
        SubscriptionFeature.objects.get_or_create(
            subscription=subscription,
            feature_name=feature_name,
            defaults={'limit': limit, 'usage_count': 0}
        )


def reset_subscription_features(subscription):
    """Reset feature usage for subscription renewal"""
    SubscriptionFeature.objects.filter(subscription=subscription).update(usage_count=0)


def update_subscription_features(subscription, new_plan):
    """Update feature limits when subscription is upgraded"""
    features = SubscriptionFeature.objects.filter(subscription=subscription)
    
    for feature in features:
        if feature.feature_name == 'packages_uploaded':
            feature.limit = new_plan.max_packages
        elif feature.feature_name == 'analytics_views':
            feature.limit = 100 if new_plan.analytics_access else 0
        
        feature.save()


# Additional helper functions for payment webhooks
@api_view(['POST'])
def payment_webhook(request):
    """Handle payment gateway webhooks"""
    try:
        # Extract webhook data
        event_type = request.data.get('event')
        payment_data = request.data.get('payload', {})
        
        # Store webhook for audit
        webhook = PaymentWebhook.objects.create(
            payment_method_id=1,  # Adjust based on your logic
            event_type=event_type,
            gateway_event_id=payment_data.get('payment', {}).get('id', ''),
            payload=request.data,
            headers=dict(request.headers)
        )
        
        # Process webhook based on event type
        if event_type == 'payment.captured':
            process_payment_captured(payment_data)
        elif event_type == 'payment.failed':
            process_payment_failed(payment_data)
        
        webhook.status = 'processed'
        webhook.processed_at = timezone.now()
        webhook.save()
        
        return Response({'status': 'ok'})
    
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return Response({'error': 'Webhook processing failed'}, status=500)


def process_payment_captured(payment_data):
    """Process payment captured webhook"""
    gateway_payment_id = payment_data.get('payment', {}).get('id')
    
    try:
        payment = Payment.objects.get(gateway_payment_id=gateway_payment_id)
        if payment.status != 'completed':
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.save()
            
            # Activate subscription if exists
            if payment.subscription:
                payment.subscription.status = 'active'
                payment.subscription.save()
    
    except Payment.DoesNotExist:
        logger.warning(f"Payment not found for gateway ID: {gateway_payment_id}")


def process_payment_failed(payment_data):
    """Process payment failed webhook"""
    gateway_payment_id = payment_data.get('payment', {}).get('id')
    
    try:
        payment = Payment.objects.get(gateway_payment_id=gateway_payment_id)
        payment.status = 'failed'
        payment.failed_at = timezone.now()
        payment.save()
    
    except Payment.DoesNotExist:
        logger.warning(f"Payment not found for gateway ID: {gateway_payment_id}")

class PaymentRefundCreateView(generics.CreateAPIView):
    """Create refund request"""
    serializer_class = PaymentRefundCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

class PaymentRefundListView(generics.ListAPIView):
    """List user's refund requests"""
    serializer_class = PaymentRefundSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        return PaymentRefund.objects.filter(
            payment__user=self.request.user
        ).order_by('-created_at')

class PaymentRefundDetailView(generics.RetrieveAPIView):
    """Retrieve refund details"""
    serializer_class = PaymentRefundSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PaymentRefund.objects.filter(payment__user=self.request.user)

# Admin Views
class AdminPaymentListView(generics.ListAPIView):
    """Admin view for all payments"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        queryset = Payment.objects.all()
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user__id=user_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by payment method
        payment_method = self.request.query_params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method__id=payment_method)
        
        return queryset.order_by('-created_at')

class AdminPaymentRefundListView(generics.ListAPIView):
    """Admin view for all refund requests"""
    serializer_class = PaymentRefundSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        queryset = PaymentRefund.objects.all()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')

class AdminPaymentRefundUpdateView(generics.UpdateAPIView):
    """Admin view to update refund status"""
    serializer_class = PaymentRefundUpdateSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = PaymentRefund.objects.all()
    
    def perform_update(self, serializer):
        refund = serializer.save()
        
        # If refund is approved, process it with gateway
        if refund.status == 'approved':
            gateway_manager = PaymentGatewayManager(refund.payment.payment_method)
            try:
                gateway_refund = gateway_manager.process_refund(refund)
                refund.gateway_refund_id = gateway_refund.get('id')
                refund.status = 'processing'
                refund.save()
            except Exception as e:
                logger.error(f"Error processing refund: {str(e)}")
                refund.status = 'failed'
                refund.save()

class PaymentTransactionListView(generics.ListAPIView):
    """List payment transactions"""
    serializer_class = PaymentTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        return PaymentTransaction.objects.filter(
            payment__user=self.request.user
        ).order_by('-created_at')

class PaymentWebhookCreateView(generics.CreateAPIView):
    """Create webhook record"""
    serializer_class = PaymentWebhookSerializer
    permission_classes = [permissions.AllowAny]  # Webhooks come from external services
    
    def perform_create(self, serializer):
        webhook = serializer.save()
        
        # Process webhook in background
        try:
            gateway_manager = PaymentGatewayManager(webhook.payment_method)
            gateway_manager.process_webhook(webhook)
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            webhook.status = 'failed'
            webhook.error_message = str(e)
            webhook.save()

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_analytics(request):
    """Get payment analytics for user"""
    user = request.user
    
    # Date range
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    if not start_date:
        start_date = timezone.now() - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    
    if not end_date:
        end_date = timezone.now()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Base queryset
    payments = Payment.objects.filter(
        user=user,
        created_at__date__gte=start_date.date(),
        created_at__date__lte=end_date.date()
    )
    
    # Calculate analytics
    total_payments = payments.count()
    total_amount = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    successful_payments = payments.filter(status='completed').count()
    failed_payments = payments.filter(status__in=['failed', 'cancelled']).count()
    
    # Refund data
    refunds = PaymentRefund.objects.filter(
        payment__user=user,
        created_at__date__gte=start_date.date(),
        created_at__date__lte=end_date.date()
    )
    refund_requests = refunds.count()
    total_refunded = refunds.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    
    analytics_data = {
        'total_payments': total_payments,
        'total_amount': total_amount,
        'successful_payments': successful_payments,
        'failed_payments': failed_payments,
        'refund_requests': refund_requests,
        'total_refunded': total_refunded,
        'success_rate': (successful_payments / total_payments * 100) if total_payments > 0 else 0,
        'monthly_data': [],  # Can be implemented as needed
        'payment_method_stats': []  # Can be implemented as needed
    }
    
    serializer = PaymentAnalyticsSerializer(analytics_data)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_payment_analytics(request):
    """Get payment analytics for admin"""
    # Date range
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    if not start_date:
        start_date = timezone.now() - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    
    if not end_date:
        end_date = timezone.now()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Base queryset
    payments = Payment.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    
    # Calculate analytics
    total_payments = payments.count()
    total_amount = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    successful_payments = payments.filter(status='completed').count()
    failed_payments = payments.filter(status__in=['failed', 'cancelled']).count()
    
    # Refund data
    refunds = PaymentRefund.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    refund_requests = refunds.count()
    total_refunded = refunds.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Monthly breakdown
    monthly_data = []
    current_date = start_date
    while current_date <= end_date:
        month_payments = payments.filter(
            created_at__year=current_date.year,
            created_at__month=current_date.month
        )
        monthly_data.append({
            'month': current_date.strftime('%Y-%m'),
            'payments': month_payments.count(),
            'amount': month_payments.aggregate(Sum('amount'))['amount__sum'] or 0,
            'successful': month_payments.filter(status='completed').count()
        })
        current_date = current_date.replace(day=1) + timedelta(days=32)
        current_date = current_date.replace(day=1)
    
    # Payment method breakdown
    payment_method_stats = []
    for method in PaymentMethod.objects.filter(is_active=True):
        method_payments = payments.filter(payment_method=method)
        payment_method_stats.append({
            'method': method.name,
            'payments': method_payments.count(),
            'amount': method_payments.aggregate(Sum('amount'))['amount__sum'] or 0,
            'success_rate': (method_payments.filter(status='completed').count() / method_payments.count() * 100) if method_payments.count() > 0 else 0
        })
    
    analytics_data = {
        'total_payments': total_payments,
        'total_amount': total_amount,
        'successful_payments': successful_payments,
        'failed_payments': failed_payments,
        'refund_requests': refund_requests,
        'total_refunded': total_refunded,
        'monthly_data': monthly_data,
        'payment_method_stats': payment_method_stats
    }
    
    serializer = PaymentAnalyticsSerializer(analytics_data)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_dashboard(request):
    """Get payment dashboard data for admin"""
    today = timezone.now().date()
    this_month = timezone.now().replace(day=1).date()
    
    # Recent payments
    recent_payments = Payment.objects.all().order_by('-created_at')[:10]
    
    # Pending refunds
    pending_refunds = PaymentRefund.objects.filter(
        status='requested'
    ).order_by('-created_at')[:10]
    
    # Today's stats
    today_payments = Payment.objects.filter(created_at__date=today).count()
    today_amount = Payment.objects.filter(
        created_at__date=today,
        status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # This month's stats
    this_month_payments = Payment.objects.filter(created_at__date__gte=this_month).count()
    this_month_amount = Payment.objects.filter(
        created_at__date__gte=this_month,
        status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Analytics
    analytics = {
        'total_payments': Payment.objects.count(),
        'total_amount': Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0,
        'successful_payments': Payment.objects.filter(status='completed').count(),
        'failed_payments': Payment.objects.filter(status__in=['failed', 'cancelled']).count(),
        'refund_requests': PaymentRefund.objects.count(),
        'total_refunded': PaymentRefund.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0,
        'monthly_data': [],
        'payment_method_stats': []
    }
    
    dashboard_data = {
        'recent_payments': recent_payments,
        'pending_refunds': pending_refunds,
        'analytics': analytics,
        'today_payments': today_payments,
        'today_amount': today_amount,
        'this_month_payments': this_month_payments,
        'this_month_amount': this_month_amount
    }
    
    serializer = PaymentDashboardSerializer(dashboard_data)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def webhook_handler(request, gateway_type):
    """Handle webhook from payment gateways"""
    try:
        # Get payment method
        payment_method = get_object_or_404(PaymentMethod, type=gateway_type, is_active=True)
        
        # Create webhook record
        webhook = PaymentWebhook.objects.create(
            payment_method=payment_method,
            event_type=request.data.get('event', 'unknown'),
            gateway_event_id=request.data.get('id', ''),
            payload=request.data,
            headers=dict(request.headers)
        )
        
        # Process webhook
        gateway_manager = PaymentGatewayManager(payment_method)
        gateway_manager.process_webhook(webhook)
        
        return Response({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return Response({'status': 'error'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_payment(request, payment_id):
    """Cancel a pending payment"""
    try:
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        
        if payment.status != 'pending':
            return Response({
                'success': False,
                'message': 'Only pending payments can be cancelled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        payment.status = 'cancelled'
        payment.failed_at = timezone.now()
        payment.save()
        
        # Create transaction record
        PaymentTransaction.objects.create(
            payment=payment,
            transaction_type='payment',
            amount=payment.amount,
            currency=payment.currency,
            status='cancelled',
            description=f'Payment cancelled by user'
        )
        
        return Response({
            'success': True,
            'message': 'Payment cancelled successfully'
        })
        
    except Exception as e:
        logger.error(f"Payment cancellation error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Payment cancellation failed'
        }, status=status.HTTP_400_BAD_REQUEST)
@csrf_exempt
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def razorpay_webhook(request):
    """Handle Razorpay webhook"""
    try:
        # Get webhook signature
        webhook_signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE')
        if not webhook_signature:
            logger.warning("Missing Razorpay webhook signature")
            return HttpResponse(status=400)
        
        # Validate signature
        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET if hasattr(settings, 'RAZORPAY_WEBHOOK_SECRET') else None
        if webhook_secret:
            payload_body = request.body.decode('utf-8')
            is_valid = RazorpaySignatureValidator.validate_webhook_signature(
                payload_body, webhook_signature, webhook_secret
            )
            if not is_valid:
                logger.warning("Invalid Razorpay webhook signature")
                return HttpResponse(status=400)
        
        # Parse webhook data
        webhook_data = json.loads(request.body)
        event_type = webhook_data.get('event')
        
        # Get or create payment method
        payment_method = get_object_or_404(PaymentMethod, type='razorpay', is_active=True)
        
        # Create webhook record
        webhook = PaymentWebhook.objects.create(
            payment_method=payment_method,
            event_type=event_type,
            gateway_event_id=webhook_data.get('id', ''),
            payload=webhook_data,
            headers=dict(request.headers)
        )
        
        # Process webhook
        gateway_manager = PaymentGatewayManager(payment_method)
        gateway_manager.process_webhook(webhook)
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"Razorpay webhook processing error: {str(e)}")
        return HttpResponse(status=500)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_receipt(request, payment_id):
    """Get payment receipt"""
    try:
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        
        if payment.status != 'completed':
            return Response({
                'success': False,
                'message': 'Receipt only available for completed payments'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        receipt_data = {
            'payment_id': payment.id,
            'amount': payment.amount,
            'total_amount': payment.total_amount,
            'processing_fee': payment.processing_fee,
            'currency': payment.currency,
            'payment_method': payment.payment_method.name,
            'status': payment.status,
            'completed_at': payment.completed_at,
            'user_email': payment.user.email,
            'subscription_plan': payment.subscription.plan.name if payment.subscription else None,
            'gateway_payment_id': payment.gateway_payment_id,
            'gateway_order_id': payment.gateway_order_id,
            'description': payment.description,
            'purpose': payment.purpose
        }
        
        return Response({
            'success': True,
            'receipt': receipt_data
        })
        
    except Exception as e:
        logger.error(f"Receipt generation error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Receipt generation failed'
        }, status=status.HTTP_400_BAD_REQUEST)
