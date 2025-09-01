from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from datetime import timedelta
import logging

from django.core.management import call_command

from .services import NotificationService, BulkNotificationService
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


# ============ SPECIFIC NOTIFICATION TYPE TASKS ============

@shared_task
def send_lead_received_notification_task(lead_id, provider_id):
    """Send lead received notification to service provider"""
    try:
        from apps.leads.models import Lead
        from apps.authentication.models import User
        
        lead = Lead.objects.get(id=lead_id)
        provider = User.objects.get(id=provider_id)
        
        logger.info(f"Sending lead_received notification for lead {lead_id} to provider {provider_id}")
        
        notification = NotificationService.send_lead_received_notification(lead, provider)
        
        return f"Lead received notification sent successfully to {provider.email} (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending lead received notification: {str(e)}")
        return f"Error sending lead received notification: {str(e)}"


@shared_task
def send_new_review_notification_task(review_id):
    """Send new review notification to provider"""
    try:
        from apps.reviews.models import Review
        
        review = Review.objects.get(id=review_id)
        
        logger.info(f"Sending new_review notification for review {review_id}")
        
        notification = NotificationService.send_new_review_notification(review)
        
        return f"New review notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending new review notification: {str(e)}")
        return f"Error sending new review notification: {str(e)}"


@shared_task
def send_package_approved_notification_task(package_id):
    """Send package approved notification"""
    try:
        from apps.packages.models import Package
        
        package = Package.objects.get(id=package_id)
        
        logger.info(f"Sending package_approved notification for package {package_id}")
        
        notification = NotificationService.send_package_approved_notification(package)
        
        return f"Package approved notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending package approved notification: {str(e)}")
        return f"Error sending package approved notification: {str(e)}"


@shared_task
def send_package_rejected_notification_task(package_id, rejection_reason=""):
    """Send package rejected notification"""
    try:
        from apps.packages.models import Package
        
        package = Package.objects.get(id=package_id)
        
        logger.info(f"Sending package_rejected notification for package {package_id}")
        
        notification = NotificationService.send_package_rejected_notification(package, rejection_reason)
        
        return f"Package rejected notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending package rejected notification: {str(e)}")
        return f"Error sending package rejected notification: {str(e)}"


@shared_task
def send_package_upload_reminder_notification_task(provider_id):
    """Send package upload reminder notification"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        provider = User.objects.get(id=provider_id)
        
        logger.info(f"Sending package_upload_reminder notification to provider {provider_id}")
        
        notification = NotificationService.send_package_upload_reminder_notification(provider)
        
        return f"Package upload reminder sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending package upload reminder: {str(e)}")
        return f"Error sending package upload reminder: {str(e)}"


@shared_task
def send_password_reset_notification_task(user_id, reset_token, reset_url):
    """Send password reset notification"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        
        logger.info(f"Sending password_reset notification to user {user_id}")
        
        notification = NotificationService.send_password_reset_notification(user, reset_token, reset_url)
        
        return f"Password reset notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending password reset notification: {str(e)}")
        return f"Error sending password reset notification: {str(e)}"


@shared_task
def send_payment_failed_notification_task(payment_id):
    """Send payment failed notification"""
    try:
        from apps.payments.models import Payment
        
        payment = Payment.objects.get(id=payment_id)
        
        logger.info(f"Sending payment_failed notification for payment {payment_id}")
        
        notification = NotificationService.send_payment_failed_notification(payment)
        
        return f"Payment failed notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending payment failed notification: {str(e)}")
        return f"Error sending payment failed notification: {str(e)}"


@shared_task
def send_payment_success_notification_task(payment_id):
    """Send payment success notification"""
    try:
        from apps.payments.models import Payment
        
        payment = Payment.objects.get(id=payment_id)
        
        logger.info(f"Sending payment_success notification for payment {payment_id}")
        
        notification = NotificationService.send_payment_success_notification(payment)
        
        return f"Payment success notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending payment success notification: {str(e)}")
        return f"Error sending payment success notification: {str(e)}"


@shared_task
def send_subscription_expiry_notification_task(subscription_id):
    """Send subscription expiry notification"""
    try:
        from apps.subscriptions.models import Subscription
        
        subscription = Subscription.objects.get(id=subscription_id)
        
        logger.info(f"Sending subscription_expiry notification for subscription {subscription_id}")
        
        notification = NotificationService.send_subscription_expiry_notification(subscription)
        
        return f"Subscription expiry notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending subscription expiry notification: {str(e)}")
        return f"Error sending subscription expiry notification: {str(e)}"


@shared_task
def send_subscription_reminder_notification_task(subscription_id, days_before_expiry=3):
    """Send subscription reminder notification"""
    try:
        from apps.subscriptions.models import Subscription
        
        subscription = Subscription.objects.get(id=subscription_id)
        
        logger.info(f"Sending subscription_reminder notification for subscription {subscription_id}")
        
        notification = NotificationService.send_subscription_reminder_notification(subscription, days_before_expiry)
        
        return f"Subscription reminder notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending subscription reminder notification: {str(e)}")
        return f"Error sending subscription reminder notification: {str(e)}"


@shared_task
def send_verification_complete_notification_task(provider_id):
    """Send verification complete notification"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        provider = User.objects.get(id=provider_id)
        
        logger.info(f"Sending verification_complete notification to provider {provider_id}")
        
        notification = NotificationService.send_verification_complete_notification(provider)
        
        return f"Verification complete notification sent successfully (Notification ID: {notification.id})"
        
    except Exception as e:
        logger.error(f"Error sending verification complete notification: {str(e)}")
        return f"Error sending verification complete notification: {str(e)}"


@shared_task
def send_welcome_notification_task(user_id):
    """Send welcome notification to new user"""
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


# ============ BULK NOTIFICATION TASKS ============

@shared_task
def send_bulk_notifications_by_type(notification_type, title, message, target_user_type='all', filters=None, data=None):
    """Send bulk notifications of specific type"""
    try:
        result = BulkNotificationService.send_bulk_notification_by_type(
            notification_type=notification_type,
            title=title,
            message=message,
            target_user_type=target_user_type,
            filters=filters or {},
            data=data or {}
        )
        
        logger.info(f"Bulk {notification_type} notification completed: {result}")
        return f"Bulk {notification_type} notification: {result['sent']} sent, {result['failed']} failed"
        
    except Exception as e:
        logger.error(f"Error in bulk {notification_type} notification: {str(e)}")
        return f"Error in bulk {notification_type} notification: {str(e)}"


@shared_task
def send_bulk_package_upload_reminders():
    """Send bulk package upload reminders to inactive providers"""
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
                notification = NotificationService.send_package_upload_reminder_notification(provider)
                sent_count += 1
            except Exception as provider_error:
                logger.error(f"Error sending package upload reminder to {provider.email}: {provider_error}")
                continue
        
        result = f"Package upload reminders sent to {sent_count} providers"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error sending bulk package upload reminders: {str(e)}")
        return f"Error sending bulk package upload reminders: {str(e)}"


@shared_task
def send_bulk_subscription_expiry_notifications():
    """Check for expiring subscriptions and send notifications"""
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
                # Calculate exact days left
                days_left = (subscription.end_date - timezone.now().date()).days
                
                if days_left == 7:
                    notification = NotificationService.send_subscription_expiry_notification(subscription)
                elif days_left in [3, 1]:
                    notification = NotificationService.send_subscription_reminder_notification(subscription, days_left)
                else:
                    continue  # Skip other days
                
                sent_count += 1
            except Exception as sub_error:
                logger.error(f"Error sending subscription notification: {sub_error}")
                continue
        
        result = f"Subscription notifications sent: {sent_count}"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error checking subscription expiry: {str(e)}")
        return f"Error checking subscription expiry: {str(e)}"


# ============ PERIODIC TASKS ============

@shared_task
def cleanup_old_notifications():
    """Clean up old notification logs"""
    try:
        cutoff_date = timezone.now() - timedelta(days=90)
        
        # Clean up old notifications
        old_notifications = Notification.objects.filter(created_at__lt=cutoff_date)
        notification_count = old_notifications.count()
        old_notifications.delete()
        
        # Clean up old logs
        old_logs = NotificationLog.objects.filter(sent_at__lt=cutoff_date)
        log_count = old_logs.count()
        old_logs.delete()
        
        result = f"Cleanup completed: {notification_count} notifications, {log_count} logs deleted"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error in notification cleanup: {str(e)}")
        return f"Error in notification cleanup: {str(e)}"


@shared_task
def process_failed_notifications():
    """Process failed notifications for retry"""
    try:
        # Get notifications that can be retried
        failed_notifications = Notification.objects.filter(
            status='failed',
            retry_count__lt=3,
            next_retry_at__lte=timezone.now()
        )
        
        retry_count = 0
        
        for notification in failed_notifications:
            try:
                success = NotificationService.send_notification(notification.id)
                if success:
                    retry_count += 1
                else:
                    notification.increment_retry()
            except Exception as retry_error:
                logger.error(f"Error retrying notification {notification.id}: {retry_error}")
                notification.increment_retry()
        
        result = f"Processed {retry_count} failed notifications"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error processing failed notifications: {str(e)}")
        return f"Error processing failed notifications: {str(e)}"


# ============ LEGACY SUPPORT TASKS (keeping for backward compatibility) ============

@shared_task
def send_lead_notification(lead_id, provider_id, notification_type='lead_received'):
    """Legacy task - redirects to new task"""
    if notification_type == 'lead_received':
        return send_lead_received_notification_task(lead_id, provider_id)
    else:
        logger.warning(f"Unknown legacy notification type: {notification_type}")
        return f"Unknown notification type: {notification_type}"


@shared_task
def send_package_status_notification_task(package_id, status):
    """Legacy task - redirects to new tasks"""
    if status == 'approved':
        return send_package_approved_notification_task(package_id)
    elif status == 'rejected':
        return send_package_rejected_notification_task(package_id)
    else:
        logger.warning(f"Unknown package status: {status}")
        return f"Unknown package status: {status}"


@shared_task
def send_payment_notification_task(payment_id, status):
    """Legacy task - redirects to new tasks"""
    if status == 'success':
        return send_payment_success_notification_task(payment_id)
    elif status == 'failed':
        return send_payment_failed_notification_task(payment_id)
    else:
        logger.warning(f"Unknown payment status: {status}")
        return f"Unknown payment status: {status}"


@shared_task
def send_review_notification_task(review_id):
    """Legacy task - redirects to new task"""
    return send_new_review_notification_task(review_id)


# ============ ADMIN AND CUSTOMER NOTIFICATIONS ============

@shared_task
def send_admin_notification(notification_type, context=None):
    """Send notifications to admin users"""
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
def send_customer_notification(lead_id, notification_type):
    """Send notifications to customers (legacy support)"""
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
            title = "Lead Confirmed"
            message = f"Your service request has been confirmed. Provider will contact you soon."
            notif_type = 'customer_lead_confirmed'
            
        elif notification_type == 'provider_assigned':
            title = "Provider Assigned"
            message = f"A service provider has been assigned to your request."
            notif_type = 'customer_provider_assigned'
            
        elif notification_type == 'service_completed':
            title = "Service Completed"
            message = f"Your service request has been marked as completed. Please leave a review."
            notif_type = 'customer_service_completed'
            
        else:
            logger.warning(f"Unknown customer notification type: {notification_type}")
            return f"Unknown notification type: {notification_type}"
        
        # Send notification using notification service
        try:
            notification = NotificationService.create_notification(
                recipient=user,
                notification_type=notif_type,
                title=title,
                message=message,
                data={'lead_id': lead_id},
                priority='normal'
            )
            
            result = f"Customer notification sent successfully (Notification ID: {notification.id})"
            logger.info(result)
            return result
            
        except Exception as send_error:
            logger.error(f"Error sending customer notification: {send_error}")
            return f"Error sending customer notification: {send_error}"
        
    except Exception as e:
        logger.error(f"Error in customer notification task: {str(e)}")
        return f"Error in customer notification task: {str(e)}"


# ============ MONITORING AND ANALYTICS TASKS ============

@shared_task
def generate_notification_analytics():
    """Generate notification analytics and send to admin"""
    try:
        from django.db.models import Count, Q
        from datetime import datetime
        
        # Get statistics for last 24 hours
        yesterday = timezone.now() - timedelta(days=1)
        
        total_sent = Notification.objects.filter(created_at__gte=yesterday).count()
        successful = Notification.objects.filter(
            created_at__gte=yesterday,
            status='sent'
        ).count()
        failed = Notification.objects.filter(
            created_at__gte=yesterday,
            status='failed'
        ).count()
        
        # Get breakdown by type
        type_breakdown = Notification.objects.filter(
            created_at__gte=yesterday
        ).values('notification_type').annotate(count=Count('id')).order_by('-count')
        
        # Get channel performance
        email_sent = Notification.objects.filter(
            created_at__gte=yesterday,
            email_sent=True
        ).count()
        sms_sent = Notification.objects.filter(
            created_at__gte=yesterday,
            sms_sent=True
        ).count()
        app_sent = Notification.objects.filter(
            created_at__gte=yesterday,
            app_sent=True
        ).count()
        push_sent = Notification.objects.filter(
            created_at__gte=yesterday,
            push_sent=True
        ).count()
        
        analytics_data = {
            'period': '24 hours',
            'total_notifications': total_sent,
            'successful': successful,
            'failed': failed,
            'success_rate': round((successful / total_sent * 100), 2) if total_sent > 0 else 0,
            'channel_performance': {
                'email': email_sent,
                'sms': sms_sent,
                'app': app_sent,
                'push': push_sent
            },
            'type_breakdown': list(type_breakdown[:10])  # Top 10 types
        }
        
        # Send analytics to admin
        send_admin_notification.delay(
            'notification_analytics',
            analytics_data
        )
        
        result = f"Notification analytics generated: {total_sent} notifications processed"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error generating notification analytics: {str(e)}")
        return f"Error generating notification analytics: {str(e)}"


@shared_task
def monitor_notification_queue():
    """Monitor notification queue and alert if overloaded"""
    try:
        from celery import current_app
        
        # Get queue information
        inspect = current_app.control.inspect()
        active_tasks = inspect.active()
        scheduled_tasks = inspect.scheduled()
        
        total_active = sum(len(tasks) for tasks in (active_tasks or {}).values())
        total_scheduled = sum(len(tasks) for tasks in (scheduled_tasks or {}).values())
        
        # Alert if queue is overloaded
        if total_active > 100 or total_scheduled > 500:
            send_admin_notification.delay(
                'queue_overload',
                {
                    'active_tasks': total_active,
                    'scheduled_tasks': total_scheduled,
                    'timestamp': timezone.now().isoformat()
                }
            )
        
        result = f"Queue monitoring: {total_active} active, {total_scheduled} scheduled"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error monitoring notification queue: {str(e)}")
        return f"Error monitoring notification queue: {str(e)}"


# ============ EMERGENCY AND SYSTEM TASKS ============

@shared_task
def send_emergency_broadcast(title, message, target_users='all', priority='high'):
    """Send emergency broadcast to specified users"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Determine target users
        if target_users == 'all':
            users = User.objects.filter(is_active=True)
        elif target_users == 'providers':
            users = User.objects.filter(user_type='service_provider', is_active=True)
        elif target_users == 'customers':
            users = User.objects.filter(user_type='customer', is_active=True)
        elif target_users == 'admins':
            users = User.objects.filter(is_staff=True, is_active=True)
        else:
            users = User.objects.filter(id__in=target_users) if isinstance(target_users, list) else User.objects.none()
        
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                notification = NotificationService.create_notification(
                    recipient=user,
                    notification_type='emergency_broadcast',
                    title=title,
                    message=message,
                    data={},
                    priority=priority,
                    send_immediately=True  # Skip queuing for emergency
                )
                sent_count += 1
            except Exception as user_error:
                logger.error(f"Failed to send emergency notification to {user.email}: {user_error}")
                failed_count += 1
        
        result = f"Emergency broadcast completed: {sent_count} sent, {failed_count} failed"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error in emergency broadcast: {str(e)}")
        return f"Error in emergency broadcast: {str(e)}"


