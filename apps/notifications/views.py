from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q, Count, Case, When, IntegerField
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.core.permissions import IsAdmin, IsServiceProvider
from apps.core.pagination import LargeResultsSetPagination
from .models import (
    Notification, NotificationTemplate, NotificationPreference,
    NotificationLog, BulkNotification
)
from .serializers import (
    NotificationSerializer, NotificationListSerializer, NotificationTemplateSerializer,
    NotificationPreferenceSerializer, NotificationLogSerializer,
    BulkNotificationSerializer, CreateNotificationSerializer,
    NotificationStatsSerializer, MarkNotificationReadSerializer
)
from .utils import NotificationService
from .filters import NotificationFilter


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for user notifications"""
    
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = NotificationFilter
    search_fields = ['title', 'message']
    ordering_fields = ['created_at', 'priority', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Get notifications for the current user"""
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related('template', 'recipient')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return NotificationListSerializer
        elif self.action == 'create':
            return CreateNotificationSerializer
        return NotificationSerializer
    
    def perform_create(self, serializer):
        """Create notification with current user as recipient if not specified"""
        if not serializer.validated_data.get('recipient'):
            serializer.save(recipient=self.request.user)
        else:
            serializer.save()
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        
        return Response({
            'message': 'Notification marked as read',
            'notification_id': notification.id,
            'read_at': notification.read_at
        })
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        updated_count = Notification.objects.filter(
            recipient=request.user,
            status__in=['pending', 'sent']
        ).update(
            status='read',
            read_at=timezone.now()
        )
        
        return Response({
            'message': f'{updated_count} notifications marked as read',
            'updated_count': updated_count
        })
    
    @action(detail=False, methods=['post'])
    def mark_multiple_read(self, request):
        """Mark multiple notifications as read"""
        serializer = MarkNotificationReadSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        notification_ids = serializer.validated_data['notification_ids']
        
        updated_count = Notification.objects.filter(
            id__in=notification_ids,
            recipient=request.user
        ).update(
            status='read',
            read_at=timezone.now()
        )
        
        return Response({
            'message': f'{updated_count} notifications marked as read',
            'updated_count': updated_count
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get notification statistics"""
        user = request.user
        
        # Base queryset
        notifications = Notification.objects.filter(recipient=user)
        
        # Calculate stats
        stats = {
            'total_notifications': notifications.count(),
            'unread_notifications': notifications.filter(status__in=['pending', 'sent']).count(),
            'sent_notifications': notifications.filter(status='sent').count(),
            'failed_notifications': notifications.filter(status='failed').count(),
            
            # Channel stats
            'email_sent': notifications.filter(email_sent=True).count(),
            'sms_sent': notifications.filter(sms_sent=True).count(),
            'app_sent': notifications.filter(app_sent=True).count(),
            
            # Time-based stats
            'notifications_today': notifications.filter(
                created_at__date=timezone.now().date()
            ).count(),
            'notifications_this_week': notifications.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),
            'notifications_this_month': notifications.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=30)
            ).count(),
        }
        
        serializer = NotificationStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get unread notification count"""
        count = Notification.objects.filter(
            recipient=request.user,
            status__in=['pending', 'sent']
        ).count()
        
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['delete'])
    def clear_all(self, request):
        """Clear all notifications"""
        deleted_count = Notification.objects.filter(
            recipient=request.user
        ).delete()[0]
        
        return Response({
            'message': f'{deleted_count} notifications cleared',
            'deleted_count': deleted_count
        })


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for notification templates (Admin only)"""
    
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAdmin]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['notification_type', 'is_active']
    search_fields = ['title', 'notification_type']
    ordering_fields = ['notification_type', 'created_at']
    ordering = ['notification_type']
    
    @action(detail=True, methods=['post'])
    def test_send(self, request, pk=None):
        """Test send notification template"""
        template = self.get_object()
        
        # Create test notification
        service = NotificationService()
        notification = service.create_notification(
            recipient=request.user,
            template_type=template.notification_type,
            data={
                'test_user': request.user.get_full_name(),
                'test_date': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'test_message': 'This is a test notification'
            },
            priority='low'
        )
        
        return Response({
            'message': 'Test notification sent',
            'notification_id': notification.id
        })


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for notification preferences"""
    
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get preference for current user"""
        return NotificationPreference.objects.filter(user=self.request.user)
    
    def get_object(self):
        """Get or create preference for current user"""
        preference, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preference
    
    @action(detail=False, methods=['get'])
    def my_preferences(self, request):
        """Get current user's preferences"""
        preference = self.get_object()
        serializer = self.get_serializer(preference)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def update_preferences(self, request):
        """Update current user's preferences"""
        preference = self.get_object()
        serializer = self.get_serializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'message': 'Preferences updated successfully',
            'preferences': serializer.data
        })


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for notification logs (Admin only)"""
    
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAdmin]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['channel', 'delivered', 'provider']
    search_fields = ['notification__title', 'notification__recipient__email']
    ordering_fields = ['sent_at', 'delivered']
    ordering = ['-sent_at']
    
    @action(detail=False, methods=['get'])
    def delivery_stats(self, request):
        """Get delivery statistics"""
        logs = self.get_queryset()
        
        stats = {
            'total_attempts': logs.count(),
            'successful_deliveries': logs.filter(delivered=True).count(),
            'failed_deliveries': logs.filter(delivered=False).count(),
            
            # Channel stats
            'email_attempts': logs.filter(channel='email').count(),
            'sms_attempts': logs.filter(channel='sms').count(),
            'app_attempts': logs.filter(channel='app').count(),
            
            # Success rates by channel
            'email_success_rate': self._calculate_success_rate(logs, 'email'),
            'sms_success_rate': self._calculate_success_rate(logs, 'sms'),
            'app_success_rate': self._calculate_success_rate(logs, 'app'),
        }
        
        return Response(stats)
    
    def _calculate_success_rate(self, logs, channel):
        """Calculate success rate for a channel"""
        channel_logs = logs.filter(channel=channel)
        total = channel_logs.count()
        if total == 0:
            return 0.0
        
        successful = channel_logs.filter(delivered=True).count()
        return round((successful / total) * 100, 2)


class BulkNotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for bulk notifications (Admin only)"""
    
    queryset = BulkNotification.objects.all()
    serializer_class = BulkNotificationSerializer
    permission_classes = [IsAdmin]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'target_user_type']
    search_fields = ['title', 'message']
    ordering_fields = ['created_at', 'status', 'scheduled_at']
    ordering = ['-created_at']
    
    def perform_create(self, serializer):
        """Create bulk notification with current user as creator"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def send_now(self, request, pk=None):
        """Send bulk notification immediately"""
        bulk_notification = self.get_object()
        
        if bulk_notification.status not in ['draft', 'scheduled']:
            return Response(
                {'error': 'Bulk notification cannot be sent in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Send bulk notification asynchronously using the correct task
        try:
            from .tasks import send_bulk_notifications
            
            # Get provider IDs based on target_user_type
            service = NotificationService()
            recipients = service._get_bulk_recipients(bulk_notification)
            
            # Extract provider IDs (assuming recipients are users with provider profiles)
            provider_ids = []
            for user in recipients:
                if hasattr(user, 'serviceprovider'):
                    provider_ids.append(user.serviceprovider.id)
            
            # Determine notification type and context based on bulk notification
            notification_type = bulk_notification.notification_type or 'general'
            context = {
                'title': bulk_notification.title,
                'message': bulk_notification.message,
                'created_by': bulk_notification.created_by.get_full_name(),
            }
            
            # Send bulk notifications
            send_bulk_notifications.delay(provider_ids, notification_type, context)
            
        except ImportError:
            return Response(
                {'error': 'Celery tasks not available'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to send bulk notification: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update status
        bulk_notification.status = 'sending'
        bulk_notification.save()
        
        return Response({
            'message': 'Bulk notification is being sent',
            'bulk_notification_id': bulk_notification.id
        })
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel bulk notification"""
        bulk_notification = self.get_object()
        
        if bulk_notification.status in ['completed', 'failed']:
            return Response(
                {'error': 'Cannot cancel completed or failed bulk notification'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        bulk_notification.status = 'cancelled'
        bulk_notification.save()
        
        return Response({
            'message': 'Bulk notification cancelled',
            'bulk_notification_id': bulk_notification.id
        })
    
    @action(detail=True, methods=['get'])
    def preview_recipients(self, request, pk=None):
        """Preview recipients for bulk notification"""
        bulk_notification = self.get_object()
        
        service = NotificationService()
        recipients = service._get_bulk_recipients(bulk_notification)
        
        recipient_data = [{
            'id': user.id,
            'name': user.get_full_name(),
            'email': user.email,
            'role': getattr(user, 'role', 'Unknown'),
            'is_active': user.is_active
        } for user in recipients[:100]]  # Limit to first 100 for preview
        
        return Response({
            'total_recipients': len(recipients),
            'preview_recipients': recipient_data,
            'showing_count': len(recipient_data)
        })
    
    @action(detail=False, methods=['post'])
    def send_subscription_expiry_reminder(self, request):
        """Send subscription expiry reminder to providers"""
        try:
            from apps.authentication.models import ServiceProviderProfile
            from .tasks import send_bulk_notifications
            
            # Get providers with expiring subscriptions
            expiry_date = request.data.get('expiry_date')
            provider_ids = request.data.get('provider_ids', [])
            
            if not expiry_date:
                return Response(
                    {'error': 'expiry_date is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not provider_ids:
                # If no specific providers, get all active providers
                provider_ids = list(ServiceProviderProfile.objects.filter(
                    is_active=True
                ).values_list('id', flat=True))
            
            context = {
                'expiry_date': expiry_date,
            }
            
            # Send bulk notifications
            send_bulk_notifications.delay(provider_ids, 'subscription_expiry', context)
            
            return Response({
                'message': f'Subscription expiry reminder sent to {len(provider_ids)} providers',
                'provider_count': len(provider_ids)
            })
            
        except Exception as e:
            return Response(
                {'error': f'Failed to send subscription expiry reminder: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def send_maintenance_notification(self, request):
        """Send system maintenance notification"""
        try:
            from apps.authentication.models import ServiceProviderProfile
            from .tasks import send_bulk_notifications
            
            maintenance_date = request.data.get('maintenance_date')
            duration = request.data.get('duration')
            provider_ids = request.data.get('provider_ids', [])
            
            if not maintenance_date:
                return Response(
                    {'error': 'maintenance_date is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not provider_ids:
                # Send to all active providers
                provider_ids = list(ServiceProviderProfile.objects.filter(
                    is_active=True
                ).values_list('id', flat=True))
            
            context = {
                'maintenance_date': maintenance_date,
                'duration': duration or 'TBD',
            }
            
            # Send bulk notifications
            send_bulk_notifications.delay(provider_ids, 'system_maintenance', context)
            
            return Response({
                'message': f'Maintenance notification sent to {len(provider_ids)} providers',
                'provider_count': len(provider_ids)
            })
            
        except Exception as e:
            return Response(
                {'error': f'Failed to send maintenance notification: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def send_new_features_notification(self, request):
        """Send new features notification"""
        try:
            from apps.authentication.models import ServiceProviderProfile
            from .tasks import send_bulk_notifications
            
            features = request.data.get('features')
            provider_ids = request.data.get('provider_ids', [])
            
            if not features:
                return Response(
                    {'error': 'features description is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not provider_ids:
                # Send to all active providers
                provider_ids = list(ServiceProviderProfile.objects.filter(
                    is_active=True
                ).values_list('id', flat=True))
            
            context = {
                'features': features,
            }
            
            # Send bulk notifications
            send_bulk_notifications.delay(provider_ids, 'new_features', context)
            
            return Response({
                'message': f'New features notification sent to {len(provider_ids)} providers',
                'provider_count': len(provider_ids)
            })
            
        except Exception as e:
            return Response(
                {'error': f'Failed to send new features notification: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminNotificationViewSet(viewsets.ModelViewSet):
    """Admin viewset for managing all notifications"""
    
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAdmin]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = NotificationFilter
    search_fields = ['title', 'message', 'recipient__email', 'recipient__first_name']
    ordering_fields = ['created_at', 'priority', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Get all notifications for admin"""
        return Notification.objects.select_related(
            'template', 'recipient'
        ).all()
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get dashboard statistics for admin"""
        notifications = self.get_queryset()
        
        # Time-based filters
        today = timezone.now().date()
        week_ago = today - timezone.timedelta(days=7)
        month_ago = today - timezone.timedelta(days=30)
        
        stats = {
            # Overall stats
            'total_notifications': notifications.count(),
            'active_users': notifications.values('recipient').distinct().count(),
            
            # Status distribution
            'pending_notifications': notifications.filter(status='pending').count(),
            'sent_notifications': notifications.filter(status='sent').count(),
            'failed_notifications': notifications.filter(status='failed').count(),
            'read_notifications': notifications.filter(status='read').count(),
            
            # Time-based stats
            'today_notifications': notifications.filter(created_at__date=today).count(),
            'week_notifications': notifications.filter(created_at__date__gte=week_ago).count(),
            'month_notifications': notifications.filter(created_at__date__gte=month_ago).count(),
            
            # Channel distribution
            'email_notifications': notifications.filter(email_sent=True).count(),
            'sms_notifications': notifications.filter(sms_sent=True).count(),
            'app_notifications': notifications.filter(app_sent=True).count(),
            
            # Template usage
            'template_usage': list(notifications.values(
                'template__notification_type'
            ).annotate(
                count=Count('id')
            ).order_by('-count')[:10])
        }
        
        return Response(stats)
    
    @action(detail=False, methods=['post'])
    def resend_failed(self, request):
        """Resend failed notifications"""
        notifications = self.get_queryset()
        failed_notifications = notifications.filter(
            status='failed',
            retry_count__lt=3
        )
        
        resent_count = 0
        service = NotificationService()
        
        for notification in failed_notifications:
            if notification.can_retry():
                try:
                    # Reset status and increment retry
                    notification.status = 'pending'
                    notification.increment_retry()
                    
                    # Send notification
                    preferences = service._get_user_preferences(notification.recipient)
                    service._send_notification(notification, preferences)
                    resent_count += 1
                except Exception as e:
                    # Log error but continue with other notifications
                    print(f"Error resending notification {notification.id}: {e}")
        
        return Response({
            'message': f'{resent_count} failed notifications have been queued for resending',
            'resent_count': resent_count
        })
    
    @action(detail=False, methods=['post'])
    def bulk_update_status(self, request):
        """Bulk update notification status"""
        notification_ids = request.data.get('notification_ids', [])
        new_status = request.data.get('status')
        
        if not notification_ids:
            return Response(
                {'error': 'notification_ids are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_status not in ['pending', 'sent', 'failed', 'read']:
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_count = self.get_queryset().filter(
            id__in=notification_ids
        ).update(status=new_status)
        
        return Response({
            'message': f'{updated_count} notifications updated',
            'updated_count': updated_count
        })
    
    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        """Bulk delete notifications"""
        notification_ids = request.data.get('notification_ids', [])
        
        if not notification_ids:
            return Response(
                {'error': 'notification_ids are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        deleted_count = self.get_queryset().filter(
            id__in=notification_ids
        ).delete()[0]
        
        return Response({
            'message': f'{deleted_count} notifications deleted',
            'deleted_count': deleted_count
        })
    
    @action(detail=False, methods=['get'])
    def export_notifications(self, request):
        """Export notifications data"""
        import csv
        from django.http import HttpResponse
        
        # Get filtered notifications
        notifications = self.filter_queryset(self.get_queryset())
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="notifications.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Recipient', 'Title', 'Message', 'Status', 'Priority',
            'Created At', 'Sent At', 'Read At', 'Email Sent', 'SMS Sent', 'App Sent'
        ])
        
        for notification in notifications:
            writer.writerow([
                notification.id,
                notification.recipient.email,
                notification.title,
                notification.message,
                notification.status,
                notification.priority,
                notification.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                notification.sent_at.strftime('%Y-%m-%d %H:%M:%S') if notification.sent_at else '',
                notification.read_at.strftime('%Y-%m-%d %H:%M:%S') if notification.read_at else '',
                notification.email_sent,
                notification.sms_sent,
                notification.app_sent,
            ])
        
        return response