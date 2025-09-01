# views.py (Updated with Admin/Superadmin functionality)
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from .models import Notification, NotificationPreference,  NotificationLog
from .serializers import (
    NotificationSerializer, 
    NotificationPreferenceSerializer, 
    NotificationLogSerializer
)
from .services import NotificationService

User = get_user_model()

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        ).order_by('-created_at')   # removed select_related('template')


class UnreadNotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user,
            status__in=['pending', 'sent']
        ).order_by('-created_at')   # removed select_related('template')


class AdminNotificationDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
            return Notification.objects.none()
        
        return Notification.objects.select_related('recipient')  # removed template

# Admin/Superadmin Views
class AdminNotificationDetailView(generics.RetrieveDestroyAPIView):
    """Admin view to get and delete specific notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
            return Notification.objects.none()
        
        return Notification.objects.select_related('recipient', 'template')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """Get dashboard statistics for admin"""
    user = request.user
    if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Calculate stats
    total_notifications = Notification.objects.count()
    sent_notifications = Notification.objects.filter(status='sent').count()
    failed_notifications = Notification.objects.filter(status='failed').count()
    pending_notifications = Notification.objects.filter(status='pending').count()
    
    # Get notification counts by type (use notification_type field instead of template)
    type_stats = Notification.objects.values(
        'notification_type'
    ).annotate(
        count=Count('id')
    )
    
    # Get recent activity (last 7 days)
    seven_days_ago = timezone.now() - timezone.timedelta(days=7)
    recent_activity = Notification.objects.filter(
        created_at__gte=seven_days_ago
    ).values('created_at__date').annotate(count=Count('id')).order_by('created_at__date')
    
    return Response({
        'total_notifications': total_notifications,
        'sent_notifications': sent_notifications,
        'failed_notifications': failed_notifications,
        'pending_notifications': pending_notifications,
        'success_rate': (sent_notifications / total_notifications * 100) if total_notifications > 0 else 0,
        'type_stats': list(type_stats),
        'recent_activity': list(recent_activity)
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_bulk_notification(request):
    """Send bulk notifications to multiple users"""
    user = request.user
    if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    data = request.data
    title = data.get('title')
    message = data.get('message')
    target_user_type = data.get('target_user_type', 'all')
    
    if not title or not message:
        return Response(
            {'error': 'Title and message are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get target users based on user type
        if target_user_type == 'all':
            target_users = User.objects.filter(is_active=True)
        elif target_user_type == 'provider':
            target_users = User.objects.filter(user_type='vendor', is_active=True)
        elif target_user_type == 'pilgrim':
            target_users = User.objects.filter(user_type='customer', is_active=True)
        elif target_user_type == 'admin':
            target_users = User.objects.filter(
                Q(user_type='admin') | Q(user_type='super_admin') | Q(is_superuser=True),
                is_active=True
            )
        else:
            return Response(
                {'error': 'Invalid target user type'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create notifications for all target users
        notifications = []
        for target_user in target_users:
            notification = Notification.objects.create(
                recipient=target_user,
                title=title,
                message=message,
                priority=data.get('priority', 'medium'),
                data=data.get('data', {}),
                created_by=user
            )
            notifications.append(notification)
        
        # Send notifications
        channels = {
            'send_email': data.get('send_email', False),
            'send_sms': data.get('send_sms', False),
            'send_app': data.get('send_app', True)
        }
        
        for notification in notifications:
            NotificationService.send_notification(notification, **channels)
        
        return Response({
            'success': True,
            'message': f'Bulk notification sent to {len(notifications)} users',
            'notification_count': len(notifications)
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to send bulk notification: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resend_failed_notifications(request):
    """Resend all failed notifications"""
    user = request.user
    if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        failed_notifications = Notification.objects.filter(status='failed')
        resent_count = 0
        
        for notification in failed_notifications:
            try:
                NotificationService.send_notification(notification)
                resent_count += 1
            except Exception as e:
                # Log the error but continue with other notifications
                print(f"Failed to resend notification {notification.id}: {str(e)}")
        
        return Response({
            'success': True,
            'message': f'{resent_count} failed notifications resent successfully'
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to resend notifications: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Notification Logs Views
class NotificationLogListView(generics.ListAPIView):
    """List notification logs for admin"""
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
            return NotificationLog.objects.none()
        
        return NotificationLog.objects.select_related(
            'notification', 'notification__recipient'
        ).order_by('-created_at')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def delivery_stats(request):
    """Get delivery statistics for admin"""
    user = request.user
    if not (user.user_type in ['admin', 'super_admin'] or user.is_superuser):
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Calculate delivery stats
    total_logs = NotificationLog.objects.count()
    delivered_logs = NotificationLog.objects.filter(status='delivered').count()
    failed_logs = NotificationLog.objects.filter(status='failed').count()
    pending_logs = NotificationLog.objects.filter(status='pending').count()
    
    # Stats by channel
    email_stats = NotificationLog.objects.filter(channel='email').aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status='delivered')),
        failed=Count('id', filter=Q(status='failed'))
    )
    
    sms_stats = NotificationLog.objects.filter(channel='sms').aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status='delivered')),
        failed=Count('id', filter=Q(status='failed'))
    )
    
    app_stats = NotificationLog.objects.filter(channel='app').aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status='delivered')),
        failed=Count('id', filter=Q(status='failed'))
    )
    
    return Response({
        'total_logs': total_logs,
        'delivered_logs': delivered_logs,
        'failed_logs': failed_logs,
        'pending_logs': pending_logs,
        'delivery_rate': (delivered_logs / total_logs * 100) if total_logs > 0 else 0,
        'channel_stats': {
            'email': email_stats,
            'sms': sms_stats,
            'app': app_stats
        }
    })


# Existing views continue below...

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    """Mark a notification as read"""
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user
    )
    
    notification.mark_as_read()
    
    return Response({
        'success': True,
        'message': 'Notification marked as read'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    """Mark all notifications as read for user"""
    count = Notification.objects.filter(
        recipient=request.user,
        status__in=['pending', 'sent']
    ).count()
    
    Notification.objects.filter(
        recipient=request.user,
        status__in=['pending', 'sent']
    ).update(status='read', read_at=timezone.now())
    
    return Response({
        'success': True,
        'message': f'{count} notifications marked as read'
    })


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """Get and update user notification preferences"""
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        preference, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preference


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_manual_notification(request):
    """Send manual notification (superadmin only)"""
    if not request.user.is_superuser:
        return Response(
            {'error': 'Permission denied. Superadmin access required.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    data = request.data
    required_fields = ['user_ids', 'notification_type', 'title', 'message']
    
    # Validate required fields
    for field in required_fields:
        if not data.get(field):
            return Response(
                {'error': f'{field} is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    try:
        notifications = NotificationService.send_manual_notification(
            user_ids=data['user_ids'],
            notification_type=data['notification_type'],
            title=data['title'],
            message=data['message'],
            data=data.get('data', {}),
            priority=data.get('priority', 'medium'),
            channels=data.get('channels', None)
        )
        
        return Response({
            'success': True,
            'message': f'{len(notifications)} notifications sent successfully',
            'notification_ids': [n.id for n in notifications]
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to send notifications: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_subscription_reminder_manual(request, subscription_id):
    """Manually send subscription reminder (superadmin only)"""
    if not request.user.is_superuser:
        return Response(
            {'error': 'Permission denied. Superadmin access required.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        from apps.subscriptions.models import Subscription
        subscription = get_object_or_404(Subscription, id=subscription_id)
        
        notification = NotificationService.send_subscription_reminder_notification(
            subscription, days_before_expiry=5
        )
        
        if notification:
            return Response({
                'success': True,
                'message': 'Subscription reminder sent successfully',
                'notification_id': notification.id
            })
        else:
            return Response(
                {'error': 'Failed to send notification'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    except Exception as e:
        return Response(
            {'error': f'Failed to send subscription reminder: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_package_reminder_manual(request, user_id):
    """Manually send package upload reminder (superadmin only)"""
    if not request.user.is_superuser:
        return Response(
            {'error': 'Permission denied. Superadmin access required.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        user = get_object_or_404(User, id=user_id)
        
        notification = NotificationService.send_package_upload_reminder_notification(user)
        
        if notification:
            return Response({
                'success': True,
                'message': 'Package upload reminder sent successfully',
                'notification_id': notification.id
            })
        else:
            return Response(
                {'error': 'Failed to send notification'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    except Exception as e:
        return Response(
            {'error': f'Failed to send package reminder: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )