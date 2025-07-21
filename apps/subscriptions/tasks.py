from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
from .models import Subscription, SubscriptionAlert, SubscriptionHistory, SubscriptionFeature
from apps.packages.models import Package
from apps.core.utils import send_notification
import logging

logger = logging.getLogger(__name__)


@shared_task
def check_subscription_expiry():
    """Check for expiring subscriptions and send alerts"""
    try:
        # Get subscriptions expiring in 7 days
        expiring_soon = Subscription.objects.filter(
            status='active',
            end_date__lte=timezone.now() + timedelta(days=7),
            end_date__gt=timezone.now()
        )
        
        for subscription in expiring_soon:
            # Check if alert already exists
            alert_exists = SubscriptionAlert.objects.filter(
                subscription=subscription,
                alert_type='expiry_warning',
                created_at__date=timezone.now().date()
            ).exists()
            
            if not alert_exists:
                days_remaining = (subscription.end_date - timezone.now()).days
                
                # Create alert
                alert = SubscriptionAlert.objects.create(
                    subscription=subscription,
                    alert_type='expiry_warning',
                    message=f'Your {subscription.plan.name} subscription will expire in {days_remaining} days. '
                           f'Please renew to continue using our services.'
                )
                
                # Send notification
                send_notification.delay(
                    user_id=subscription.user.id,
                    title='Subscription Expiring Soon',
                    message=alert.message,
                    notification_type='subscription_expiry'
                )
                
                logger.info(f"Expiry alert sent for subscription {subscription.id}")
        
        logger.info(f"Processed {expiring_soon.count()} expiring subscriptions")
        
    except Exception as e:
        logger.error(f"Error checking subscription expiry: {str(e)}")


@shared_task
def expire_subscriptions():
    """Mark expired subscriptions as expired and remove packages"""
    try:
        # Get expired subscriptions
        expired_subscriptions = Subscription.objects.filter(
            status='active',
            end_date__lt=timezone.now()
        )
        
        for subscription in expired_subscriptions:
            # Mark as expired
            subscription.status = 'expired'
            subscription.save()
            
            # Create history record
            SubscriptionHistory.objects.create(
                subscription=subscription,
                action='expired',
                notes='Subscription expired automatically'
            )
            
            # Remove user's packages
            Package.objects.filter(
                provider=subscription.user,
                is_active=True
            ).update(is_active=False)
            
            # Create alert
            alert = SubscriptionAlert.objects.create(
                subscription=subscription,
                alert_type='expiry_warning',
                message='Your subscription has expired. Your packages have been deactivated. '
                       'Please renew to continue using our services.'
            )
            
            # Send notification
            send_notification.delay(
                user_id=subscription.user.id,
                title='Subscription Expired',
                message=alert.message,
                notification_type='subscription_expired'
            )
            
            logger.info(f"Expired subscription {subscription.id}")
        
        logger.info(f"Processed {expired_subscriptions.count()} expired subscriptions")
        
    except Exception as e:
        logger.error(f"Error expiring subscriptions: {str(e)}")


@shared_task
def send_renewal_reminders():
    """Send renewal reminders for subscriptions expiring in 3 days"""
    try:
        # Get subscriptions expiring in 3 days
        expiring_subscriptions = Subscription.objects.filter(
            status='active',
            end_date__lte=timezone.now() + timedelta(days=3),
            end_date__gt=timezone.now()
        )
        
        for subscription in expiring_subscriptions:
            # Check if renewal reminder already sent today
            reminder_exists = SubscriptionAlert.objects.filter(
                subscription=subscription,
                alert_type='renewal_reminder',
                created_at__date=timezone.now().date()
            ).exists()
            
            if not reminder_exists:
                # Create alert
                alert = SubscriptionAlert.objects.create(
                    subscription=subscription,
                    alert_type='renewal_reminder',
                    message=f'Your {subscription.plan.name} subscription expires soon. '
                           f'Renew now to avoid service interruption.'
                )
                
                # Send notification
                send_notification.delay(
                    user_id=subscription.user.id,
                    title='Renew Your Subscription',
                    message=alert.message,
                    notification_type='renewal_reminder'
                )
                
                logger.info(f"Renewal reminder sent for subscription {subscription.id}")
        
        logger.info(f"Sent renewal reminders for {expiring_subscriptions.count()} subscriptions")
        
    except Exception as e:
        logger.error(f"Error sending renewal reminders: {str(e)}")


@shared_task
def check_feature_limits():
    """Check feature usage limits and send alerts"""
    try:
        # Get features approaching limits (90% usage)
        approaching_limit = SubscriptionFeature.objects.filter(
            limit__isnull=False,
            usage_count__gte=models.F('limit') * 0.9
        ).select_related('subscription')
        
        for feature in approaching_limit:
            # Check if alert already exists
            alert_exists = SubscriptionAlert.objects.filter(
                subscription=feature.subscription,
                alert_type='feature_limit',
                created_at__date=timezone.now().date()
            ).exists()
            
            if not alert_exists:
                # Create alert
                alert = SubscriptionAlert.objects.create(
                    subscription=feature.subscription,
                    alert_type='feature_limit',
                    message=f'You are approaching the limit for {feature.feature_name}. '
                           f'Usage: {feature.usage_count}/{feature.limit}. '
                           f'Consider upgrading your plan.'
                )
                
                # Send notification
                send_notification.delay(
                    user_id=feature.subscription.user.id,
                    title='Feature Limit Warning',
                    message=alert.message,
                    notification_type='feature_limit'
                )
                
                logger.info(f"Feature limit alert sent for {feature.feature_name}")
        
        logger.info(f"Processed {approaching_limit.count()} features approaching limits")
        
    except Exception as e:
        logger.error(f"Error checking feature limits: {str(e)}")


