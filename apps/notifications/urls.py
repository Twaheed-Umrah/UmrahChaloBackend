# urls.py (Updated with admin endpoints)
from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # User Notification Endpoints
    path('', views.NotificationListView.as_view(), name='notification_list'),
    path('unread/', views.UnreadNotificationListView.as_view(), name='unread_notifications'),
    
    # Notification Actions
    path('<int:notification_id>/read/', views.mark_notification_read, name='mark_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    
    # Notification Preferences
    path('preferences/', views.NotificationPreferenceView.as_view(), name='notification_preferences'),
    
    
    path('admin/notifications/<int:pk>/', views.AdminNotificationDetailView.as_view(), name='admin_notification_detail'),
    path('admin/notifications/dashboard_stats/', views.dashboard_stats, name='dashboard_stats'),
    
    # Bulk Operations
    path('bulk/', views.send_bulk_notification, name='send_bulk_notification'),
    path('admin/notifications/resend_failed/', views.resend_failed_notifications, name='resend_failed'),
    # Notification Logs
    path('logs/', views.NotificationLogListView.as_view(), name='notification_logs'),
    path('logs/delivery_stats/', views.delivery_stats, name='delivery_stats'),
    
    # Manual Notifications (Superadmin)
    path('manual/send/', views.send_manual_notification, name='send_manual_notification'),
    path('manual/subscription-reminder/<int:subscription_id>/', 
         views.send_subscription_reminder_manual, name='send_subscription_reminder_manual'),
    path('manual/package-reminder/<int:user_id>/', 
         views.send_package_reminder_manual, name='send_package_reminder_manual'),
]

# API Endpoint Documentation:
"""
User Endpoints:
- GET /api/notify/ - Get user's notifications
- GET /api/notify/unread/ - Get unread notifications
- POST /api/notify/{id}/read/ - Mark notification as read
- POST /api/notify/mark-all-read/ - Mark all as read
- GET /api/notify/preferences/ - Get notification preferences
- PUT /api/notify/preferences/ - Update notification preferences

Admin/Superadmin Endpoints:
- GET /api/notify/admin/notifications/ - Get all notifications (admin view)
- POST /api/notify/admin/notifications/ - Create/send new notification
- GET /api/notify/admin/notifications/{id}/ - Get specific notification
- DELETE /api/notify/admin/notifications/{id}/ - Delete notification
- GET /api/notify/admin/notifications/dashboard_stats/ - Get dashboard statistics
- POST /api/notify/admin/notifications/resend_failed/ - Resend failed notifications

Bulk Operations:
- POST /api/notify/bulk/ - Send bulk notifications

Template Management:
- GET /api/notify/templates/ - List notification templates
- POST /api/notify/templates/ - Create new template
- GET /api/notify/templates/{id}/ - Get specific template
- PUT /api/notify/templates/{id}/ - Update template
- DELETE /api/notify/templates/{id}/ - Delete template

Logs & Analytics:
- GET /api/notify/logs/ - Get notification logs
- GET /api/notify/logs/delivery_stats/ - Get delivery statistics

Manual Notifications:
- POST /api/notify/manual/send/ - Send manual notification to specific users
- POST /api/notify/manual/subscription-reminder/{subscription_id}/ - Send subscription reminder
- POST /api/notify/manual/package-reminder/{user_id}/ - Send package upload reminder
"""