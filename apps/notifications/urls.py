from django.urls import path, include
from .views import (
    NotificationViewSet,
    NotificationTemplateViewSet,
    NotificationPreferenceViewSet,
    NotificationLogViewSet,
    BulkNotificationViewSet,
    AdminNotificationViewSet
)

urlpatterns = [
    # Notification endpoints
    path('notifications/', NotificationViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='notification-list'),
    path('notifications/<int:pk>/', NotificationViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='notification-detail'),
    path('notifications/<int:pk>/mark_read/', NotificationViewSet.as_view({
        'post': 'mark_read'
    }), name='notification-mark-read'),
    path('notifications/mark_all_read/', NotificationViewSet.as_view({
        'post': 'mark_all_read'
    }), name='notification-mark-all-read'),
    path('notifications/mark_multiple_read/', NotificationViewSet.as_view({
        'post': 'mark_multiple_read'
    }), name='notification-mark-multiple-read'),
    path('notifications/stats/', NotificationViewSet.as_view({
        'get': 'stats'
    }), name='notification-stats'),
    path('notifications/unread_count/', NotificationViewSet.as_view({
        'get': 'unread_count'
    }), name='notification-unread-count'),
    path('notifications/clear_all/', NotificationViewSet.as_view({
        'delete': 'clear_all'
    }), name='notification-clear-all'),

    # Template endpoints
    path('templates/', NotificationTemplateViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='notificationtemplate-list'),
    path('templates/<int:pk>/', NotificationTemplateViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='notificationtemplate-detail'),
    path('templates/<int:pk>/test_send/', NotificationTemplateViewSet.as_view({
        'post': 'test_send'
    }), name='notificationtemplate-test-send'),

    # Preference endpoints
    path('preferences/', NotificationPreferenceViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='notificationpreference-list'),
    path('preferences/<int:pk>/', NotificationPreferenceViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='notificationpreference-detail'),
    path('preferences/my_preferences/', NotificationPreferenceViewSet.as_view({
        'get': 'my_preferences'
    }), name='notificationpreference-my-preferences'),
    path('preferences/update_preferences/', NotificationPreferenceViewSet.as_view({
        'patch': 'update_preferences'
    }), name='notificationpreference-update-preferences'),

    # Log endpoints
    path('logs/', NotificationLogViewSet.as_view({
        'get': 'list'
    }), name='notificationlog-list'),
    path('logs/<int:pk>/', NotificationLogViewSet.as_view({
        'get': 'retrieve'
    }), name='notificationlog-detail'),
    path('logs/delivery_stats/', NotificationLogViewSet.as_view({
        'get': 'delivery_stats'
    }), name='notificationlog-delivery-stats'),

    # Bulk notification endpoints
    path('bulk/', BulkNotificationViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='bulknotification-list'),
    path('bulk/<int:pk>/', BulkNotificationViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='bulknotification-detail'),
    path('bulk/<int:pk>/send_now/', BulkNotificationViewSet.as_view({
        'post': 'send_now'
    }), name='bulknotification-send-now'),
    path('bulk/<int:pk>/cancel/', BulkNotificationViewSet.as_view({
        'post': 'cancel'
    }), name='bulknotification-cancel'),
    path('bulk/<int:pk>/preview_recipients/', BulkNotificationViewSet.as_view({
        'get': 'preview_recipients'
    }), name='bulknotification-preview-recipients'),

    # Admin notification endpoints
    path('admin/notifications/', AdminNotificationViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='adminnotification-list'),
    path('admin/notifications/<int:pk>/', AdminNotificationViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='adminnotification-detail'),
    path('admin/notifications/dashboard_stats/', AdminNotificationViewSet.as_view({
        'get': 'dashboard_stats'
    }), name='adminnotification-dashboard-stats'),
    path('admin/notifications/resend_failed/', AdminNotificationViewSet.as_view({
        'post': 'resend_failed'
    }), name='adminnotification-resend-failed'),
    path('admin/notifications/bulk_update_status/', AdminNotificationViewSet.as_view({
        'post': 'bulk_update_status'
    }), name='adminnotification-bulk-update-status'),
    path('admin/notifications/bulk_delete/', AdminNotificationViewSet.as_view({
        'post': 'bulk_delete'
    }), name='adminnotification-bulk-delete'),
    path('admin/notifications/export_notifications/', AdminNotificationViewSet.as_view({
        'get': 'export_notifications'
    }), name='adminnotification-export-notifications'),
]
