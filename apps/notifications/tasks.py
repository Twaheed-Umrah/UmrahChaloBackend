from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from datetime import timedelta
import logging

from .services import NotificationService
from .models import Notification, NotificationLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_notification_task(self, notification_id):
    """
    Send individual notification using new notification service
    """
    try:
        logger.info(f"Processing notification task for ID: {notification_id}")
        success = NotificationService.send_notification(notification_id)
        
        if not success:
            # Only raise exception if notification completely failed
            try:
                notification = Notification.objects.get(id=notification_id)
                # If at least app notification worked, don't retry
                if notification.app_sent:
                    logger.info(f"Notification {notification_id} partially successful (app notification sent)")
                    return f"Notification {notification_id} partially sent (app notification successful)"
                else:
                    raise Exception(f"All channels failed for notification {notification_id}")
            except Notification.DoesNotExist:
                raise Exception(f"Notification {notification_id} not found")
        
        return f"Notification {notification_id} sent successfully"
        
    except Exception as e:
        logger.error(f"Error in send_notification_task for {notification_id}: {str(e)}")
        
        if self.request.retries < self.max_retries:
            # Exponential backoff: 60s, 300s, 900s
            countdown = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying notification {notification_id} in {countdown} seconds (attempt {self.request.retries + 1})")
            raise self.retry(countdown=countdown, exc=e)
        else:
            # Mark notification as failed after max retries
            try:
                notification = Notification.objects.get(id=notification_id)
                if hasattr(notification, 'mark_as_failed'):
                    notification.mark_as_failed()
                    notification.save()
                logger.error(f"Notification {notification_id} failed after {self.max_retries} retries")
            except Notification.DoesNotExist:
                logger.error(f"Notification {notification_id} not found during failure handling")
            except Exception as save_error:
                logger.error(f"Error marking notification as failed: {save_error}")
            raise


@shared_task
def send_lead_notification(lead_id, provider_id, notification_type='lead_received'):
    """
    Send lead notification to service provider using new notification service
    """
    try:
        from apps.leads.models import Lead
        from apps.authentication.models import User
        
        lead = Lead.objects.get(id=lead_id)
        provider = User.objects.get(id=provider_id)
        
        logger.info(f"Sending {notification_type} notification for lead {lead_id} to provider {provider_id}")
        
        # Use the new notification service
        notification = NotificationService.send_lead_received_notification(lead, provider)
        
        return f"Lead notification sent successfully to {provider.email} (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending lead notification: {str(e)}")
        return f"Error sending lead notification: {str(e)}"


@shared_task
def send_package_status_notification_task(package_id, status):
    """
    Send package status notification using new notification service
    """
    try:
        from apps.packages.models import Package
        
        package = Package.objects.get(id=package_id)
        
        logger.info(f"Sending package {status} notification for package {package_id}")
        
        notification = NotificationService.send_package_status_notification(package, status)
        
        return f"Package status notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending package status notification: {str(e)}")
        return f"Error sending package status notification: {str(e)}"


@shared_task
def send_welcome_notification_task(user_id):
    """
    Send welcome notification using new notification service
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        
        logger.info(f"Sending welcome notification to user {user_id}")
        
        notification = NotificationService.send_welcome_notification(user)
        
        return f"Welcome notification sent successfully to {user.email} (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending welcome notification: {str(e)}")
        return f"Error sending welcome notification: {str(e)}"


@shared_task
def send_bulk_notifications(notification_data):
    """
    Send bulk notifications using new notification service
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        target_user_type = notification_data.get('target_user_type', 'all')
        notification_type = notification_data.get('notification_type', 'system_notification')
        title = notification_data.get('title', 'System Notification')
        message = notification_data.get('message', '')
        filters = notification_data.get('filters', {})
        
        # Get target users
        users_query = User.objects.filter(is_active=True)
        
        if target_user_type != 'all':
            users_query = users_query.filter(user_type=target_user_type)
        
        if filters:
            users_query = users_query.filter(**filters)
        
        users = users_query.all()
        sent_count = 0
        failed_count = 0
        
        logger.info(f"Sending bulk notification to {len(users)} users")
        
        for user in users:
            try:
                notification = NotificationService.create_notification(
                    recipient=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    data=notification_data.get('data', {}),
                    send_immediately=True
                )
                sent_count += 1
                
            except Exception as user_error:
                logger.error(f"Error sending bulk notification to user {user.id}: {user_error}")
                failed_count += 1
                continue
        
        result = f"Bulk notification completed: {sent_count} sent, {failed_count} failed"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error in bulk notification: {str(e)}")
        return f"Error in bulk notification: {str(e)}"


