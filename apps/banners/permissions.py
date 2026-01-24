from rest_framework import permissions
from apps.core.models import UserRole

class PublicReadAdminWrite(permissions.BasePermission):
    """
    SIMPLE PERMISSION:
    - Read (GET, HEAD, OPTIONS): PUBLIC (everyone)
    - Write (POST, PUT, PATCH, DELETE): Admin/SuperAdmin only
    """
    
    def has_permission(self, request, view):
        # Read operations: ALLOW EVERYONE
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write operations: ONLY Admin/SuperAdmin
        return (
            request.user.is_authenticated and
            request.user.user_type in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        )