@shared_task
def auto_renew_subscriptions():
    """Auto-renew subscriptions that have auto_renew enabled"""
    try:
        # Get subscriptions with auto-renewal enabled that expire today
        auto_renew_subscriptions = Subscription.objects.filter(
            status='active',
            auto_renew=True,
            end_date__date=timezone.now().date()
        )
        
        for subscription in auto_renew_subscriptions:
            try:
                # Extend subscription
                subscription.extend_subscription(subscription.plan.duration_months)
                subscription.save()
                
                # Create history record
                SubscriptionHistory.objects.create(
                    subscription=subscription,
                    action='renewed',
                    new_plan=subscription.plan,
                    amount=subscription.plan.price,
                    notes='Auto-renewed'
                )
                
                # Create alert
                alert = SubscriptionAlert.objects.create(
                    subscription=subscription,
                    alert_type='renewal_reminder',
                    message=f'Your {subscription.plan.name} subscription has been auto-renewed '
                           f'for {subscription.plan.duration_months} months.'
                )
                
                # Send notification
                send_notification.delay(
                    user_id=subscription.user.id,
                    title='Subscription Auto-Renewed',
                    message=alert.message,
                    notification_type='auto_renewal'
                )
                
                logger.info(f"Auto-renewed subscription {subscription.id}")
                
            except Exception as e:
                logger.error(f"Error auto-renewing subscription {subscription.id}: {str(e)}")
                
                # Create alert about failed renewal
                SubscriptionAlert.objects.create(
                    subscription=subscription,
                    alert_type='payment_failed',
                    message='Auto-renewal failed. Please renew manually to continue using our services.'
                )
        
        logger.info(f"Processed {auto_renew_subscriptions.count()} auto-renewal subscriptions")
        
    except Exception as e:
        logger.error(f"Error processing auto-renewals: {str(e)}")


@shared_task
def cleanup_old_alerts():
    """Clean up old subscription alerts"""
    try:
        # Delete alerts older than 90 days
        old_alerts = SubscriptionAlert.objects.filter(
            created_at__lt=timezone.now() - timedelta(days=90)
        )
        
        count = old_alerts.count()
        old_alerts.delete()
        
        logger.info(f"Cleaned up {count} old subscription alerts")
        
    except Exception as e:
        logger.error(f"Error cleaning up old alerts: {str(e)}")


@shared_task
def update_subscription_analytics():
    """Update subscription analytics and metrics"""
    try:
        from django.db.models import Count, Sum, Avg
        from django.core.cache import cache
        
        # Calculate metrics
        total_subscriptions = Subscription.objects.count()
        active_subscriptions = Subscription.objects.filter(status='active').count()
        expired_subscriptions = Subscription.objects.filter(status='expired').count()
        
        # Revenue metrics
        total_revenue = Subscription.objects.aggregate(
            total=Sum('amount_paid')
        )['total'] or 0
        
        monthly_revenue = Subscription.objects.filter(
            created_at__gte=timezone.now().replace(day=1)
        ).aggregate(
            total=Sum('amount_paid')
        )['total'] or 0
        
        # Plan popularity
        plan_stats = Subscription.objects.values(
            'plan__name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Cache metrics
        cache_data = {
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'total_revenue': float(total_revenue),
            'monthly_revenue': float(monthly_revenue),
            'plan_stats': list(plan_stats),
            'updated_at': timezone.now().isoformat()
        }
        
        cache.set('subscription_analytics', cache_data, 3600)  # Cache for 1 hour
        
        logger.info("Updated subscription analytics")
        
    except Exception as e:
        logger.error(f"Error updating subscription analytics: {str(e)}")


@shared_task
def send_upgrade_suggestions():
    """Send upgrade suggestions to users based on usage patterns"""
    try:
        # Get basic plan users with high usage
        basic_subscriptions = Subscription.objects.filter(
            status='active',
            plan__plan_type='basic'
        ).select_related('user', 'plan')
        
        for subscription in basic_subscriptions:
            # Check feature usage
            high_usage_features = SubscriptionFeature.objects.filter(
                subscription=subscription,
                usage_count__gte=models.F('limit') * 0.8
            ).count()
            
            if high_usage_features >= 2:  # If 2 or more features are at 80% usage
                # Check if upgrade suggestion already sent this month
                suggestion_exists = SubscriptionAlert.objects.filter(
                    subscription=subscription,
                    alert_type='plan_upgrade',
                    created_at__gte=timezone.now().replace(day=1)
                ).exists()
                
                if not suggestion_exists:
                    # Create alert
                    alert = SubscriptionAlert.objects.create(
                        subscription=subscription,
                        alert_type='plan_upgrade',
                        message='Based on your usage pattern, you might benefit from upgrading '
                               'to a premium plan for better features and higher limits.'
                    )
                    
                    # Send notification
                    send_notification.delay(
                        user_id=subscription.user.id,
                        title='Upgrade Suggestion',
                        message=alert.message,
                        notification_type='upgrade_suggestion'
                    )
                    
                    logger.info(f"Upgrade suggestion sent for subscription {subscription.id}")
        
        logger.info("Processed upgrade suggestions")
        
    except Exception as e:
        logger.error(f"Error sending upgrade suggestions: {str(e)}")