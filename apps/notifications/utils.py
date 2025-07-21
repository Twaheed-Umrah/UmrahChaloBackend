import logging
import json
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .models import (
    Notification, NotificationTemplate, NotificationPreference,
    NotificationLog, BulkNotification
)

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    """Service class for handling notifications"""
    
    def __init__(self):
        self.email_backend = EmailNotificationBackend()
        self.sms_backend = SMSNotificationBackend()
        self.app_backend = AppNotificationBackend()
    
    def create_notification(
        self,
        recipient: User,
        template_type: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = 'medium',
        title: Optional[str] = None,
        message: Optional[str] = None
    ) -> Notification:
        """Create a new notification"""
        
        try:
            # Get template
            template = NotificationTemplate.objects.get(
                notification_type=template_type,
                is_active=True
            )
            
            # Get user preferences
            preferences = self._get_user_preferences(recipient)
            
            # Render message from template
            rendered_data = self._render_template(template, data or {})
            
            # Create notification
            notification = Notification.objects.create(
                recipient=recipient,
                template=template,
                title=title or rendered_data['title'],
                message=message or rendered_data['message'],
                data=data or {},
                priority=priority
            )
            
            # Send notification based on preferences
            self._send_notification(notification, preferences)
            
            return notification
            
        except NotificationTemplate.DoesNotExist:
            logger.error(f"Template not found: {template_type}")
            raise ValueError(f"Invalid notification template: {template_type}")
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise
    
    def send_bulk_notification(
        self,
        bulk_notification: BulkNotification,
        recipients: Optional[List[User]] = None
    ) -> None:
        """Send bulk notification to multiple users"""
        
        try:
            if not recipients:
                recipients = self._get_bulk_recipients(bulk_notification)
            
            bulk_notification.total_recipients = len(recipients)
            bulk_notification.status = 'sending'
            bulk_notification.started_at = timezone.now()
            bulk_notification.save()
            
            sent_count = 0
            failed_count = 0
            
            for recipient in recipients:
                try:
                    with transaction.atomic():
                        # Create individual notification
                        notification = Notification.objects.create(
                            recipient=recipient,
                            template=self._get_default_template(),
                            title=bulk_notification.title,
                            message=bulk_notification.message,
                            priority='medium'
                        )
                        
                        # Get preferences
                        preferences = self._get_user_preferences(recipient)
                        
                        # Send notification
                        success = self._send_bulk_notification_to_user(
                            notification, bulk_notification, preferences
                        )
                        
                        if success:
                            sent_count += 1
                        else:
                            failed_count += 1
                            
                except Exception as e:
                    logger.error(f"Error sending bulk notification to {recipient.email}: {str(e)}")
                    failed_count += 1
            
            # Update bulk notification status
            bulk_notification.sent_count = sent_count
            bulk_notification.failed_count = failed_count
            bulk_notification.status = 'completed'
            bulk_notification.completed_at = timezone.now()
            bulk_notification.save()
            
        except Exception as e:
            bulk_notification.status = 'failed'
            bulk_notification.save()
            logger.error(f"Error in bulk notification: {str(e)}")
            raise
    
    def _get_user_preferences(self, user: User) -> NotificationPreference:
        """Get or create user notification preferences"""
        try:
            preferences, created = NotificationPreference.objects.get_or_create(
                user=user,
                defaults={
                    'email_lead_notifications': True,
                    'email_subscription_notifications': True,
                    'email_package_notifications': True,
                    'sms_lead_notifications': True,
                    'app_lead_notifications': True,
                    'email_marketing': True,
                    'sms_marketing': False,
                    'app_marketing': True,
                    'email_review_notifications': True,
                    'sms_review_notifications': False,
                    'app_review_notifications': True,
                    'sms_subscription_notifications': False,
                    'app_subscription_notifications': True,
                    'sms_package_notifications': False,
                    'app_package_notifications': True,
                }
            )
            return preferences
        except Exception as e:
            logger.error(f"Error getting user preferences: {str(e)}")
            # Return default preferences object
            return NotificationPreference(
                user=user,
                email_lead_notifications=True,
                email_subscription_notifications=True,
                email_package_notifications=True,
                sms_lead_notifications=True,
                app_lead_notifications=True,
                email_marketing=True,
                sms_marketing=False,
                app_marketing=True,
            )
    
    def _render_template(self, template: NotificationTemplate, data: Dict[str, Any]) -> Dict[str, str]:
        """Render notification template with data"""
        
        try:
            # Simple template rendering - you can enhance this with Django templates
            title = template.title or 'Notification'
            message = template.app_body or template.email_body or template.sms_body or 'You have a new notification'
            
            # Replace placeholders safely
            for key, value in data.items():
                if value is not None:
                    placeholder = f"{{{key}}}"
                    str_value = str(value)
                    title = title.replace(placeholder, str_value)
                    message = message.replace(placeholder, str_value)
            
            return {
                'title': title,
                'message': message,
                'email_subject': template.email_subject or title,
                'email_body': template.email_body or message,
                'sms_body': template.sms_body or message
            }
        except Exception as e:
            logger.error(f"Error rendering template: {str(e)}")
            return {
                'title': 'Notification',
                'message': 'You have a new notification',
                'email_subject': 'Notification',
                'email_body': 'You have a new notification',
                'sms_body': 'You have a new notification'
            }
    
    def _send_notification(self, notification: Notification, preferences: NotificationPreference) -> None:
        """Send notification through appropriate channels"""
        
        try:
            template = notification.template
            
            # Initialize status flags
            notification.email_sent = False
            notification.sms_sent = False
            notification.app_sent = False
            
            # Send email
            if template.send_email and self._should_send_email(notification, preferences):
                notification.email_sent = self.email_backend.send_email_notification(notification)
            
            # Send SMS
            if template.send_sms and self._should_send_sms(notification, preferences):
                notification.sms_sent = self.sms_backend.send_sms_notification(notification)
            
            # Send app notification
            if template.send_app and self._should_send_app(notification, preferences):
                notification.app_sent = self.app_backend.send_app_notification(notification)
            
            # Update notification status
            if notification.email_sent or notification.sms_sent or notification.app_sent:
                notification.mark_as_sent()
            else:
                notification.status = 'failed'
                notification.save()
                
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            notification.status = 'failed'
            notification.save()
    
    def _should_send_email(self, notification: Notification, preferences: NotificationPreference) -> bool:
        """Check if email should be sent based on preferences"""
        template_type = notification.template.notification_type
        
        preference_map = {
            'lead_received': getattr(preferences, 'email_lead_notifications', True),
            'subscription_expiry': getattr(preferences, 'email_subscription_notifications', True),
            'package_approved': getattr(preferences, 'email_package_notifications', True),
            'package_rejected': getattr(preferences, 'email_package_notifications', True),
            'new_review': getattr(preferences, 'email_review_notifications', True),
            'welcome': True,
            'payment_success': True,
            'payment_failed': True,
            'package_upload_reminder': getattr(preferences, 'email_package_notifications', True),
        }
        
        return preference_map.get(template_type, True)
    
    def _should_send_sms(self, notification: Notification, preferences: NotificationPreference) -> bool:
        """Check if SMS should be sent based on preferences"""
        template_type = notification.template.notification_type
        
        preference_map = {
            'lead_received': getattr(preferences, 'sms_lead_notifications', False),
            'subscription_expiry': getattr(preferences, 'sms_subscription_notifications', False),
            'package_approved': getattr(preferences, 'sms_package_notifications', False),
            'package_rejected': getattr(preferences, 'sms_package_notifications', False),
            'new_review': getattr(preferences, 'sms_review_notifications', False),
            'welcome': False,
            'payment_success': True,
            'payment_failed': True,
            'package_upload_reminder': False,
        }
        
        return preference_map.get(template_type, False)
    
    def _should_send_app(self, notification: Notification, preferences: NotificationPreference) -> bool:
        """Check if app notification should be sent based on preferences"""
        template_type = notification.template.notification_type
        
        preference_map = {
            'lead_received': getattr(preferences, 'app_lead_notifications', True),
            'subscription_expiry': getattr(preferences, 'app_subscription_notifications', True),
            'package_approved': getattr(preferences, 'app_package_notifications', True),
            'package_rejected': getattr(preferences, 'app_package_notifications', True),
            'new_review': getattr(preferences, 'app_review_notifications', True),
            'welcome': True,
            'payment_success': True,
            'payment_failed': True,
            'package_upload_reminder': getattr(preferences, 'app_package_notifications', True),
        }
        
        return preference_map.get(template_type, True)
    
    def _get_bulk_recipients(self, bulk_notification: BulkNotification) -> List[User]:
        """Get recipients for bulk notification"""
        
        try:
            queryset = User.objects.filter(is_active=True)
            
            # Filter by user type
            if bulk_notification.target_user_type == 'pilgrims':
                queryset = queryset.filter(role='pilgrim')
            elif bulk_notification.target_user_type == 'providers':
                queryset = queryset.filter(role='provider')
            elif bulk_notification.target_user_type == 'premium_providers':
                queryset = queryset.filter(
                    role='provider',
                    provider_profile__subscription__is_active=True,
                    provider_profile__subscription__plan_type='premium'
                )
            
            # Apply additional filters
            filters = bulk_notification.target_filters
            if filters:
                if filters.get('city'):
                    queryset = queryset.filter(city__icontains=filters['city'])
                if filters.get('state'):
                    queryset = queryset.filter(state__icontains=filters['state'])
                if filters.get('is_verified') is not None:
                    queryset = queryset.filter(is_verified=filters['is_verified'])
            
            return list(queryset)
            
        except Exception as e:
            logger.error(f"Error getting bulk recipients: {str(e)}")
            return []
    
    def _send_bulk_notification_to_user(
        self, 
        notification: Notification, 
        bulk_notification: BulkNotification,
        preferences: NotificationPreference
    ) -> bool:
        """Send bulk notification to a single user"""
        
        try:
            success = False
            
            # Send email
            if bulk_notification.send_email and getattr(preferences, 'email_marketing', True):
                email_success = self.email_backend.send_email_notification(notification)
                success = email_success or success
            
            # Send SMS
            if bulk_notification.send_sms and getattr(preferences, 'sms_marketing', False):
                sms_success = self.sms_backend.send_sms_notification(notification)
                success = sms_success or success
            
            # Send app notification
            if bulk_notification.send_app and getattr(preferences, 'app_marketing', True):
                app_success = self.app_backend.send_app_notification(notification)
                success = app_success or success
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending bulk notification to user: {str(e)}")
            return False
    
    def _get_default_template(self) -> NotificationTemplate:
        """Get default template for bulk notifications"""
        try:
            template, created = NotificationTemplate.objects.get_or_create(
                notification_type='bulk_notification',
                defaults={
                    'title': 'Notification',
                    'app_body': 'You have a new notification',
                    'email_body': 'You have a new notification',
                    'sms_body': 'You have a new notification',
                    'email_subject': 'Notification',
                    'send_email': True,
                    'send_sms': False,
                    'send_app': True,
                    'is_active': True,
                }
            )
            return template
        except Exception as e:
            logger.error(f"Error getting default template: {str(e)}")
            raise


