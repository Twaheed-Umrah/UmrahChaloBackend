from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from apps.core.pagination import LargeResultsSetPagination
from apps.core.permissions import IsOwnerOrReadOnly
from .models import PaymentMethod, Payment, PaymentRefund, PaymentTransaction, PaymentWebhook
from .serializers import (
    PaymentMethodSerializer, PaymentCreateSerializer, PaymentSerializer,
    PaymentUpdateSerializer, PaymentRefundCreateSerializer, PaymentRefundSerializer,
    PaymentRefundUpdateSerializer, PaymentTransactionSerializer,
    PaymentWebhookSerializer, PaymentAnalyticsSerializer, PaymentDashboardSerializer
)
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
        except Exception as e:
            logger.error(f"Error creating payment order: {str(e)}")
            payment.status = 'failed'
            payment.failed_at = timezone.now()
            payment.save()
            raise

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
        
        return queryset.order_by('-created_at')

class PaymentDetailView(generics.RetrieveAPIView):
    """Retrieve payment details"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)

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
    """Verify payment with gateway"""
    try:
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        
        gateway_manager = PaymentGatewayManager(payment.payment_method)
        verification_result = gateway_manager.verify_payment(
            payment_id=request.data.get('razorpay_payment_id'),
            order_id=request.data.get('razorpay_order_id'),
            signature=request.data.get('razorpay_signature')
        )
        
        if verification_result['success']:
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.gateway_payment_id = verification_result['payment_id']
            payment.gateway_signature = verification_result['signature']
            payment.save()
            
            # Activate subscription
            if payment.subscription:
                payment.subscription.activate()
            
            return Response({
                'success': True,
                'message': 'Payment verified successfully',
                'payment': PaymentSerializer(payment).data
            })
        else:
            payment.status = 'failed'
            payment.failed_at = timezone.now()
            payment.save()
            
            return Response({
                'success': False,
                'message': 'Payment verification failed'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Payment verification failed'
        }, status=status.HTTP_400_BAD_REQUEST)

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
        payment__user=user,
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
            'currency': payment.currency,
            'payment_method': payment.payment_method.name,
            'status': payment.status,
            'completed_at': payment.completed_at,
            'user_email': payment.user.email,
            'subscription_plan': payment.subscription.plan.name if payment.subscription else None,
            'gateway_payment_id': payment.gateway_payment_id
        }
        
        return Response(receipt_data)
        
    except Exception as e:
        logger.error(f"Receipt generation error: {str(e)}")
        return Response({
            'success': False,
            'message': 'Receipt generation failed'
        }, status=status.HTTP_400_BAD_REQUEST)