@shared_task
def system_maintenance_notification(maintenance_start, maintenance_end, message=""):
    """Send system maintenance notifications"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Send to all active users
        users = User.objects.filter(is_active=True)
        
        default_message = f"System maintenance scheduled from {maintenance_start} to {maintenance_end}. Services may be temporarily unavailable."
        final_message = message if message else default_message
        
        sent_count = 0
        
        for user in users:
            try:
                notification = NotificationService.create_notification(
                    recipient=user,
                    notification_type='system_maintenance',
                    title="Scheduled Maintenance Notice",
                    message=final_message,
                    data={
                        'maintenance_start': maintenance_start,
                        'maintenance_end': maintenance_end
                    },
                    priority='normal'
                )
                sent_count += 1
            except Exception as user_error:
                logger.error(f"Failed to send maintenance notification to {user.email}: {user_error}")
                continue
        
        result = f"Maintenance notification sent to {sent_count} users"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error sending maintenance notifications: {str(e)}")
        return f"Error sending maintenance notifications: {str(e)}"


# ============ TESTING AND DEVELOPMENT TASKS ============

@shared_task
def test_notification_channels(user_id, test_message="Test notification"):
    """Test all notification channels for a specific user"""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        
        # Create test notification
        notification = NotificationService.create_notification(
            recipient=user,
            notification_type='system_test',
            title="Notification Channel Test",
            message=test_message,
            data={'test': True},
            priority='low'
        )
        
        result = f"Test notification sent to {user.email} (Notification ID: {notification.id})"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error in test notification: {str(e)}")
        return f"Error in test notification: {str(e)}"


@shared_task
def validate_notification_templates():
    """Validate all notification templates"""
    try:
        from django.template import Template, Context
        from django.template.loader import get_template
        
        # List of template names to validate
        template_names = [
            'notifications/email/lead_received.html',
            'notifications/email/new_review.html',
            'notifications/email/package_approved.html',
            'notifications/email/package_rejected.html',
            'notifications/email/services_approved.html',
            'notifications/email/services_rejected.html',
            'notifications/email/payment_success.html',
            'notifications/email/payment_failed.html',
            'notifications/email/subscription_expiry.html',
            'notifications/email/welcome.html',
            'notifications/sms/lead_received.txt',
            'notifications/sms/package_approved.txt'
        ]
        
        valid_count = 0
        invalid_templates = []
        
        for template_name in template_names:
            try:
                template = get_template(template_name)
                # Test render with dummy context
                test_context = Context({
                    'user': {'name': 'Test User', 'email': 'test@example.com'},
                    'data': {'test': True}
                })
                template.render(test_context)
                valid_count += 1
            except Exception as template_error:
                invalid_templates.append({
                    'template': template_name,
                    'error': str(template_error)
                })
        
        if invalid_templates:
            # Send alert to admin about invalid templates
            send_admin_notification.delay(
                'template_validation_failed',
                {
                    'invalid_templates': invalid_templates,
                    'valid_count': valid_count,
                    'total_count': len(template_names)
                }
            )
        
        result = f"Template validation: {valid_count}/{len(template_names)} valid"
        logger.info(result)
        return result
        
    except Exception as e:
        logger.error(f"Error validating templates: {str(e)}")
        return f"Error validating templates: {str(e)}"


@shared_task
def send_daily_notifications():
    """Celery task to send daily automated notifications"""
    try:
        call_command('send_automated_notifications')
        logger.info("Daily notifications sent successfully")
    except Exception as e:
        logger.error(f"Failed to send daily notifications: {e}")
        raise