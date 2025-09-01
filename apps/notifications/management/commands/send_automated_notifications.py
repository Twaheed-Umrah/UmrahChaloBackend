# management/commands/send_daily_notifications.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
from notifications.services import NotificationService
from subscriptions.models import Subscription  # Adjust import based on your app structure
from apps.authentication.models import User  # Adjust import based on your app structure
from notifications.models import Notification
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send daily automatic notifications for subscription expiry and package upload reminders'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what notifications would be sent without actually sending them',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force send notifications even if already sent today',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting daily notification job (dry_run={dry_run})')
        )
        
        # Send subscription expiry notifications (5 days before expiry)
        self.send_subscription_expiry_notifications(dry_run, force)
        
        # Send subscription reminder notifications (expired subscriptions)
        self.send_subscription_reminder_notifications(dry_run, force)
        
        # Send package upload reminder notifications
        self.send_package_upload_reminders(dry_run, force)
        
        self.stdout.write(
            self.style.SUCCESS('Daily notification job completed successfully')
        )

    def send_subscription_expiry_notifications(self, dry_run=False, force=False):
        """Send notifications 5 days before subscription expires"""
        target_date = timezone.now().date() + timedelta(days=5)
        
        # Get subscriptions expiring in 5 days
        expiring_subscriptions = Subscription.objects.filter(
            end_date=target_date,
            is_active=True
        ).select_related('user', 'plan')
        
        sent_count = 0
        for subscription in expiring_subscriptions:
            # Check if notification already sent today (unless force is True)
            if not force and self._notification_sent_today(
                subscription.user, 'subscription_expiry'
            ):
                continue
            
            if dry_run:
                self.stdout.write(
                    f'Would send subscription expiry notification to {subscription.user.email}'
                )
            else:
                try:
                    NotificationService.send_subscription_expiry_notification(subscription)
                    sent_count += 1
                    self.stdout.write(
                        f'Sent subscription expiry notification to {subscription.user.email}'
                    )
                except Exception as e:
                    logger.error(f'Failed to send subscription expiry notification: {e}')
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Sent {sent_count} subscription expiry notifications')
            )

    def send_subscription_reminder_notifications(self, dry_run=False, force=False):
        """Send reminders for expired subscriptions"""
        today = timezone.now().date()
        
        # Get expired subscriptions (ended yesterday or before)
        expired_subscriptions = Subscription.objects.filter(
            Q(end_date__lt=today) | Q(end_date=today, is_active=False),
            user__is_active=True
        ).select_related('user', 'plan')
        
        sent_count = 0
        for subscription in expired_subscriptions:
            # Check if notification already sent today (unless force is True)
            if not force and self._notification_sent_today(
                subscription.user, 'subscription_reminder'
            ):
                continue
            
            days_since_expiry = (today - subscription.end_date).days
            
            if dry_run:
                self.stdout.write(
                    f'Would send subscription reminder to {subscription.user.email} '
                    f'(expired {days_since_expiry} days ago)'
                )
            else:
                try:
                    NotificationService.send_subscription_reminder_notification(
                        subscription, days_before_expiry=0
                    )
                    sent_count += 1
                    self.stdout.write(
                        f'Sent subscription reminder to {subscription.user.email}'
                    )
                except Exception as e:
                    logger.error(f'Failed to send subscription reminder: {e}')
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Sent {sent_count} subscription reminder notifications')
            )

    def send_package_upload_reminders(self, dry_run=False, force=False):
        """Send package upload reminders to providers with expired subscriptions or new users"""
        today = timezone.now().date()
        
        # Get service providers with expired subscriptions or new users (within 7 days)
        providers = User.objects.filter(
            user_type='provider',  # Adjust field name based on your User model
            is_active=True
        ).select_related('subscription')  # Adjust based on your model relationship
        
        sent_count = 0
        for provider in providers:
            # Skip if notification already sent today (unless force is True)
            if not force and self._notification_sent_today(
                provider, 'package_upload_reminder'
            ):
                continue
            
            # Check if provider meets criteria
            should_send = False
            reason = ""
            
            # Check if user is newly created (within 7 days)
            if hasattr(provider, 'date_joined'):
                days_since_joined = (today - provider.date_joined.date()).days
                if days_since_joined <= 7:
                    should_send = True
                    reason = f"new user ({days_since_joined} days old)"
            
            # Check if subscription is expired
            if hasattr(provider, 'subscription') and provider.subscription:
                if provider.subscription.end_date < today:
                    should_send = True
                    days_expired = (today - provider.subscription.end_date).days
                    reason = f"expired subscription ({days_expired} days ago)"
            elif not hasattr(provider, 'subscription') or not provider.subscription:
                # No subscription means they need to upload packages
                should_send = True
                reason = "no active subscription"
            
            if should_send:
                if dry_run:
                    self.stdout.write(
                        f'Would send package upload reminder to {provider.email} ({reason})'
                    )
                else:
                    try:
                        NotificationService.send_package_upload_reminder_notification(provider)
                        sent_count += 1
                        self.stdout.write(
                            f'Sent package upload reminder to {provider.email} ({reason})'
                        )
                    except Exception as e:
                        logger.error(f'Failed to send package upload reminder: {e}')
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Sent {sent_count} package upload reminder notifications')
            )

    def _notification_sent_today(self, user, notification_type):
        """Check if notification of this type was already sent today"""
        today = timezone.now().date()
        return Notification.objects.filter(
            recipient=user,
            notification_type=notification_type,
            created_at__date=today
        ).exists()


