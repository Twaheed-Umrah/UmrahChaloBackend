import razorpay
import hashlib
import hmac
import json
import logging
import requests
import base64
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from .models import Payment, PaymentRefund, PaymentTransaction, PaymentWebhook

logger = logging.getLogger(__name__)

class PaymentGatewayManager:
    """Payment gateway manager for handling different payment methods"""
    
    def __init__(self, payment_method):
        self.payment_method = payment_method
        self.gateway_config = payment_method.gateway_config
        
        if payment_method.type == 'razorpay':
            self.client = razorpay.Client(
                auth=(
                    settings.RAZORPAY_KEY_ID or 'rzp_live_SbhF1RJDJyDNdv',
                    settings.RAZORPAY_KEY_SECRET or '7Ox6LW8kzLycPbStojMiROWB'
                )
            )
    
    def create_order(self, payment):
        """Create payment order with gateway"""
        try:
            if self.payment_method.type == 'razorpay':
                return self._create_razorpay_order(payment)
            elif self.payment_method.type == 'paypal':
                return self._create_paypal_order(payment)
            else:
                raise NotImplementedError(f"Payment method {self.payment_method.type} not implemented")
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            raise
    
    def _create_razorpay_order(self, payment):
        """Create Razorpay order"""
        order_data = {
            'amount': int(payment.total_amount * 100),  # Amount in paise
            'currency': payment.currency,
            'receipt': f'payment_{payment.id}',
            'notes': {
                'payment_id': str(payment.id),
                'user_email': payment.user.email,
                'purpose': payment.purpose
            }
        }
        
        order = self.client.order.create(order_data)
        
        # Create transaction record
        PaymentTransaction.objects.create(
            payment=payment,
            transaction_type='payment',
            amount=payment.total_amount,
            currency=payment.currency,
            gateway_transaction_id=order['id'],
            gateway_response=order,
            status='pending',
            description=f'Razorpay order created for payment {payment.id}'
        )
        
        return order
    
    def verify_payment(self, payment_id, order_id, signature):
        """Verify payment signature"""
        try:
            if self.payment_method.type == 'razorpay':
                return self._verify_razorpay_payment(payment_id, order_id, signature)
            elif self.payment_method.type == 'paypal':
                # For PayPal, we capture using the order_id, signature/payment_id are not used same way
                return self._verify_paypal_payment(order_id)
            else:
                raise NotImplementedError(f"Payment method {self.payment_method.type} not implemented")
        except Exception as e:
            logger.error(f"Error verifying payment: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _verify_razorpay_payment(self, payment_id, order_id, signature):
        """Verify Razorpay payment signature"""
        try:
            # Verify signature
            generated_signature = hmac.new(
                settings.RAZORPAY_KEY_SECRET.encode() or b'7Ox6LW8kzLycPbStojMiROWB',
                f'{order_id}|{payment_id}'.encode(),
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
            logger.error(f"Razorpay verification error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def process_refund(self, refund):
        """Process refund with gateway"""
        try:
            if self.payment_method.type == 'razorpay':
                return self._process_razorpay_refund(refund)
            elif self.payment_method.type == 'paypal':
                # To be implemented
                raise NotImplementedError("PayPal refund not implemented yet")
            else:
                raise NotImplementedError(f"Payment method {self.payment_method.type} not implemented")
        except Exception as e:
            logger.error(f"Error processing refund: {str(e)}")
            raise
    
    def _process_razorpay_refund(self, refund):
        """Process Razorpay refund"""
        refund_data = {
            'amount': int(refund.amount * 100),  # Amount in paise
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
            status='processing',
            description=f'Refund processed for payment {refund.payment.id}'
        )
        
        return gateway_refund
    
    def process_webhook(self, webhook):
        """Process webhook from payment gateway"""
        try:
            if self.payment_method.type == 'razorpay':
                return self._process_razorpay_webhook(webhook)
            elif self.payment_method.type == 'paypal':
                # To be implemented
                logger.warning("PayPal webhook processing not implemented")
                webhook.status = 'ignored'
                webhook.save()
            else:
                logger.warning(f"Webhook processing not implemented for {self.payment_method.type}")
                webhook.status = 'ignored'
                webhook.save()
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            webhook.status = 'failed'
            webhook.error_message = str(e)
            webhook.save()
            raise

    # ------------------ PayPal Integration Methods ------------------

    def _get_paypal_access_token(self):
        client_id = settings.PAYMENT_GATEWAY_SETTINGS.get('PAYPAL', {}).get('CLIENT_ID', '')
        secret = settings.PAYMENT_GATEWAY_SETTINGS.get('PAYPAL', {}).get('SECRET_KEY', '')
        mode = settings.PAYMENT_GATEWAY_SETTINGS.get('PAYPAL', {}).get('MODE', 'sandbox')
        
        base_url = "https://api-m.paypal.com" if mode == 'live' else "https://api-m.sandbox.paypal.com"
        
        auth_str = f"{client_id}:{secret}"
        auth_bytes = auth_str.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}
        
        response = requests.post(f"{base_url}/v1/oauth2/token", headers=headers, data=data)
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            logger.error(f"Failed to get PayPal token: {response.text}")
            raise Exception("Failed to get PayPal token")

    def _create_paypal_order(self, payment):
        """Create PayPal order"""
        token = self._get_paypal_access_token()
        mode = settings.PAYMENT_GATEWAY_SETTINGS.get('PAYPAL', {}).get('MODE', 'sandbox')
        base_url = "https://api-m.paypal.com" if mode == 'live' else "https://api-m.sandbox.paypal.com"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # PayPal uses standard formatted float string (e.g. "100.00")
        amount_str = f"{payment.total_amount:.2f}"
        
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": f"payment_{payment.id}",
                    "amount": {
                        "currency_code": payment.currency,
                        "value": amount_str
                    },
                    "description": payment.purpose
                }
            ]
        }
        
        response = requests.post(f"{base_url}/v2/checkout/orders", headers=headers, json=payload)
        if response.status_code in (200, 201):
            order = response.json()
            
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=payment,
                transaction_type='payment',
                amount=payment.total_amount,
                currency=payment.currency,
                gateway_transaction_id=order['id'],
                gateway_response=order,
                status='pending',
                description=f'PayPal order created for payment {payment.id}'
            )
            
            return order
        else:
            logger.error(f"Failed to create PayPal order: {response.text}")
            raise Exception("Failed to create PayPal order")

    def _verify_paypal_payment(self, order_id):
        """Verify/Capture PayPal payment"""
        token = self._get_paypal_access_token()
        mode = settings.PAYMENT_GATEWAY_SETTINGS.get('PAYPAL', {}).get('MODE', 'sandbox')
        base_url = "https://api-m.paypal.com" if mode == 'live' else "https://api-m.sandbox.paypal.com"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Capture the order
        response = requests.post(f"{base_url}/v2/checkout/orders/{order_id}/capture", headers=headers, json={})
        
        # 201 Created or 200 OK means captured
        if response.status_code in (200, 201):
            capture_data = response.json()
            status = capture_data.get('status')
            
            if status == 'COMPLETED':
                # Get capture ID
                try:
                    capture_id = capture_data['purchase_units'][0]['payments']['captures'][0]['id']
                except (KeyError, IndexError):
                    capture_id = order_id
                    
                return {
                    'success': True,
                    'payment_id': capture_id,
                    'order_id': order_id,
                    'signature': None,
                    'payment_details': capture_data
                }
            else:
                return {'success': False, 'error': f'PayPal status is {status}'}
        else:
            logger.error(f"PayPal capture failed: {response.text}")
            # Could be already captured, check if it's already complete by getting order details
            get_resp = requests.get(f"{base_url}/v2/checkout/orders/{order_id}", headers=headers)
            if get_resp.status_code == 200:
                order_data = get_resp.json()
                if order_data.get('status') == 'COMPLETED':
                    try:
                        capture_id = order_data['purchase_units'][0]['payments']['captures'][0]['id']
                    except (KeyError, IndexError):
                        capture_id = order_id
                    return {
                        'success': True,
                        'payment_id': capture_id,
                        'order_id': order_id,
                        'signature': None,
                        'payment_details': order_data
                    }
            return {'success': False, 'error': f'Capture error: {response.text}'}
    
    def _process_razorpay_webhook(self, webhook):
        """Process Razorpay webhook"""
        event_type = webhook.event_type
        payload = webhook.payload
        
        try:
            if event_type == 'payment.captured':
                self._handle_payment_captured(webhook, payload)
            elif event_type == 'payment.failed':
                self._handle_payment_failed(webhook, payload)
            elif event_type == 'refund.processed':
                self._handle_refund_processed(webhook, payload)
            else:
                logger.info(f"Unhandled webhook event: {event_type}")
                webhook.status = 'ignored'
            
            webhook.processed_at = timezone.now()
            webhook.status = 'processed'
            webhook.save()
            
        except Exception as e:
            logger.error(f"Error processing Razorpay webhook: {str(e)}")
            webhook.status = 'failed'
            webhook.error_message = str(e)
            webhook.save()
            raise
    
    def _handle_payment_captured(self, webhook, payload):
        """Handle payment captured webhook"""
        payment_data = payload.get('payment', {}).get('entity', {})
        order_id = payment_data.get('order_id')
        
        if order_id:
            try:
                payment = Payment.objects.get(gateway_order_id=order_id)
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.gateway_payment_id = payment_data.get('id')
                payment.gateway_response = payment_data
                payment.save()
                
                # Activate subscription if exists
                if payment.subscription:
                    payment.subscription.activate()
                    
                logger.info(f"Payment {payment.id} marked as completed via webhook")
                
            except Payment.DoesNotExist:
                logger.warning(f"Payment not found for order_id: {order_id}")
    
    def _handle_payment_failed(self, webhook, payload):
        """Handle payment failed webhook"""
        payment_data = payload.get('payment', {}).get('entity', {})
        order_id = payment_data.get('order_id')
        
        if order_id:
            try:
                payment = Payment.objects.get(gateway_order_id=order_id)
                payment.status = 'failed'
                payment.failed_at = timezone.now()
                payment.gateway_response = payment_data
                payment.save()
                
                logger.info(f"Payment {payment.id} marked as failed via webhook")
                
            except Payment.DoesNotExist:
                logger.warning(f"Payment not found for order_id: {order_id}")
    
    def _handle_refund_processed(self, webhook, payload):
        """Handle refund processed webhook"""
        refund_data = payload.get('refund', {}).get('entity', {})
        payment_id = refund_data.get('payment_id')
        
        if payment_id:
            try:
                payment = Payment.objects.get(gateway_payment_id=payment_id)
                refund = PaymentRefund.objects.get(
                    payment=payment,
                    gateway_refund_id=refund_data.get('id')
                )
                refund.status = 'completed'
                refund.completed_at = timezone.now()
                refund.gateway_response = refund_data
                refund.save()
                
                logger.info(f"Refund {refund.id} marked as completed via webhook")
                
            except (Payment.DoesNotExist, PaymentRefund.DoesNotExist):
                logger.warning(f"Refund not found for payment_id: {payment_id}")


class RazorpaySignatureValidator:
    """Validate Razorpay webhook signatures"""
    
    @staticmethod
    def validate_webhook_signature(payload, signature, secret):
        """Validate webhook signature"""
        try:
            expected_signature = hmac.new(
                secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Signature validation error: {str(e)}")
            return False