from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for any ViewSets (if needed in the future)
router = DefaultRouter()

app_name = 'authentication'

urlpatterns = [
    # Authentication
    path('auth/', include([
        path('register/', views.UserRegistrationView.as_view(), name='user-registration'),
        path('login/', views.UserLoginView.as_view(), name='user-login'),
        path('logout/', views.LogoutView.as_view(), name='user-logout'),
        path('token/refresh/', views.CustomTokenRefreshView.as_view(), name='token-refresh'),
    ])),
    
    # OTP
    path('otp/', include([
        path('login/', views.OTPLoginView.as_view(), name='otp-login'),
        path('verify/', views.OTPVerificationView.as_view(), name='otp-verification'),
        path('resend/', views.resend_otp, name='resend-otp'),
    ])),
    
    # Password
    path('password/', include([
        path('reset/', views.PasswordResetView.as_view(), name='password-reset'),
        path('reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
        path('change/', views.ChangePasswordView.as_view(), name='password-change'),
    ])),
    
    # Profile
    path('profile/', include([
        path('', views.UserProfileView.as_view(), name='user-profile'),
        path('stats/', views.user_stats, name='user-stats'),
        path('dashboard/', views.dashboard_stats, name='dashboard-stats'),
        path('preferences/', views.user_preferences, name='user-preferences'),
        path('preferences/update/', views.update_user_preferences, name='update-user-preferences'),
    ])),
    
    # Account Management
    path('account/', include([
        path('deactivate/', views.deactivate_account, name='deactivate-account'),
        path('reactivate/', views.reactivate_account, name='reactivate-account'),
        path('export/', views.export_user_data, name='export-user-data'),
        path('delete/', views.delete_user_account, name='delete-user-account'),
    ])),
    
    # Verification
    path('verify/', include([
        path('email/', views.EmailVerificationView.as_view(), name='email-verification'),
        path('phone/', views.PhoneVerificationView.as_view(), name='phone-verification'),
    ])),
    
    # Notifications
    path('notifications/', include([
        path('settings/', views.notification_settings, name='notification-settings'),
        path('settings/update/', views.update_notification_settings, name='update-notification-settings'),
    ])),
    
    # Service Providers
    path('providers/', include([
        path('register/', views.ServiceProviderRegistrationView.as_view(), name='provider-registration'),
        path('', views.ServiceProviderListView.as_view(), name='provider-list'),
        path('<int:pk>/', views.ServiceProviderDetailView.as_view(), name='provider-detail'),
        path('<int:provider_id>/verify/', views.ProviderVerificationView.as_view(), name='provider-verification'),
    ])),
        
    # Activity & Tracking
    path('tracking/', include([
        path('activities/', views.UserActivityListView.as_view(), name='user-activities'),
        path('sessions/', views.UserSessionListView.as_view(), name='user-sessions'),
        path('login-attempts/', views.LoginAttemptListView.as_view(), name='login-attempts'),
    ])),
    
    # Saved Packages
    path('saved-packages/', include([
        path('', views.SavedPackageListCreateView.as_view(), name='saved-packages'),
        path('<int:pk>/', views.SavedPackageDetailView.as_view(), name='saved-package-detail'),
    ])),
    
    # Admin
    path('admin/', include([
        path('users/', views.UserManagementListView.as_view(), name='admin-user-list'),
        path('users/bulk-action/', views.BulkUserActionView.as_view(), name='admin-bulk-action'),
        path('dashboard/', views.admin_dashboard_stats, name='admin-dashboard'),
    ])),
]