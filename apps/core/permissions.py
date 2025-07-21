from rest_framework import permissions
from apps.core.models import UserRole

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions are only allowed to the owner of the object.
        return obj.user == request.user

class IsPilgrim(permissions.BasePermission):
    """
    Custom permission to only allow pilgrims.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.PILGRIM
        )

class IsServiceProvider(permissions.BasePermission):
    """
    Custom permission to only allow service providers.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.PROVIDER
        )

class IsAdmin(permissions.BasePermission):
    """
    Custom permission to only allow admins.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.ADMIN
        )

class IsSuperAdmin(permissions.BasePermission):
    """
    Custom permission to only allow super admins.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.SUPER_ADMIN
        )

class IsAdminOrSuperAdmin(permissions.BasePermission):
    """
    Custom permission to only allow admins or super admins.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        )

class IsProviderOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow service providers or admins.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role in [UserRole.PROVIDER, UserRole.ADMIN, UserRole.SUPER_ADMIN]
        )

class IsVerifiedProvider(permissions.BasePermission):
    """
    Custom permission to only allow verified service providers.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.PROVIDER and
            request.user.profile.is_verified
        )

class IsActiveSubscription(permissions.BasePermission):
    """
    Custom permission to check if provider has active subscription.
    """
    def has_permission(self, request, view):
        if not (request.user.is_authenticated and hasattr(request.user, 'profile')):
            return False
        
        if request.user.profile.role != UserRole.PROVIDER:
            return True  # Allow non-providers
        
        # Check if provider has active subscription
        from apps.subscriptions.models import Subscription
        return Subscription.objects.filter(
            provider=request.user.profile,
            is_active=True
        ).exists()

class CanViewLead(permissions.BasePermission):
    """
    Custom permission to check if user can view lead.
    """
    def has_object_permission(self, request, view, obj):
        # Pilgrims can view their own leads
        if request.user.profile.role == UserRole.PILGRIM:
            return obj.pilgrim == request.user.profile
        
        # Providers can view leads sent to them
        if request.user.profile.role == UserRole.PROVIDER:
            return obj.providers.filter(id=request.user.profile.id).exists()
        
        # Admins can view all leads
        if request.user.profile.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return True
        
        return False

class CanManagePackage(permissions.BasePermission):
    """
    Custom permission to check if user can manage packages.
    """
    def has_object_permission(self, request, view, obj):
        # Providers can manage their own packages
        if request.user.profile.role == UserRole.PROVIDER:
            return obj.provider == request.user.profile
        
        # Admins can manage all packages
        if request.user.profile.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return True
        
        return False

class CanManageService(permissions.BasePermission):
    """
    Custom permission to check if user can manage services.
    """
    def has_object_permission(self, request, view, obj):
        # Providers can manage their own services
        if request.user.profile.role == UserRole.PROVIDER:
            return obj.provider == request.user.profile
        
        # Admins can manage all services
        if request.user.profile.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return True
        
        return False

class ReadOnlyOrOwnerWrite(permissions.BasePermission):
    """
    Custom permission to allow read-only access to anyone,
    but write access only to the owner.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for anyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for the owner
        return obj.user == request.user

class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow owners and admins to edit,
    but read-only for others.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for anyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions for owner
        if hasattr(obj, 'user') and obj.user == request.user:
            return True
        
        # Write permissions for admins
        if (hasattr(request.user, 'profile') and 
            request.user.profile.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]):
            return True
        
        return False
    
class IsProviderOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow read-only access to everyone, but only providers can modify.
    """
    
    def has_permission(self, request, view):
        # Read permissions for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Write permissions only for providers
        return (
            request.user.is_authenticated and
            request.user.role == 'provider'
        )
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Write permissions only for the provider owner
        return obj.user == request.user