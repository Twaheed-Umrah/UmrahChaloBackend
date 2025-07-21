import hashlib
import hmac
import json
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import Payment, PaymentRefund, PaymentTransaction, PaymentWebhook
import razorpay
import stripe
import requests

logger = logging.getLogger(__name__)

class PaymentGatewayManager:
    """Manager class for handling different payment gateways"""
    
    def __init__(self, payment_method):
        self.payment_method = payment_method
        self.gateway_type = payment_method.type
        self.config = payment_method.gateway_config
        
        # Initialize gateway clients
        if self.gateway_type == 'razorpay':
            self.client = razorpay.Client(
                auth=(self.config.get('key_id'), self.config.get('key_secret'))
            )
        elif self.gateway_type == 'stripe':
            stripe.api_key = self.config.get('secret_key')
            self.client = stripe
        elif self.gateway_type == 'paypal':
            self.client = self._initialize_paypal()
        elif self.gateway_type == 'upi':
            self.client = self._initialize_upi()
    
    def _initialize_paypal(self):
        """Initialize PayPal client"""
        try:
            # PayPal SDK initialization
            import paypalrestsdk
            
            paypalrestsdk.configure({
                "mode": self.config.get('mode', 'sandbox'),  # sandbox or live
                "client_id": self.config.get('client_id'),
                "client_secret": self.config.get('client_secret')
            })
            
            return paypalrestsdk
        except ImportError:
            logger.error("PayPal SDK not installed. Install with: pip install paypalrestsdk")
            raise
    
    def _initialize_upi(self):
        """Initialize UPI client (placeholder for UPI integration)"""
        # UPI integration would depend on the specific provider
        # This is a placeholder for UPI gateway initialization
        return {
            'base_url': self.config.get('base_url'),
            'merchant_id': self.config.get('merchant_id'),
            'api_key': self.config.get('api_key')
        }
    
    def create_order(self, payment):
        """Create order with payment gateway"""
        try:
            if self.gateway_type == 'razorpay':
                return self._create_razorpay_order(payment)
            elif self.gateway_type == 'stripe':
                return self._create_stripe_payment_intent(payment)
            elif self.gateway_type == 'paypal':
                return self._create_paypal_order(payment)
            elif self.gateway_type == 'upi':
                return self._create_upi_order(payment)
            else:
                raise Exception(f"Unsupported payment gateway: {self.gateway_type}")
        except Exception as e:
            logger.error(f"Error creating order for {self.gateway_type}: {str(e)}")
            raise
    
    def _create_razorpay_order(self, payment):
        """Create Razorpay order"""
        order_data = {
            'amount': int(payment.total_amount * 100),  # Convert to paise
            'currency': payment.currency,
            'payment_capture': 1,
            'notes': {
                'payment_id': str(payment.id),
                'user_id': str(payment.user.id),
                'subscription_id': str(payment.subscription.id) if payment.subscription else None
            }
        }
        
        order = self.client.order.create(data=order_data)
        
        # Create transaction record
        PaymentTransaction.objects.create(
            payment=payment,
            transaction_type='payment',
            amount=payment.total_amount,
            currency=payment.currency,
            gateway_transaction_id=order['id'],
            gateway_response=order,
            status='pending'
        )
        
        return order
    
    def _create_stripe_payment_intent(self, payment):
        """Create Stripe payment intent"""
        intent_data = {
            'amount': int(payment.total_amount * 100),  # Convert to cents
            'currency': payment.currency.lower(),
            'automatic_payment_methods': {'enabled': True},
            'metadata': {
                'payment_id': str(payment.id),
                'user_id': str(payment.user.id),
                'subscription_id': str(payment.subscription.id) if payment.subscription else None
            }
        }
        
        intent = self.client.PaymentIntent.create(**intent_data)
        
        # Create transaction record
        PaymentTransaction.objects.create(
            payment=payment,
            transaction_type='payment',
            amount=payment.total_amount,
            currency=payment.currency,
            gateway_transaction_id=intent['id'],
            gateway_response=intent,
            status='pending'
        )
        
        return intent
    
    def _create_paypal_order(self, payment):
        """Create PayPal order"""
        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": payment.currency,
                    "value": str(payment.total_amount)
                },
                "description": payment.description or f"Payment for {payment.purpose}",
                "custom_id": str(payment.id)
            }],
            "application_context": {
                "return_url": self.config.get('return_url'),
                "cancel_url": self.config.get('cancel_url')
            }
        }
        
        order = self.client.Payment(order_data)
        
        if order.create():
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=payment,
                transaction_type='payment',
                amount=payment.total_amount,
                currency=payment.currency,
                gateway_transaction_id=order.id,
                gateway_response=order.to_dict(),
                status='pending'
            )
            
            return order.to_dict()
        else:
            raise Exception(f"PayPal order creation failed: {order.error}")
    
    def _create_upi_order(self, payment):
        """Create UPI order"""
        # This is a placeholder implementation for UPI
        # Actual implementation would depend on the UPI provider
        order_data = {
            'amount': float(payment.total_amount),
            'currency': payment.currency,
            'payment_id': str(payment.id),
            'user_id': str(payment.user.id),
            'description': payment.description or f"Payment for {payment.purpose}"
        }
        
        # Example API call to UPI provider
        headers = {
            'Authorization': f"Bearer {self.config.get('api_key')}",
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{self.config.get('base_url')}/create-order",
                json=order_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                order = response.json()
                
                # Create transaction record
                PaymentTransaction.objects.create(
                    payment=payment,
                    transaction_type='payment',
                    amount=payment.total_amount,
                    currency=payment.currency,
                    gateway_transaction_id=order.get('order_id'),
                    gateway_response=order,
                    status='pending'
                )
                
                return order
            else:
                raise Exception(f"UPI order creation failed: {response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"UPI API error: {str(e)}")
    
    def verify_payment(self, payment_id, order_id, signature):
        """Verify payment with gateway"""
        try:
            if self.gateway_type == 'razorpay':
                return self._verify_razorpay_payment(payment_id, order_id, signature)
            elif self.gateway_type == 'stripe':
                return self._verify_stripe_payment(payment_id)
            elif self.gateway_type == 'paypal':
                return self._verify_paypal_payment(payment_id)
            elif self.gateway_type == 'upi':
                return self._verify_upi_payment(payment_id, order_id, signature)
            else:
                raise Exception(f"Unsupported payment gateway: {self.gateway_type}")
        except Exception as e:
            logger.error(f"Error verifying payment for {self.gateway_type}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _verify_razorpay_payment(self, payment_id, order_id, signature):
        """Verify Razorpay payment"""
        try:
            # Verify signature
            generated_signature = hmac.new(
                self.config.get('key_secret').encode('utf-8'),
                f"{order_id}|{payment_id}".encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if generated_signature == signature:
                # Fetch payment details from Razorpay
                payment_details = self.client.payment.fetch(payment_id)
                
                return {
                    'success': True,
                    'payment_id': payment_id,
                    'order_id': order_id,
                    'signature': signature,
                    'payment_details': payment_details
                }
            else:
                return {'success': False, 'error': 'Invalid signature'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _verify_stripe_payment(self, payment_intent_id):
        """Verify Stripe payment"""
        try:
            intent = self.client.PaymentIntent.retrieve(payment_intent_id)
            
            if intent.status == 'succeeded':
                return {
                    'success': True,
                    'payment_id': payment_intent_id,
                    'payment_details': intent
                }
            else:
                return {'success': False, 'error': f'Payment status: {intent.status}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _verify_paypal_payment(self, payment_id):
        """Verify PayPal payment"""
        try:
            payment = self.client.Payment.find(payment_id)
            
            if payment.state == 'approved':
                return {
                    'success': True,
                    'payment_id': payment_id,
                    'payment_details': payment.to_dict()
                }
            else:
                return {'success': False, 'error': f'Payment state: {payment.state}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _verify_upi_payment(self, payment_id, order_id, signature):
        """Verify UPI payment"""
        try:
            # Verify signature (if applicable)
            if signature:
                generated_signature = hmac.new(
                    self.config.get('api_key').encode('utf-8'),
                    f"{order_id}|{payment_id}".encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                if generated_signature != signature:
                    return {'success': False, 'error': 'Invalid signature'}
            
            # Verify payment status with UPI provider
            headers = {
                'Authorization': f"Bearer {self.config.get('api_key')}",
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.config.get('base_url')}/verify-payment/{payment_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                payment_details = response.json()
                
                if payment_details.get('status') == 'success':
                    return {
                        'success': True,
                        'payment_id': payment_id,
                        'order_id': order_id,
                        'signature': signature,
                        'payment_details': payment_details
                    }
                else:
                    return {'success': False, 'error': f"Payment status: {payment_details.get('status')}"}
            else:
                return {'success': False, 'error': f'Verification failed: {response.text}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def process_refund(self, refund):
        """Process refund with gateway"""
        try:
            if self.gateway_type == 'razorpay':
                return self._process_razorpay_refund(refund)
            elif self.gateway_type == 'stripe':
                return self._process_stripe_refund(refund)
            elif self.gateway_type == 'paypal':
                return self._process_paypal_refund(refund)
            elif self.gateway_type == 'upi':
                return self._process_upi_refund(refund)
            else:
                raise Exception(f"Unsupported payment gateway: {self.gateway_type}")
        except Exception as e:
            logger.error(f"Error processing refund for {self.gateway_type}: {str(e)}")
            raise
    
    def _process_razorpay_refund(self, refund):
        """Process Razorpay refund"""
        refund_data = {
            'amount': int(refund.amount * 100),  # Convert to paise
            'notes': {
                'refund_id': str(refund.id),
                'reason': refund.reason,
                'description': refund.description
            }
        }
        
        gateway_refund = self.client.payment.refund(
            refund.payment.gateway_payment_id,
            refund_data
        )
        
        # Create transaction record
        PaymentTransaction.objects.create(
            payment=refund.payment,
            transaction_type='refund',
            amount=refund.amount,
            currency=refund.payment.currency,
            gateway_transaction_id=gateway_refund['id'],
            gateway_response=gateway_refund,
            status='processing'
        )
        
        return gateway_refund
    
    def _process_stripe_refund(self, refund):
        """Process Stripe refund"""
        refund_data = {
            'payment_intent': refund.payment.gateway_payment_id,
            'amount': int(refund.amount * 100),  # Convert to cents
            'metadata': {
                'refund_id': str(refund.id),
                'reason': refund.reason,
                'description': refund.description
            }
        }
        
        gateway_refund = self.client.Refund.create(**refund_data)
        
        # Create transaction record
        PaymentTransaction.objects.create(
            payment=refund.payment,
            transaction_type='refund',
            amount=refund.amount,
            currency=refund.payment.currency,
            gateway_transaction_id=gateway_refund['id'],
            gateway_response=gateway_refund,
            status='processing'
        )
        
        return gateway_refund
    
    def _process_paypal_refund(self, refund):
        """Process PayPal refund"""
        # Find the sale transaction
        payment = self.client.Payment.find(refund.payment.gateway_payment_id)
        
        # Get the sale transaction
        sale = None
        for transaction in payment.transactions:
            for related_resource in transaction.related_resources:
                if 'sale' in related_resource:
                    sale = related_resource['sale']
                    break
        
        if not sale:
            raise Exception("No sale transaction found for refund")
        
        # Create refund
        refund_data = {
            'amount': {
                'total': str(refund.amount),
                'currency': refund.payment.currency
            },
            'description': refund.description or f"Refund for {refund.reason}"
        }
        
        gateway_refund = self.client.Refund(refund_data)
        
        if gateway_refund.create(sale['id']):
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=refund.payment,
                transaction_type='refund',
                amount=refund.amount,
                currency=refund.payment.currency,
                gateway_transaction_id=gateway_refund.id,
                gateway_response=gateway_refund.to_dict(),
                status='processing'
            )
            
            return gateway_refund.to_dict()
        else:
            raise Exception(f"PayPal refund creation failed: {gateway_refund.error}")
    
    def _process_upi_refund(self, refund):
        """Process UPI refund"""
        refund_data = {
            'payment_id': refund.payment.gateway_payment_id,
            'amount': float(refund.amount),
            'currency': refund.payment.currency,
            'refund_id': str(refund.id),
            'reason': refund.reason,
            'description': refund.description
        }
        
        headers = {
            'Authorization': f"Bearer {self.config.get('api_key')}",
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            f"{self.config.get('base_url')}/process-refund",
            json=refund_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            gateway_refund = response.json()
            
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=refund.payment,
                transaction_type='refund',
                amount=refund.amount,
                currency=refund.payment.currency,
                gateway_transaction_id=gateway_refund.get('refund_id'),
                gateway_response=gateway_refund,
                status='processing'
            )
            
            return gateway_refund
        else:
            raise Exception(f"UPI refund processing failed: {response.text}")
    
    def process_webhook(self, webhook):
        """Process webhook from gateway"""
        try:
            webhook.status = 'processing'
            webhook.save()
            
            if self.gateway_type == 'razorpay':
                self._process_razorpay_webhook(webhook)
            elif self.gateway_type == 'stripe':
                self._process_stripe_webhook(webhook)
            elif self.gateway_type == 'paypal':
                self._process_paypal_webhook(webhook)
            elif self.gateway_type == 'upi':
                self._process_upi_webhook(webhook)
            
            webhook.status = 'completed'
            webhook.processed_at = timezone.now()
            webhook.save()
            
        except Exception as e:
            webhook.status = 'failed'
            webhook.error_message = str(e)
            webhook.save()
            logger.error(f"Error processing webhook: {str(e)}")
            raise
    
    def _process_razorpay_webhook(self, webhook):
        """Process Razorpay webhook"""
        event_type = webhook.event_type
        payload = webhook.payload
        
        if event_type == 'payment.captured':
            payment_id = payload.get('payment', {}).get('entity', {}).get('id')
            if payment_id:
                self._update_payment_status(payment_id, 'completed')
        
        elif event_type == 'payment.failed':
            payment_id = payload.get('payment', {}).get('entity', {}).get('id')
            if payment_id:
                self._update_payment_status(payment_id, 'failed')
        
        elif event_type == 'refund.processed':
            refund_id = payload.get('refund', {}).get('entity', {}).get('id')
            if refund_id:
                self._update_refund_status(refund_id, 'completed')
    
    def _process_stripe_webhook(self, webhook):
        """Process Stripe webhook"""
        event_type = webhook.event_type
        payload = webhook.payload
        
        if event_type == 'payment_intent.succeeded':
            payment_intent_id = payload.get('data', {}).get('object', {}).get('id')
            if payment_intent_id:
                self._update_payment_status(payment_intent_id, 'completed')
        
        elif event_type == 'payment_intent.payment_failed':
            payment_intent_id = payload.get('data', {}).get('object', {}).get('id')
            if payment_intent_id:
                self._update_payment_status(payment_intent_id, 'failed')
        
        elif event_type == 'charge.dispute.created':
            # Handle dispute creation
            pass
    
    def _process_paypal_webhook(self, webhook):
        """Process PayPal webhook"""
        event_type = webhook.event_type
        payload = webhook.payload
        
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            payment_id = payload.get('resource', {}).get('id')
            if payment_id:
                self._update_payment_status(payment_id, 'completed')
        
        elif event_type == 'PAYMENT.CAPTURE.DENIED':
            payment_id = payload.get('resource', {}).get('id')
            if payment_id:
                self._update_payment_status(payment_id, 'failed')
    
    def _process_upi_webhook(self, webhook):
        """Process UPI webhook"""
        event_type = webhook.event_type
        payload = webhook.payload
        
        if event_type == 'payment.success':
            payment_id = payload.get('payment_id')
            if payment_id:
                self._update_payment_status(payment_id, 'completed')
        
        elif event_type == 'payment.failed':
            payment_id = payload.get('payment_id')
            if payment_id:
                self._update_payment_status(payment_id, 'failed')
    
    def _update_payment_status(self, gateway_payment_id, status):
        """Update payment status based on gateway callback"""
        try:
            payment = Payment.objects.get(gateway_payment_id=gateway_payment_id)
            payment.status = status
            
            if status == 'completed':
                payment.completed_at = timezone.now()
                if payment.subscription:
                    payment.subscription.activate()
            elif status == 'failed':
                payment.failed_at = timezone.now()
            
            payment.save()
            
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for gateway_payment_id: {gateway_payment_id}")
    
    def _update_refund_status(self, gateway_refund_id, status):
        """Update refund status based on gateway callback"""
        try:
            refund = PaymentRefund.objects.get(gateway_refund_id=gateway_refund_id)
            refund.status = status
            
            if status == 'completed':
                refund.completed_at = timezone.now()
            
            refund.save()
            
        except PaymentRefund.DoesNotExist:
            logger.warning(f"Refund not found for gateway_refund_id: {gateway_refund_id}")


class PaymentHelper:
    """Helper class for payment-related utilities"""
    
    @staticmethod
    def calculate_processing_fee(amount, payment_method):
        """Calculate processing fee for a payment"""
        percentage_fee = (amount * payment_method.processing_fee_percentage) / 100
        total_fee = percentage_fee + payment_method.processing_fee_fixed
        return total_fee
    
    @staticmethod
    def validate_webhook_signature(payload, signature, secret):
        """Validate webhook signature"""
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    @staticmethod
    def generate_receipt_number():
        """Generate unique receipt number"""
        import uuid
        return f"RCP-{uuid.uuid4().hex[:8].upper()}"
    
    @staticmethod
    def format_currency(amount, currency='INR'):
        """Format currency amount"""
        if currency == 'INR':
            return f"₹{amount:,.2f}"
        elif currency == 'USD':
            return f"${amount:,.2f}"
        else:
            return f"{amount:,.2f} {currency}"
    
    @staticmethod
    def get_payment_status_display(status):
        """Get display text for payment status"""
        status_map = {
            'pending': 'Pending',
            'processing': 'Processing',
            'completed': 'Completed',
            'failed': 'Failed',
            'cancelled': 'Cancelled',
            'refunded': 'Refunded'
        }
        return status_map.get(status, status.title())
    
    @staticmethod
    def is_payment_refundable(payment):
        """Check if payment can be refunded"""
        if payment.status != 'completed':
            return False
        
        # Check if already fully refunded
        total_refunded = payment.refunds.filter(
            status__in=['completed', 'approved', 'processing']
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        return total_refunded < payment.amount
    
    @staticmethod
    def get_refundable_amount(payment):
        """Get maximum refundable amount for a payment"""
        if not PaymentHelper.is_payment_refundable(payment):
            return 0
        
        total_refunded = payment.refunds.filter(
            status__in=['completed', 'approved', 'processing']
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        return payment.amount - total_refunded


class PaymentAnalytics:
    """Analytics helper for payment data"""
    
    @staticmethod
    def get_payment_success_rate(queryset):
        """Calculate payment success rate"""
        total_payments = queryset.count()
        successful_payments = queryset.filter(status='completed').count()
        
        if total_payments == 0:
            return 0
        
        return (successful_payments / total_payments) * 100
    
    @staticmethod
    def get_average_transaction_amount(queryset):
        """Calculate average transaction amount"""
        from django.db.models import Avg
        
        avg_amount = queryset.filter(status='completed').aggregate(
            avg_amount=Avg('amount')
        )['avg_amount']
        
        return avg_amount or 0
    
    @staticmethod
    def get_payment_trends(queryset, period='monthly'):
        """Get payment trends over time"""
        from django.db.models import Count, Sum
        from django.db.models.functions import TruncMonth, TruncDay
        
        if period == 'monthly':
            trunc_func = TruncMonth
        else:
            trunc_func = TruncDay
        
        trends = queryset.annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            payment_count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('period')
        
        return trends
    
    @staticmethod
    def get_top_payment_methods(queryset, limit=5):
        """Get top payment methods by usage"""
        from django.db.models import Count, Sum
        
        return queryset.values(
            'payment_method__name'
        ).annotate(
            payment_count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('-payment_count')[:limit]