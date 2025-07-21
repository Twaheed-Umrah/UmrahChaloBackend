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
    list_display = ('email', 'username', 'user_type', 'is_verified', 'is_active', 'created_at')
    list_filter = ('user_type', 'is_verified', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'username', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('phone',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Other info', {'fields': ('user_type', 'is_verified', 'last_login', 'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2', 'user_type', 'is_verified')}
        ),
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']


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
    search_fields = ('user__email', 'session_key')


@admin.register(ServiceProviderProfile)
class ServiceProviderProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'business_email', 'business_phone', 'verification_status', 'is_active', 'is_featured')
    list_filter = ('verification_status', 'is_active', 'is_featured', 'business_type')
    search_fields = ('business_name', 'user__email', 'business_email')


@admin.register(SavedPackage)
class SavedPackageAdmin(admin.ModelAdmin):
    list_display = ('user', 'package', 'created_at')
    search_fields = ('user__email', 'package__title')


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'ip_address', 'created_at')
    list_filter = ('activity_type',)
    search_fields = ('user__email', 'description')
    ordering = ('-created_at',)
