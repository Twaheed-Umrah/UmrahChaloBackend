# views.py (API Views)
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer


class NotificationListView(generics.ListAPIView):
    """Get user's notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related('template').order_by('-created_at')


class UnreadNotificationListView(generics.ListAPIView):
    """Get user's unread notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user,
            status__in=['pending', 'sent']
        ).select_related('template').order_by('-created_at')


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