@shared_task
def send_subscription_expiry_notifications():
    """
    Check for expiring subscriptions and send notifications
    """
    try:
        from apps.subscriptions.models import Subscription
        
        # Get subscriptions expiring in next 7 days
        expiry_date = timezone.now().date() + timedelta(days=7)
        expiring_subscriptions = Subscription.objects.filter(
            end_date__lte=expiry_date,
            is_active=True
        )
        
        sent_count = 0
        
        for subscription in expiring_subscriptions:
            try:
                notification = NotificationService.send_subscription_expiry_notification(subscription)
                sent_count += 1
            except Exception as sub_error:
                logger.error(f"Error sending subscription expiry notification: {sub_error}")
                continue
        
        result = f"Subscription expiry notifications sent: {sent_count}"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error checking subscription expiry: {str(e)}")
        return f"Error checking subscription expiry: {str(e)}"


@shared_task
def send_payment_notification_task(payment_id, status):
    """
    Send payment notification using new notification service
    """
    try:
        from apps.payments.models import Payment
        
        payment = Payment.objects.get(id=payment_id)
        
        logger.info(f"Sending payment {status} notification for payment {payment_id}")
        
        notification = NotificationService.send_payment_notification(payment, status)
        
        return f"Payment notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending payment notification: {str(e)}")
        return f"Error sending payment notification: {str(e)}"


@shared_task
def send_review_notification_task(review_id):
    """
    Send new review notification using new notification service
    """
    try:
        from apps.reviews.models import Review
        
        review = Review.objects.get(id=review_id)
        
        logger.info(f"Sending review notification for review {review_id}")
        
        notification = NotificationService.send_new_review_notification(review)
        
        return f"Review notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending review notification: {str(e)}")
        return f"Error sending review notification: {str(e)}"


@shared_task
def send_verification_complete_notification_task(provider_id):
    """
    Send verification complete notification using new notification service
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        provider = User.objects.get(id=provider_id)
        
        logger.info(f"Sending verification complete notification to provider {provider_id}")
        
        notification = NotificationService.send_verification_complete_notification(provider)
        
        return f"Verification notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending verification notification: {str(e)}")
        return f"Error sending verification notification: {str(e)}"


# Legacy support tasks (keeping for backward compatibility)
@shared_task
def send_customer_notification(lead_id, notification_type):
    """
    Send notifications to customers (legacy support)
    """
    try:
        from apps.leads.models import Lead
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        lead = Lead.objects.get(id=lead_id)
        
        # Try to get user by email, otherwise use lead info
        try:
            user = User.objects.get(email=lead.email)
        except User.DoesNotExist:
            # Create a temporary user object for notification
            user = User(email=lead.email, full_name=lead.customer_name)
            user.id = 0  # Temporary ID
        
        if notification_type == 'lead_confirmed':
            title = "Lead Submission Confirmed"
            message = f"Thank you for submitting your inquiry through Umrah Chalo. Reference ID: #{lead.id}"
            notif_type = 'lead_confirmed'
            
        elif notification_type == 'provider_response':
            title = "Service Provider Response Received"
            message = f"A service provider has responded to your inquiry (Reference: #{lead.id})"
            notif_type = 'provider_response'
            
        else:
            logger.warning(f"Unknown customer notification type: {notification_type}")
            return f"Unknown notification type: {notification_type}"
        
        # Use new notification service if user exists in database
        if user.id > 0:
            notification = NotificationService.create_notification(
                recipient=user,
                notification_type=notif_type,
                title=title,
                message=message,
                data={
                    'lead_id': lead.id,
                    'customer_name': lead.customer_name
                },
                related_object=lead
            )
            return f"Customer notification sent via notification service (ID: {notification.id})"
        else:
            # Fallback to direct email for non-registered users
            send_mail(
                title,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [lead.email],
                fail_silently=False,
            )
            return f"Customer notification sent via direct email"
        
    except Exception as e:
        logger.error(f"Error sending customer notification: {str(e)}")
        return f"Error sending customer notification: {str(e)}"


@shared_task
def send_admin_notification(notification_type, context=None):
    """
    Send notifications to admin users
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Get admin users
        admin_users = User.objects.filter(is_staff=True, is_superuser=True)
        sent_count = 0
        
        if notification_type == 'new_provider_registration':
            title = "New Provider Registration"
            message = f"New service provider has registered: {context.get('provider_name', 'Unknown')}"
            notif_type = 'admin_new_provider'
            
        elif notification_type == 'high_lead_volume':
            title = "High Lead Volume Alert"
            message = f"High lead volume detected: {context.get('lead_count', 0)} leads in the last hour"
            notif_type = 'admin_high_volume'
            
        elif notification_type == 'system_error':
            title = "System Error Alert"
            message = f"System error detected: {context.get('error', 'Unknown error')}"
            notif_type = 'admin_system_error'
            
        else:
            logger.warning(f"Unknown admin notification type: {notification_type}")
            return f"Unknown notification type: {notification_type}"
        
        # Send to all admin users using notification service
        for admin_user in admin_users:
            try:
                notification = NotificationService.create_notification(
                    recipient=admin_user,
                    notification_type=notif_type,
                    title=title,
                    message=message,
                    data=context or {},
                    priority='high'
                )
                sent_count += 1
            except Exception as admin_error:
                logger.error(f"Error sending admin notification to {admin_user.email}: {admin_error}")
                continue
        
        result = f"Admin notification sent to {sent_count} users"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error sending admin notification: {str(e)}")
        return f"Error sending admin notification: {str(e)}"


@shared_task
def send_sms_notification(phone_number, message):
    """
    Send SMS notification (placeholder for SMS service integration)
    """
    try:
        # TODO: Integrate with Twilio
        if hasattr(settings, 'TWILIO_ACCOUNT_SID') and settings.TWILIO_ACCOUNT_SID:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            client.messages.create(
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            
            logger.info(f"SMS sent successfully to {phone_number}")
        else:
            # Log for development
            logger.info(f"SMS to {phone_number}: {message}")
        
        return f"SMS sent successfully to {phone_number}"
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return f"Error sending SMS: {str(e)}"


@shared_task
def send_whatsapp_notification(phone_number, message):
    """
    Send WhatsApp notification (placeholder for WhatsApp Business API)
    """
    try:
        # TODO: Integrate with WhatsApp Business API
        logger.info(f"WhatsApp to {phone_number}: {message}")
        
        return f"WhatsApp message sent successfully to {phone_number}"
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return f"Error sending WhatsApp message: {str(e)}"


@shared_task
def cleanup_old_notifications():
    """
    Clean up old notification logs
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=90)
        
        # Clean up old notifications
        old_notifications = Notification.objects.filter(created_at__lt=cutoff_date)
        notification_count = old_notifications.count()
        old_notifications.delete()
        
        # Clean up old logs
        old_logs = NotificationLog.objects.filter(created_at__lt=cutoff_date)
        log_count = old_logs.count()
        old_logs.delete()
        
        result = f"Cleanup completed: {notification_count} notifications, {log_count} logs deleted"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error in notification cleanup: {str(e)}")
        return f"Error in notification cleanup: {str(e)}"


@shared_task
def send_package_upload_reminders():
    """
    Send reminders to service providers who haven't uploaded packages
    """
    try:
        from django.contrib.auth import get_user_model
        from apps.packages.models import Package
        User = get_user_model()
        
        # Get service providers who haven't uploaded packages in last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        providers_without_recent_packages = User.objects.filter(
            user_type='service_provider',
            is_active=True
        ).exclude(
            packages__created_at__gte=thirty_days_ago
        ).distinct()
        
        sent_count = 0
        
        for provider in providers_without_recent_packages:
            try:
                notification = NotificationService.create_notification(
                    recipient=provider,
                    notification_type='package_upload_reminder',
                    title="Upload New Packages",
                    message="It's been a while since you uploaded new packages. Upload fresh packages to attract more customers!",
                    data={
                        'provider_name': provider.full_name,
                        'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/dashboard/"
                    }
                )
                sent_count += 1
            except Exception as provider_error:
                logger.error(f"Error sending package upload reminder to {provider.email}: {provider_error}")
                continue
        
        result = f"Package upload reminders sent to {sent_count} providers"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error sending package upload reminders: {str(e)}")
        return f"Error sending package upload reminders: {str(e)}"