# management/commands/send_manual_notifications.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from notifications.services import NotificationService
from subscriptions.models import Subscription
from users.models import User
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manually send notifications to specific users or groups'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['subscription_expiry', 'subscription_reminder', 'package_upload_reminder'],
            required=True,
            help='Type of notification to send',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Send to specific user ID',
        )
        parser.add_argument(
            '--user-email',
            type=str,
            help='Send to specific user email',
        )
        parser.add_argument(
            '--user-type',
            type=str,
            choices=['provider', 'pilgrim'],
            help='Send to all users of specific type',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what notifications would be sent without actually sending them',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force send even if notification was already sent today',
        )

    def handle(self, *args, **options):
        notification_type = options['type']
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting manual notification job: {notification_type}')
        )
        
        # Get target users
        users = self.get_target_users(options)
        
        if not users:
            self.stdout.write(
                self.style.ERROR('No users found matching the criteria')
            )
            return
        
        sent_count = 0
        for user in users:
            # Check if already sent today (unless force is True)
            if not force and self._notification_sent_today(user, notification_type):
                self.stdout.write(
                    f'Skipping {user.email} - notification already sent today'
                )
                continue
            
            if dry_run:
                self.stdout.write(f'Would send {notification_type} to {user.email}')
            else:
                try:
                    if notification_type == 'subscription_expiry':
                        subscription = getattr(user, 'subscription', None)
                        if subscription:
                            NotificationService.send_subscription_expiry_notification(subscription)
                        else:
                            self.stdout.write(f'No subscription found for {user.email}')
                            continue
                    
                    elif notification_type == 'subscription_reminder':
                        subscription = getattr(user, 'subscription', None)
                        if subscription:
                            NotificationService.send_subscription_reminder_notification(subscription)
                        else:
                            self.stdout.write(f'No subscription found for {user.email}')
                            continue
                    
                    elif notification_type == 'package_upload_reminder':
                        NotificationService.send_package_upload_reminder_notification(user)
                    
                    sent_count += 1
                    self.stdout.write(f'Sent {notification_type} to {user.email}')
                    
                except Exception as e:
                    logger.error(f'Failed to send notification to {user.email}: {e}')
                    self.stdout.write(
                        self.style.ERROR(f'Failed to send to {user.email}: {e}')
                    )
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully sent {sent_count} notifications')
            )

    def get_target_users(self, options):
        """Get users based on the provided criteria"""
        if options['user_id']:
            return User.objects.filter(id=options['user_id'])
        
        if options['user_email']:
            return User.objects.filter(email=options['user_email'])
        
        if options['user_type']:
            return User.objects.filter(
                user_type=options['user_type'],
                is_active=True
            )
        
        # If no specific criteria, return empty queryset
        return User.objects.none()

    def _notification_sent_today(self, user, notification_type):
        """Check if notification of this type was already sent today"""
        today = timezone.now().date()
        from notifications.models import Notification
        return Notification.objects.filter(
            recipient=user,
            notification_type=notification_type,
            created_at__date=today
        ).exists()