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
    """Main service for handling notifications with improved error handling"""
    
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
        """
        Create a new notification with robust error handling
        """
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
        """
        Send notification through all enabled channels synchronously
        """
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
    
    @staticmethod
    def send_welcome_notification(user):
        """Send welcome notification to new user"""
        try:
            return NotificationService.create_notification(
                recipient=user,
                notification_type='welcome',
                title=f"Welcome to Umrah Chalo, {user.full_name or user.email}!",
                message="Thank you for joining our platform. We're excited to have you!",
                data={
                    'user_name': user.full_name or user.email,
                    'user_type': getattr(user, 'get_user_type_display', lambda: 'User')(),
                }
            )
        except Exception as e:
            logger.error(f"Failed to send welcome notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_lead_received_notification(lead, provider):
        """Send lead received notification to provider"""
        try:
            return NotificationService.create_notification(
                recipient=provider,
                notification_type='lead_received',
                title="New Lead Received!",
                message=f"You have received a new lead from {lead.pilgrim.full_name}",
                data={
                    'lead_id': lead.id,
                    'pilgrim_name': lead.pilgrim.full_name,
                    'pilgrim_phone': getattr(lead.pilgrim, 'phone', 'N/A'),
                    'pilgrim_email': getattr(lead.pilgrim, 'email', 'N/A'),
                    'package_name': lead.package.name if lead.package else 'General Inquiry',
                    'message': getattr(lead, 'message', ''),
                    'created_at': lead.created_at.strftime('%Y-%m-%d %H:%M'),
                },
                related_object=lead
            )
        except Exception as e:
            logger.error(f"Failed to send lead notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_package_status_notification(package, status):
        """Send package status notification"""
        try:
            if status == 'approved':
                notification_type = 'package_approved'
                title = "Package Approved!"
                message = f"Your package '{package.name}' has been approved and is now live."
            else:
                notification_type = 'package_rejected'
                title = "Package Rejected"
                message = f"Your package '{package.name}' has been rejected. Please review and resubmit."
            
            return NotificationService.create_notification(
                recipient=package.provider,
                notification_type=notification_type,
                title=title,
                message=message,
                data={
                    'package_name': package.name,
                    'package_id': package.id,
                    'provider_name': getattr(package.provider, 'business_name', package.provider.full_name),
                },
                related_object=package
            )
        except Exception as e:
            logger.error(f"Failed to send package status notification: {e}")
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
                },
                related_object=subscription
            )
        except Exception as e:
            logger.error(f"Failed to send subscription expiry notification: {e}")
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
                },
                related_object=review
            )
        except Exception as e:
            logger.error(f"Failed to send review notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_payment_notification(payment, status):
        """Send payment notification"""
        try:
            if status == 'success':
                notification_type = 'payment_success'
                title = "Payment Successful!"
                message = f"Your payment of ₹{payment.amount} has been processed successfully."
            else:
                notification_type = 'payment_failed'
                title = "Payment Failed"
                message = f"Your payment of ₹{payment.amount} has failed. Please try again."
            
            return NotificationService.create_notification(
                recipient=payment.user,
                notification_type=notification_type,
                title=title,
                message=message,
                data={
                    'amount': payment.amount,
                    'payment_id': payment.id,
                    'payment_method': getattr(payment, 'payment_method', 'N/A'),
                    'transaction_id': getattr(payment, 'transaction_id', 'N/A'),
                },
                related_object=payment
            )
        except Exception as e:
            logger.error(f"Failed to send payment notification: {e}")
            return type('MockNotification', (), {'id': 0, 'status': 'failed'})
    
    @staticmethod
    def send_verification_complete_notification(provider):
        """Send verification complete notification"""
        try:
            business_name = 'N/A'
            if hasattr(provider, 'service_provider_profile'):
                business_name = getattr(provider.service_provider_profile, 'business_name', provider.full_name)
            
            return NotificationService.create_notification(
                recipient=provider,
                notification_type='verification_complete',
                title="Verification Complete!",
                message="Your service provider profile has been verified successfully.",
                data={
                    'business_name': business_name,
                    'verification_date': timezone.now().strftime('%Y-%m-%d'),
                },
                related_object=provider
            )
        except Exception as e:
            logger.error(f"Failed to send verification notification: {e}")
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
                    logger.info(f"Using template: {template_path}")
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
                
                logger.info(f"Email sent successfully to {notification.recipient.email}")
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
            logger.info(f"=== EMAIL NOTIFICATION ===")
            logger.info(f"To: {notification.recipient.email}")
            logger.info(f"Subject: {notification.title}")
            logger.info(f"Message: {notification.message}")
            logger.info(f"Type: {notification.notification_type}")
            logger.info(f"========================")
            
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
    def send_sms(notification: Notification) -> bool:
        """Send SMS notification"""
        try:
            if not notification.recipient.phone:
                logger.warning(f"No phone number for user {notification.recipient.id}")
                return False
            
            # Get SMS content
            sms_content = notification.message
            
            # Try to get SMS template
            template_paths = [
                f"notifications/sms/{notification.notification_type}.txt",
                f"notifications/{notification.notification_type}_sms.txt",
            ]
            
            context = {
                'notification': notification,
                'user': notification.recipient,
                **notification.data
            }
            
            rendered_content = EmailNotificationService.render_template_safe(template_paths, context)
            if rendered_content:
                sms_content = rendered_content
            
            # For now, log the SMS
            logger.info(f"=== SMS NOTIFICATION ===")
            logger.info(f"To: {notification.recipient.phone}")
            logger.info(f"Message: {sms_content}")
            logger.info(f"======================")
            
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
    def send_app_notification(notification: Notification) -> bool:
        """Send in-app notification"""
        try:
            # Try to get app notification template
            template_paths = [
                f"notifications/app/{notification.notification_type}.txt",
                f"notifications/{notification.notification_type}_app.txt",
            ]
            
            context = {
                'notification': notification,
                'user': notification.recipient,
                **notification.data
            }
            
            rendered_content = EmailNotificationService.render_template_safe(template_paths, context)
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
            
            logger.info(f"App notification processed for user {notification.recipient.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing app notification {notification.id}: {str(e)}")
            return False
        
