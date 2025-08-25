from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Notification Lists
    path('', views.NotificationListView.as_view(), name='notification_list'),
    path('unread/', views.UnreadNotificationListView.as_view(), name='unread_notifications'),
    
    # Notification Actions
    path('<int:notification_id>/read/', views.mark_notification_read, name='mark_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    
    # Notification Preferences
    path('preferences/', views.NotificationPreferenceView.as_view(), name='notification_preferences'),
]

# # Get all notifications
# GET /api/notifications/

# # Get unread notifications
# GET /api/notifications/unread/

# # Mark notification as read
# POST /api/notifications/123/read/

# # Mark all as read
# POST /api/notifications/mark-all-read/

# # Get notification preferences
# GET /api/notifications/preferences/

# # Update notification preferences
# PUT /api/notifications/preferences/