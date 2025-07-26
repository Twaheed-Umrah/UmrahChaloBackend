from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    OTPVerification,
    LoginAttempt,
    UserSession,
    ServiceProviderProfile,
    SavedPackage,
    UserActivity
)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email', 'username', 'full_name', 'user_type', 'is_verified',
        'latitude', 'longitude', 'is_active', 'created_at'
    )
    list_filter = ('user_type', 'is_verified', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'username', 'phone', 'full_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'last_login', 'location_updated_at')

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {
            'fields': (
                'full_name', 'phone', 'user_type', 'is_verified',
                'latitude', 'longitude', 'location_address', 'location_updated_at'
            )
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Timestamps', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'username', 'password1', 'password2',
                'user_type', 'is_verified'
            ),
        }),
    )

# Register other models with default or enhanced admin options
@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'purpose', 'is_used', 'expires_at', 'created_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('user__email', 'otp')

@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('email', 'ip_address', 'success', 'created_at')
    list_filter = ('success',)
    search_fields = ('email', 'ip_address')

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'session_key', 'ip_address', 'is_active', 'created_at', 'last_activity')
    list_filter = ('is_active',)
    search_fields = ('user__email', 'session_key', 'ip_address')

@admin.register(ServiceProviderProfile)
class ServiceProviderProfileAdmin(admin.ModelAdmin):
    list_display = (
        'business_name', 'user', 'business_type', 'verification_status',
        'is_active', 'is_featured', 'created_at'
    )
    list_filter = ('business_type', 'verification_status', 'is_active', 'is_featured')
    search_fields = ('business_name', 'user__email', 'business_phone', 'business_email')

@admin.register(SavedPackage)
class SavedPackageAdmin(admin.ModelAdmin):
    list_display = ('user', 'package', 'created_at')
    search_fields = ('user__email', 'package__title')
    list_filter = ('created_at',)

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'ip_address', 'created_at')
    list_filter = ('activity_type', 'created_at')
    search_fields = ('user__email', 'description', 'ip_address')
