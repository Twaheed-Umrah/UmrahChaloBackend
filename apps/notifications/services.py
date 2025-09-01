import logging
import os
import re
from typing import Dict, Any, Optional, List
from django.template.loader import render_to_string, get_template
from django.template import TemplateDoesNotExist
from django.core.mail import EmailMultiAlternatives, send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.core.exceptions import ValidationError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import socket

from .models import Notification, NotificationPreference, NotificationLog

logger = logging.getLogger(__name__)


class NotificationService:
    """Main service for handling all notification types with multi-channel support"""
    
    @staticmethod
    def create_notification(
        recipient,
        notification_type: str,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        related_object=None,
        priority: str = 'medium',
        send_immediately: bool = True
    ) -> Notification:
        """Create a new notification with robust error handling"""
        try:
            with transaction.atomic():
                # Clean notification type - remove any extensions
                clean_notification_type = notification_type.replace('.html', '').replace('.txt', '')
                
                # Get or create user preferences
                preferences, _ = NotificationPreference.objects.get_or_create(
                    user=recipient,
                    defaults={}
                )
                
                # Determine channels based on user preferences
                send_email = preferences.get_channel_preference(clean_notification_type, 'email')
                send_sms = preferences.get_channel_preference(clean_notification_type, 'sms')
                send_app = preferences.get_channel_preference(clean_notification_type, 'app')
                
                # Create notification
                notification = Notification.objects.create(
                    recipient=recipient,
                    notification_type=clean_notification_type,
                    title=title,
                    message=message,
                    data=data or {},
                    priority=priority,
                    send_email=send_email,
                    send_sms=send_sms,
                    send_app=send_app,
                    content_object=related_object
                )
                
                if send_immediately:
                    # Always send synchronously to avoid Celery issues
                    NotificationService.send_notification(notification.id)
                
                return notification
                
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            # Create a minimal notification to prevent cascade failures
            try:
                notification = Notification.objects.create(
                    recipient=recipient,
                    notification_type=clean_notification_type,
                    title=title,
                    message=message,
                    data=data or {},
                    priority=priority,
                    send_email=False,
                    send_sms=False,
                    send_app=True,  # Keep app notification
                    content_object=related_object,
                    status='failed'
                )
                return notification
            except Exception as inner_e:
                logger.error(f"Failed to create fallback notification: {inner_e}")
                raise inner_e
    
    @staticmethod
    def send_notification(notification_id: int) -> bool:
        """Send notification through all enabled channels synchronously"""
        try:
            notification = Notification.objects.get(id=notification_id)
            
            if notification.status != 'pending':
                logger.info(f"Notification {notification_id} already processed with status: {notification.status}")
                return True
            
            success_count = 0
            total_channels = 0
            
            # Send email
            if notification.send_email:
                total_channels += 1
                try:
                    email_success = EmailNotificationService.send_email(notification)
                    notification.email_sent = email_success
                    if email_success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"Email sending failed: {e}")
                    notification.email_sent = False
            
            # Send SMS
            if notification.send_sms:
                total_channels += 1
                try:
                    sms_success = SMSNotificationService.send_sms(notification)
                    notification.sms_sent = sms_success
                    if sms_success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"SMS sending failed: {e}")
                    notification.sms_sent = False
            
            # Send app notification (in-app) - This should always work
            if notification.send_app:
                total_channels += 1
                try:
                    app_success = AppNotificationService.send_app_notification(notification)
                    notification.app_sent = app_success
                    if app_success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"App notification failed: {e}")
                    notification.app_sent = False
            
            # Update notification status - consider it successful if any channel worked
            if success_count > 0:
                notification.mark_as_sent()
                logger.info(f"Notification {notification_id} marked as sent ({success_count}/{total_channels} channels successful)")
            else:
                notification.mark_as_failed()
                logger.warning(f"Notification {notification_id} marked as failed (0/{total_channels} channels successful)")
            
            notification.save()
            return success_count > 0
            
        except Notification.DoesNotExist:
            logger.error(f"Notification {notification_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error sending notification {notification_id}: {str(e)}")
            return False
    
    # ============ NOTIFICATION TYPE HANDLERS ============
    
    @staticmethod
    def send_lead_received_notification(lead, provider):
        """Send lead received notification to provider"""
        try:
            return NotificationService.create_notification(
                recipient=provider,
                notification_type='lead_received',
                title="New Lead Received!",
                message=f"You have received a new lead from {lead.full_name}",
                data={
                    'lead_id': lead.id,
                    'pilgrim_name': lead.full_name,
                    'pilgrim_phone': lead.phone or 'N/A',
                    'pilgrim_email': lead.email or 'N/A',
                    'package_name': lead.package.name if lead.package else 'General Inquiry',
                    'message': getattr(lead, 'message', ''),
                    'created_at': lead.created_at.strftime('%Y-%m-%d %H:%M'),
                    'provider_name': getattr(provider, 'business_name', provider.full_name),
                },
                related_object=lead,
                priority='high'
            )
        except Exception as e:
            logger.error(f"Failed to send lead notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_new_review_notification(review):
        """Send new review notification to provider"""
        try:
            return NotificationService.create_notification(
                recipient=review.provider,
                notification_type='new_review',
                title="New Review Received!",
                message=f"You received a {review.rating}-star review from {review.user.full_name}",
                data={
                    'reviewer_name': review.user.full_name,
                    'rating': review.rating,
                    'comment': getattr(review, 'comment', ''),
                    'package_name': review.package.name if review.package else '',
                    'review_id': review.id,
                    'provider_name': getattr(review.provider, 'business_name', review.provider.full_name),
                },
                related_object=review,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send review notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_package_approved_notification(package):
        """Send package approved notification"""
        from decimal import Decimal
        try:
            provider = package.provider  # ServiceProviderProfile
            provider_user = provider.user  # User instance
            provider_name = getattr(provider, 'business_name', None) or provider_user.get_full_name()

        # Ensure all values are JSON serializable
            duration = int(package.duration_days) if package.duration_days is not None else None
            price = float(package.final_price) if isinstance(package.final_price, Decimal) else package.final_price

            return NotificationService.create_notification(
                recipient=provider_user,  # ✅ pass user, not profile
                notification_type='package_approved',
                title="Package Approved!",
                message=f"Your package '{package.name}' has been approved and is now live.",
                data={
                    'package_name': package.name or package.title ,
                    'package_id': package.id,
                    'provider_name': provider_name,
                    "package_duration": duration,
                    "package_price": price,
                    'package_url': f"{getattr(settings, 'FRONTEND_URL', '')}/package/{package.id}",
                    'approved_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
             },
                related_object=package,
                priority='medium'
         )
        except Exception as e:
            logger.error(f"Failed to send package approved notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})

    @staticmethod
    def send_package_rejected_notification(package, rejection_reason=""):
        """Send package rejected notification"""
        
        provider = package.provider  # ServiceProviderProfile
        provider_user = provider.user  # User instance
        provider_name = getattr(provider, 'business_name', None) or provider_user.get_full_name()
        try:
            return NotificationService.create_notification(
                recipient=provider_user,  # ✅ pass user, not profile
                notification_type='package_rejected',  # 🔄 corrected
                title="Package Rejected",
                message=f"Your package '{package.name}' has been rejected. Please review and resubmit.",
                data={
                    'package_name': package.name or package.title,
                    'package_id': package.id,
                    'provider_name': provider_name,
                    'rejection_reason': rejection_reason,
                    'rejected_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
                },
                related_object=package,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send package rejected notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    @staticmethod
    def send_service_approved_notification(service):
        """Send service approved notification"""
        from decimal import Decimal
        try:
            provider = service.provider  # ServiceProviderProfile
            provider_user = provider.user  # User instance
            provider_name = getattr(provider, 'business_name', None) or provider_user.get_full_name()

            # Ensure JSON serializable values
            price = float(service.price) if isinstance(service.price, Decimal) else service.price

            return NotificationService.create_notification(
                recipient=provider_user,  # ✅ pass user, not profile
                notification_type='services_approved',
                title="Service Approved!",
                message=f"Your service '{service.title}' has been approved and is now live.",
                data={
                    'service_title': service.title,
                    'service_id': service.id,
                    'provider_name': provider_name,
                    "service_price": price,
                    "service_currency": service.price_currency,
                    "service_duration": service.duration or "",
                    'service_url': f"{getattr(settings, 'FRONTEND_URL', '')}/service/{service.slug}",
                    'approved_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
                },
                related_object=service,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send service approved notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})

    @staticmethod
    def send_service_rejected_notification(service, rejection_reason=""):
        """Send service rejected notification"""
        try:
            provider = service.provider
            provider_user = provider.user
            provider_name = getattr(provider, 'business_name', None) or provider_user.get_full_name()

            return NotificationService.create_notification(
                recipient=provider_user,
                notification_type='services_rejected',
                title="Service Rejected",
                message=f"Your service '{service.title}' has been rejected. Please review and resubmit.",
                data={
                    'service_title': service.title,
                    'service_id': service.id,
                    'provider_name': provider_name,
                    'rejection_reason': rejection_reason,
                    'rejected_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
                },
                related_object=service,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send service rejected notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
   
    @staticmethod
    def send_package_upload_reminder_notification(provider):
        """Send package upload reminder notification"""
        try:
            return NotificationService.create_notification(
                recipient=provider,
                notification_type='package_upload_reminder',
                title="Upload New Packages",
                message="It's been a while since you uploaded new packages. Upload fresh packages to attract more customers!",
                data={
                    'provider_name': getattr(provider, 'business_name', provider.full_name),
                    'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/dashboard/",
                    'upload_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/packages/create",
                },
                related_object=provider,
                priority='low'
            )
        except Exception as e:
            logger.error(f"Failed to send package upload reminder: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_password_reset_notification(user, reset_token, reset_url):
        """Send password reset notification"""
        try:
            return NotificationService.create_notification(
                recipient=user,
                notification_type='password_reset',
                title="Password Reset Request",
                message="You requested a password reset. Click the link in your email to reset your password.",
                data={
                    'user_name': user.full_name or user.email,
                    'reset_token': reset_token,
                    'reset_url': reset_url,
                    'expires_at': (timezone.now() + timezone.timedelta(hours=24)).strftime('%Y-%m-%d %H:%M'),
                },
                related_object=user,
                priority='high'
            )
        except Exception as e:
            logger.error(f"Failed to send password reset notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    @staticmethod
    def send_payment_failed_notification(payment):
        """Send payment failed notification"""
        try:
            return NotificationService.create_notification(
                recipient=payment.user,
                notification_type='payment_failed',
                title="Payment Failed",
                message=f"Your payment of ₹{payment.amount} has failed. Please try again.",
                data={
                    'amount': str(payment.amount),  # ensure JSON serializable
                    'payment_id': payment.id,
                    'payment_method': str(payment.payment_method) if payment.payment_method else "N/A",
                    'transaction_id': getattr(payment, 'transaction_id', 'N/A'),
                    'failure_reason': getattr(payment, 'failure_reason', 'Unknown'),
                    'retry_url': f"{getattr(settings, 'FRONTEND_URL', '')}/payment/retry/{payment.id}",
                },
                related_object=payment,
                priority='high'
            )
        except Exception as e:
            logger.error(f"Failed to send payment failed notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})

    @staticmethod
    def send_payment_success_notification(payment):
        try:
            amount = float(payment.total_amount)  # Convert Decimal to float (or str)
    
            return NotificationService.create_notification(
                recipient=payment.user,
                notification_type='payment_success',
                title="Payment Successful!",
                message=f"Your payment of ₹{amount} has been processed successfully.",
                data={
                    'amount': str(amount),
                    'payment_id': payment.id,
                    'payment_method': str(payment.payment_method) if payment.payment_method else None,
                    'transaction_id': payment.gateway_payment_id,
                    'receipt_url': f"{getattr(settings, 'FRONTEND_URL', '')}/payment/receipt/{payment.id}",
                    'processed_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
                },
                related_object=payment,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send payment success notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})    
    @staticmethod
    def send_subscription_expiry_notification(subscription):
        """Send subscription expiry notification"""
        try:
            days_left = (subscription.end_date - timezone.now().date()).days
            
            return NotificationService.create_notification(
                recipient=subscription.user,
                notification_type='subscription_expiry',
                title=f"Subscription Expiring in {days_left} days",
                message=f"Your {subscription.plan.name} subscription will expire on {subscription.end_date}",
                data={
                    'plan_name': subscription.plan.name,
                    'end_date': subscription.end_date.strftime('%Y-%m-%d'),
                    'days_left': days_left,
                    'subscription_id': subscription.id,
                    'renewal_url': f"{getattr(settings, 'FRONTEND_URL', '')}/subscription/renew/{subscription.id}",
                    'pricing_url': f"{getattr(settings, 'FRONTEND_URL', '')}/pricing",
                },
                related_object=subscription,
                priority='high'
            )
        except Exception as e:
            logger.error(f"Failed to send subscription expiry notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_subscription_reminder_notification(subscription, days_before_expiry=3):
        """Send subscription reminder notification"""
        try:
            return NotificationService.create_notification(
                recipient=subscription.user,
                notification_type='subscription_reminder',
                title=f"Subscription Renewal Reminder",
                message=f"Don't forget to renew your {subscription.plan.name} subscription before it expires in {days_before_expiry} days",
                data={
                    'plan_name': subscription.plan.name,
                    'end_date': subscription.end_date.strftime('%Y-%m-%d'),
                    'days_left': days_before_expiry,
                    'subscription_id': subscription.id,
                    'renewal_url': f"{getattr(settings, 'FRONTEND_URL', '')}/subscription/renew/{subscription.id}",
                    'benefits': getattr(subscription.plan, 'features', []),
                },
                related_object=subscription,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send subscription reminder: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_verification_complete_notification(provider):
       """Send verification complete notification"""
       try:
           business_name = getattr(provider, 'business_name', 'N/A')

           return NotificationService.create_notification(
               recipient=provider.user,  # ✅ must be a User instance
               notification_type='verification_complete',
               title="Verification Complete!",
               message="Your service provider profile has been verified successfully.",
               data={
                   'business_name': business_name,
                   'verification_date': timezone.now().strftime('%Y-%m-%d'),
                   'provider_name': provider.user.full_name or business_name,  # ✅ fetch from User
                   'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/dashboard/",
               },
               related_object=provider,
               priority='medium'
           )
       except Exception as e:
           logger.error(f"Failed to send verification notification: {e}")
           return type('MockNotification', (), {'id': 0, 'status': 'failed'})

    @staticmethod
    def send_welcome_notification(user):
        """Send welcome notification to new user"""
        try:
            user_type_display = 'User'
            if hasattr(user, 'user_type'):
                user_type_display = user.get_user_type_display() if hasattr(user, 'get_user_type_display') else user.user_type.title()
            
            return NotificationService.create_notification(
                recipient=user,
                notification_type='welcome',
                title=f"Welcome to Umrah Chalo, {user.full_name or user.email}!",
                message="Thank you for joining our platform. We're excited to have you!",
                data={
                    'user_name': user.full_name or user.email,
                    'user_type': user_type_display,
                    'profile_url': f"{getattr(settings, 'FRONTEND_URL', '')}/profile/",
                    'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/dashboard/",
                    'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@umrahchalo.com'),
                },
                related_object=user,
                priority='medium'
            )
        except Exception as e:
            logger.error(f"Failed to send welcome notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})


class EmailNotificationService:
    """Service for handling email notifications with improved error handling"""
    
    @staticmethod
    def is_email_configured() -> bool:
        """Check if email is properly configured"""
        try:
            required_settings = ['EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'EMAIL_HOST']
            for setting in required_settings:
                if not hasattr(settings, setting) or not getattr(settings, setting):
                    return False
            return True
        except:
            return False
    @staticmethod
    def send_manual_notification(user_ids, notification_type, title, message, 
                               data=None, priority='medium', channels=None):
        """Send manual notification to specific users (for superadmin)"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            users = User.objects.filter(id__in=user_ids)
            notifications_created = []
            
            for user in users:
                notification = NotificationService.create_notification(
                    recipient=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    data=data,
                    priority=priority,
                )
                if notification:
                    notifications_created.append(notification)
            
            logger.info(f"Created {len(notifications_created)} manual notifications")
            return notifications_created
            
        except Exception as e:
            logger.error(f"Failed to send manual notifications: {e}")
            return []

    @staticmethod
    def test_smtp_connection() -> bool:
        """Test SMTP connection with timeout"""
        try:
            if not EmailNotificationService.is_email_configured():
                return False
                
            # Set a timeout to prevent hanging
            server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10)
            
            if hasattr(settings, 'EMAIL_USE_TLS') and settings.EMAIL_USE_TLS:
                server.starttls()
            elif hasattr(settings, 'EMAIL_USE_SSL') and settings.EMAIL_USE_SSL:
                server = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10)
            
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.quit()
            return True
        except (smtplib.SMTPException, socket.error, OSError) as e:
            logger.warning(f"SMTP connection test failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"Email configuration test failed: {e}")
            return False
    
    @staticmethod
    def clean_subject_line(subject: str) -> str:
        """Clean email subject line to remove newlines and extra whitespace"""
        if not subject:
            return "Notification from Umrah Chalo"
        
        # Remove newlines and normalize whitespace
        cleaned = re.sub(r'\s+', ' ', subject.replace('\n', ' ').replace('\r', ' '))
        cleaned = cleaned.strip()
        
        # Limit length
        if len(cleaned) > 200:
            cleaned = cleaned[:197] + "..."
        
        return cleaned
    
    @staticmethod
    def get_template_paths(notification_type: str) -> Dict[str, List[str]]:
        """Get all possible template paths for a notification type"""
        clean_type = notification_type.replace('.html', '').replace('.txt', '')
        
        return {
            'subject': [
                f"notifications/email/{clean_type}_subject.txt",
                f"notifications/email/{clean_type}/subject.txt",
                f"notifications/{clean_type}_subject.txt",
                f"templates/notifications/email/{clean_type}_subject.txt",
            ],
            'text': [
                f"notifications/email/{clean_type}.txt",
                f"notifications/{clean_type}.txt",
                f"templates/notifications/{clean_type}.txt",
                f"templates/notifications/email/{clean_type}.txt",
            ],
            'html': [
                f"notifications/email/{clean_type}.html",
                f"notifications/{clean_type}.html",
                f"templates/notifications/email/{clean_type}.html",
                f"templates/notifications/{clean_type}.html",
            ]
        }
    
    @staticmethod
    def render_template_safe(template_paths: List[str], context: dict) -> Optional[str]:
        """Safely render template from list of possible paths"""
        for template_path in template_paths:
            try:
                content = render_to_string(template_path, context).strip()
                if content:  # Only return non-empty content
                    logger.info(f"Using email template: {template_path}")
                    return content
            except TemplateDoesNotExist:
                continue
            except Exception as e:
                logger.warning(f"Error rendering template {template_path}: {e}")
                continue
        return None
    
    @staticmethod
    def send_email(notification: Notification) -> bool:
        """Send email notification with comprehensive error handling"""
        try:
            # Validate recipient email
            if not notification.recipient.email:
                logger.warning(f"No email address for user {notification.recipient.id}")
                return False
            
            # Check email configuration
            if not EmailNotificationService.is_email_configured():
                logger.warning("Email not configured properly, using console backend")
                return EmailNotificationService.send_console_email(notification)
            
            # Test SMTP connection (with timeout for production)
            if getattr(settings, 'ENVIRONMENT', 'development') == 'production':
                if not EmailNotificationService.test_smtp_connection():
                    logger.warning("SMTP connection failed, using console backend")
                    return EmailNotificationService.send_console_email(notification)
            
            # Get template paths
            template_paths = EmailNotificationService.get_template_paths(notification.notification_type)
            
            # Prepare context
            context = {
                'notification': notification,
                'user': notification.recipient,
                'recipient': notification.recipient,
                'site_name': getattr(settings, 'SITE_NAME', 'Umrah Chalo'),
                'site_url': getattr(settings, 'SITE_URL', 'https://umrahchalo.com'),
                'frontend_url': getattr(settings, 'FRONTEND_URL', 'https://umrahchalo.com'),
                **notification.data
            }
            
            # Get email subject
            subject = EmailNotificationService.render_template_safe(template_paths['subject'], context)
            if not subject:
                subject = notification.title
            subject = EmailNotificationService.clean_subject_line(subject)
            
            # Get email body (text)
            text_body = EmailNotificationService.render_template_safe(template_paths['text'], context)
            if not text_body:
                text_body = notification.message
            
            # Get HTML body (optional)
            html_body = EmailNotificationService.render_template_safe(template_paths['html'], context)
            
            # Send email
            try:
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@umrahchalo.com')
                
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    from_email=from_email,
                    to=[notification.recipient.email]
                )
                
                if html_body:
                    email.attach_alternative(html_body, "text/html")
                
                email.send(fail_silently=False)
                
                # Log success
                NotificationLog.objects.create(
                    notification=notification,
                    channel='email',
                    delivered=True,
                    provider='django_email'
                )
                
                logger.info(f"Email sent successfully to {notification.recipient.email} for {notification.notification_type}")
                return True
                
            except Exception as send_error:
                logger.error(f"Failed to send email: {send_error}")
                return EmailNotificationService.send_console_email(notification)
                
        except Exception as e:
            logger.error(f"Error in email service for notification {notification.id}: {str(e)}")
            return EmailNotificationService.send_console_email(notification)
    
    @staticmethod
    def send_console_email(notification: Notification) -> bool:
        """Fallback to console email for development"""
        try:
            logger.info(f"=== EMAIL NOTIFICATION ({notification.notification_type}) ===")
            logger.info(f"To: {notification.recipient.email}")
            logger.info(f"Subject: {notification.title}")
            logger.info(f"Message: {notification.message}")
            logger.info(f"Type: {notification.notification_type}")
            logger.info(f"Data: {notification.data}")
            logger.info(f"========================================")
            
            # Log as successful for development
            NotificationLog.objects.create(
                notification=notification,
                channel='email',
                delivered=True,
                provider='console_email',
                error_message='Using console backend'
            )
            
            return True
        except Exception as e:
            logger.error(f"Console email failed: {e}")
            return False


class SMSNotificationService:
    """Service for handling SMS notifications"""
    
    @staticmethod
    def get_template_paths(notification_type: str) -> List[str]:
        """Get SMS template paths"""
        clean_type = notification_type.replace('.html', '').replace('.txt', '')
        return [
            f"notifications/sms/{clean_type}.txt",
            f"notifications/{clean_type}_sms.txt",
            f"templates/notifications/sms/{clean_type}.txt",
        ]
    
    @staticmethod
    def render_template_safe(template_paths: List[str], context: dict) -> Optional[str]:
        """Safely render SMS template"""
        for template_path in template_paths:
            try:
                content = render_to_string(template_path, context).strip()
                if content:
                    logger.info(f"Using SMS template: {template_path}")
                    return content
            except TemplateDoesNotExist:
                continue
            except Exception as e:
                logger.warning(f"Error rendering SMS template {template_path}: {e}")
                continue
        return None
    
    @staticmethod
    def send_sms(notification: Notification) -> bool:
        """Send SMS notification"""
        try:
            if not notification.recipient.phone:
                logger.warning(f"No phone number for user {notification.recipient.id}")
                return False
            
            # Get template paths
            template_paths = SMSNotificationService.get_template_paths(notification.notification_type)
            
            # Prepare context
            context = {
                'notification': notification,
                'user': notification.recipient,
                'recipient': notification.recipient,
                'site_name': getattr(settings, 'SITE_NAME', 'Umrah Chalo'),
                **notification.data
            }
            
            # Get SMS content
            sms_content = SMSNotificationService.render_template_safe(template_paths, context)
            if not sms_content:
                sms_content = notification.message
            
            # Truncate SMS to 160 characters if needed
            if len(sms_content) > 160:
                sms_content = sms_content[:157] + "..."
            
            # TODO: Integrate with actual SMS provider (Twilio, etc.)
            # For now, log the SMS
            logger.info(f"=== SMS NOTIFICATION ({notification.notification_type}) ===")
            logger.info(f"To: {notification.recipient.phone}")
            logger.info(f"Message: {sms_content}")
            logger.info(f"======================================")
            
            # Log success
            NotificationLog.objects.create(
                notification=notification,
                channel='sms',
                delivered=True,
                provider='console_sms'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending SMS for notification {notification.id}: {str(e)}")
            
            # Log failure
            try:
                NotificationLog.objects.create(
                    notification=notification,
                    channel='sms',
                    delivered=False,
                    error_message=str(e),
                    provider='console_sms'
                )
            except:
                pass
            
            return False


class AppNotificationService:
    """Service for handling in-app notifications"""
    
    @staticmethod
    def get_template_paths(notification_type: str) -> List[str]:
        """Get app notification template paths"""
        clean_type = notification_type.replace('.html', '').replace('.txt', '')
        return [
            f"notifications/app/{clean_type}.txt",
            f"notifications/{clean_type}_app.txt",
            f"templates/notifications/app/{clean_type}.txt",
        ]
    
    @staticmethod
    def render_template_safe(template_paths: List[str], context: dict) -> Optional[str]:
        """Safely render app notification template"""
        for template_path in template_paths:
            try:
                content = render_to_string(template_path, context).strip()
                if content:
                    logger.info(f"Using app template: {template_path}")
                    return content
            except TemplateDoesNotExist:
                continue
            except Exception as e:
                logger.warning(f"Error rendering app template {template_path}: {e}")
                continue
        return None
    
    @staticmethod
    def send_app_notification(notification: Notification) -> bool:
        """Send in-app notification"""
        try:
            # Get template paths
            template_paths = AppNotificationService.get_template_paths(notification.notification_type)
            
            # Prepare context
            context = {
                'notification': notification,
                'user': notification.recipient,
                'recipient': notification.recipient,
                'site_name': getattr(settings, 'SITE_NAME', 'Umrah Chalo'),
                **notification.data
            }
            
            # Try to get app notification template
            rendered_content = AppNotificationService.render_template_safe(template_paths, context)
            if rendered_content:
                notification.message = rendered_content
                notification.save(update_fields=['message'])
            
            # Log success
            NotificationLog.objects.create(
                notification=notification,
                channel='app',
                delivered=True,
                provider='in_app'
            )
            
            logger.info(f"App notification processed for user {notification.recipient.id} ({notification.notification_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error processing app notification {notification.id}: {str(e)}")
            
            # Log failure
            try:
                NotificationLog.objects.create(
                    notification=notification,
                    channel='app',
                    delivered=False,
                    error_message=str(e),
                    provider='in_app'
                )
            except:
                pass
            
            return False


# ============ INTEGRATION WITH TWILIO FOR SMS ============

class TwilioSMSService:
    """Production SMS service using Twilio"""
    
    @staticmethod
    def is_configured() -> bool:
        """Check if Twilio is properly configured"""
        required_settings = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER']
        return all(hasattr(settings, setting) and getattr(settings, setting) for setting in required_settings)
    
    @staticmethod
    def send_sms(notification: Notification) -> bool:
        """Send SMS using Twilio"""
        try:
            if not TwilioSMSService.is_configured():
                logger.warning("Twilio not configured, falling back to console SMS")
                return SMSNotificationService.send_sms(notification)
            
            from twilio.rest import Client
            
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            # Get SMS content
            template_paths = SMSNotificationService.get_template_paths(notification.notification_type)
            context = {
                'notification': notification,
                'user': notification.recipient,
                'recipient': notification.recipient,
                'site_name': getattr(settings, 'SITE_NAME', 'Umrah Chalo'),
                **notification.data
            }
            
            sms_content = SMSNotificationService.render_template_safe(template_paths, context)
            if not sms_content:
                sms_content = notification.message
            
            # Truncate SMS to 160 characters if needed
            if len(sms_content) > 160:
                sms_content = sms_content[:157] + "..."
            
            # Send SMS
            message = client.messages.create(
                body=sms_content,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=notification.recipient.phone
            )
            
            # Log success
            NotificationLog.objects.create(
                notification=notification,
                channel='sms',
                delivered=True,
                provider='twilio',
                provider_response={'message_sid': message.sid, 'status': message.status}
            )
            
            logger.info(f"SMS sent successfully via Twilio to {notification.recipient.phone}")
            return True
            
        except Exception as e:
            logger.error(f"Twilio SMS failed: {e}")
            
            # Log failure
            try:
                NotificationLog.objects.create(
                    notification=notification,
                    channel='sms',
                    delivered=False,
                    error_message=str(e),
                    provider='twilio'
                )
            except:
                pass
            
            # Fallback to console
            return SMSNotificationService.send_sms(notification)


# ============ BULK NOTIFICATION HANDLERS ============

class BulkNotificationService:
    """Service for handling bulk notifications"""
    
    @staticmethod
    def send_bulk_notification_by_type(
        notification_type: str,
        title: str,
        message: str,
        target_user_type: str = 'all',
        filters: Dict[str, Any] = None,
        data: Dict[str, Any] = None
    ) -> Dict[str, int]:
        """Send bulk notifications of specific type"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Get target users
            users_query = User.objects.filter(is_active=True)
            
            if target_user_type != 'all':
                users_query = users_query.filter(user_type=target_user_type)
            
            if filters:
                users_query = users_query.filter(**filters)
            
            users = users_query.all()
            sent_count = 0
            failed_count = 0
            
            logger.info(f"Sending bulk {notification_type} notification to {len(users)} users")
            
            for user in users:
                try:
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=notification_type,
                        title=title,
                        message=message,
                        data=data or {},
                        send_immediately=True
                    )
                    sent_count += 1
                    
                except Exception as user_error:
                    logger.error(f"Error sending bulk notification to user {user.id}: {user_error}")
                    failed_count += 1
                    continue
            
            result = {
                'sent': sent_count,
                'failed': failed_count,
                'total': len(users)
            }
            
            logger.info(f"Bulk {notification_type} notification completed: {sent_count} sent, {failed_count} failed")
            return result
            
        except Exception as e:
            logger.error(f"Error in bulk notification: {str(e)}")
            return {'sent': 0, 'failed': 0, 'total': 0, 'error': str(e)}


# ============ UTILITY FUNCTIONS ============

def get_notification_service_for_sms():
    """Get the appropriate SMS service based on configuration"""
    if TwilioSMSService.is_configured():
        return TwilioSMSService
    return SMSNotificationService


def send_immediate_notification(
    recipient,
    notification_type: str,
    title: str,
    message: str,
    data: Dict[str, Any] = None,
    related_object=None,
    priority: str = 'medium'
):
    """Utility function to send immediate notification"""
    return NotificationService.create_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
        related_object=related_object,
        priority=priority,
        send_immediately=True
    )


def create_delayed_notification(
    recipient,
    notification_type: str,
    title: str,
    message: str,
    data: Dict[str, Any] = None,
    related_object=None,
    priority: str = 'medium'
):
    """Utility function to create notification without immediate sending"""
    return NotificationService.create_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
        related_object=related_object,
        priority=priority,
        send_immediately=False
    )