class EmailNotificationBackend:
    """Backend for sending email notifications"""
    
    def send_email_notification(self, notification: Notification) -> bool:
        """Send email notification"""
        
        try:
            template = notification.template
            recipient = notification.recipient
            
            # Check if recipient has email
            if not recipient.email:
                logger.warning(f"No email address for user {recipient.id}")
                return False
            
            # Render email content
            subject = template.email_subject or notification.title
            message = template.email_body or notification.message
            
            # Replace placeholders safely
            for key, value in notification.data.items():
                if value is not None:
                    placeholder = f"{{{key}}}"
                    str_value = str(value)
                    subject = subject.replace(placeholder, str_value)
                    message = message.replace(placeholder, str_value)
            
            # Send email
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=[recipient.email],
                fail_silently=False
            )
            
            # Log the attempt
            self._log_notification_attempt(
                notification=notification,
                channel='email',
                success=True,
                provider='django_email'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
            self._log_notification_attempt(
                notification=notification,
                channel='email',
                success=False,
                provider='django_email',
                error_message=str(e)
            )
            return False
    
    def _log_notification_attempt(
        self, 
        notification: Notification,
        channel: str,
        success: bool,
        provider: str,
        error_message: Optional[str] = None
    ) -> None:
        """Log notification attempt"""
        
        try:
            NotificationLog.objects.create(
                notification=notification,
                channel=channel,
                delivered=success,
                delivered_at=timezone.now() if success else None,
                provider=provider,
                error_message=error_message or '',
                provider_response={}
            )
        except Exception as e:
            logger.error(f"Error logging notification attempt: {str(e)}")


class SMSNotificationBackend:
    """Backend for sending SMS notifications"""
    
    def send_sms_notification(self, notification: Notification) -> bool:
        """Send SMS notification"""
        
        try:
            template = notification.template
            recipient = notification.recipient
            
            # Check if user has phone number
            if not hasattr(recipient, 'phone_number') or not recipient.phone_number:
                logger.warning(f"No phone number for user {recipient.email}")
                return False
            
            # Render SMS content
            message = template.sms_body or notification.message
            
            # Replace placeholders safely
            for key, value in notification.data.items():
                if value is not None:
                    placeholder = f"{{{key}}}"
                    str_value = str(value)
                    message = message.replace(placeholder, str_value)
            
            # Truncate message if too long
            if len(message) > 160:
                message = message[:157] + "..."
            
            # Send SMS using external provider
            success = self._send_sms_via_provider(recipient.phone_number, message)
            
            # Log the attempt
            self._log_notification_attempt(
                notification=notification,
                channel='sms',
                success=success,
                provider='twilio'
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending SMS notification: {str(e)}")
            self._log_notification_attempt(
                notification=notification,
                channel='sms',
                success=False,
                provider='twilio',
                error_message=str(e)
            )
            return False
    
    def _send_sms_via_provider(self, phone_number: str, message: str) -> bool:
        """Send SMS via external provider (Twilio, etc.)"""
        
        try:
            # Check if Twilio is configured
            if hasattr(settings, 'TWILIO_ACCOUNT_SID') and settings.TWILIO_ACCOUNT_SID:
                try:
                    # Uncomment and configure for production use
                    # from twilio.rest import Client
                    # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                    # message = client.messages.create(
                    #     body=message,
                    #     from_=settings.TWILIO_PHONE_NUMBER,
                    #     to=phone_number
                    # )
                    # return True
                    
                    # For development, just log the attempt
                    logger.info(f"SMS would be sent to {phone_number}: {message}")
                    return True
                    
                except Exception as e:
                    logger.error(f"Twilio SMS error: {str(e)}")
                    return False
            else:
                logger.warning("Twilio configuration not found")
                return False
                
        except Exception as e:
            logger.error(f"Error in SMS provider: {str(e)}")
            return False
    
    def _log_notification_attempt(
        self, 
        notification: Notification,
        channel: str,
        success: bool,
        provider: str,
        error_message: Optional[str] = None
    ) -> None:
        """Log notification attempt"""
        
        try:
            NotificationLog.objects.create(
                notification=notification,
                channel=channel,
                delivered=success,
                delivered_at=timezone.now() if success else None,
                provider=provider,
                error_message=error_message or '',
                provider_response={}
            )
        except Exception as e:
            logger.error(f"Error logging notification attempt: {str(e)}")


class AppNotificationBackend:
    """Backend for sending app notifications (push notifications)"""
    
    def send_app_notification(self, notification: Notification) -> bool:
        """Send app notification"""
        
        try:
            # For development, just mark as sent
            # In production, integrate with Firebase Cloud Messaging (FCM)
            # or Apple Push Notification Service (APNS)
            
            # Example FCM integration:
            # from firebase_admin import messaging
            # message = messaging.Message(
            #     notification=messaging.Notification(
            #         title=notification.title,
            #         body=notification.message,
            #     ),
            #     token=user_device_token,
            # )
            # response = messaging.send(message)
            
            self._log_notification_attempt(
                notification=notification,
                channel='app',
                success=True,
                provider='fcm'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending app notification: {str(e)}")
            self._log_notification_attempt(
                notification=notification,
                channel='app',
                success=False,
                provider='fcm',
                error_message=str(e)
            )
            return False
    
    def _log_notification_attempt(
        self, 
        notification: Notification,
        channel: str,
        success: bool,
        provider: str,
        error_message: Optional[str] = None
    ) -> None:
        """Log notification attempt"""
        
        try:
            NotificationLog.objects.create(
                notification=notification,
                channel=channel,
                delivered=success,
                delivered_at=timezone.now() if success else None,
                provider=provider,
                error_message=error_message or '',
                provider_response={}
            )
        except Exception as e:
            logger.error(f"Error logging notification attempt: {str(e)}")


# Helper functions for common notification scenarios
def send_lead_notification(lead_instance, providers: List[User]) -> None:
    """Send lead notification to providers"""
    
    service = NotificationService()
    
    for provider in providers:
        try:
            service.create_notification(
                recipient=provider,
                template_type='lead_received',
                data={
                    'lead_id': lead_instance.id,
                    'customer_name': getattr(lead_instance, 'customer_name', 'Unknown'),
                    'customer_phone': getattr(lead_instance, 'customer_phone', 'Not provided'),
                    'service_type': getattr(lead_instance, 'service_type', 'Not specified'),
                    'travel_date': lead_instance.travel_date.strftime('%Y-%m-%d') if getattr(lead_instance, 'travel_date', None) else 'Not specified',
                    'budget': getattr(lead_instance, 'budget', None) or 'Not specified',
                    'location': getattr(lead_instance, 'location', None) or 'Not specified',
                },
                priority='high'
            )
        except Exception as e:
            logger.error(f"Error sending lead notification to {provider.email}: {str(e)}")


def send_subscription_expiry_notification(provider: User, days_remaining: int) -> None:
    """Send subscription expiry notification"""
    
    try:
        service = NotificationService()
        
        service.create_notification(
            recipient=provider,
            template_type='subscription_expiry',
            data={
                'provider_name': provider.get_full_name(),
                'days_remaining': days_remaining,
                'renewal_url': f"{getattr(settings, 'FRONTEND_URL', '')}/subscription/renew",
            },
            priority='high' if days_remaining <= 3 else 'medium'
        )
    except Exception as e:
        logger.error(f"Error sending subscription expiry notification: {str(e)}")


def send_package_approval_notification(package_instance, is_approved: bool) -> None:
    """Send package approval/rejection notification"""
    
    try:
        service = NotificationService()
        
        template_type = 'package_approved' if is_approved else 'package_rejected'
        
        service.create_notification(
            recipient=package_instance.provider,
            template_type=template_type,
            data={
                'package_name': getattr(package_instance, 'name', 'Unknown Package'),
                'package_id': package_instance.id,
                'provider_name': package_instance.provider.get_full_name(),
                'review_comment': getattr(package_instance, 'review_comment', ''),
            },
            priority='medium'
        )
    except Exception as e:
        logger.error(f"Error sending package approval notification: {str(e)}")


def send_review_notification(review_instance) -> None:
    """Send new review notification to provider"""
    
    try:
        service = NotificationService()
        
        review_text = getattr(review_instance, 'review_text', '')
        truncated_review = review_text[:100] + '...' if len(review_text) > 100 else review_text
        
        service.create_notification(
            recipient=review_instance.provider,
            template_type='new_review',
            data={
                'reviewer_name': review_instance.reviewer.get_full_name(),
                'rating': getattr(review_instance, 'rating', 'Not rated'),
                'review_text': truncated_review,
                'package_name': getattr(review_instance.package, 'name', 'Service') if getattr(review_instance, 'package', None) else 'Service',
            },
            priority='low'
        )
    except Exception as e:
        logger.error(f"Error sending review notification: {str(e)}")


def send_welcome_notification(user: User) -> None:
    """Send welcome notification to new user"""
    
    try:
        service = NotificationService()
        
        service.create_notification(
            recipient=user,
            template_type='welcome',
            data={
                'user_name': user.get_full_name(),
                'user_email': user.email,
                'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/dashboard",
            },
            priority='low'
        )
    except Exception as e:
        logger.error(f"Error sending welcome notification: {str(e)}")


def send_payment_notification(payment_instance, is_success: bool) -> None:
    """Send payment success/failure notification"""
    
    try:
        service = NotificationService()
        
        template_type = 'payment_success' if is_success else 'payment_failed'
        
        service.create_notification(
            recipient=payment_instance.user,
            template_type=template_type,
            data={
                'amount': getattr(payment_instance, 'amount', 'N/A'),
                'payment_id': payment_instance.id,
                'transaction_id': getattr(payment_instance, 'transaction_id', 'N/A'),
                'service_name': getattr(payment_instance, 'service_name', 'Service'),
                'payment_date': payment_instance.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(payment_instance, 'created_at') else 'N/A',
            },
            priority='medium'
        )
    except Exception as e:
        logger.error(f"Error sending payment notification: {str(e)}")


def send_package_upload_reminder(provider: User) -> None:
    """Send reminder to upload packages"""
    
    try:
        service = NotificationService()
        
        service.create_notification(
            recipient=provider,
            template_type='package_upload_reminder',
            data={
                'provider_name': provider.get_full_name(),
                'upload_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/packages/create",
            },
            priority='low'
        )
    except Exception as e:
        logger.error(f"Error sending package upload reminder: {str(e)}")