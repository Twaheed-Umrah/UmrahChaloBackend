from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from .views import PackageViewSet, PackageImageViewSet, PackageAdminViewSet

app_name = 'packages'

# Create main router
router = DefaultRouter()

# Register main package viewset
router.register(r'packages', PackageViewSet, basename='package')

# Create nested router for package images
packages_router = routers.NestedDefaultRouter(router, r'packages', lookup='package')
packages_router.register(r'images', PackageImageViewSet, basename='package-images')

# Admin router
admin_router = DefaultRouter()
admin_router.register(r'packages', PackageAdminViewSet, basename='admin-package')

urlpatterns = [
    # =============================================================================
    # PUBLIC/USER URLS - Accessible to all users (authenticated and unauthenticated)
    # Role-based filtering applied in viewset get_queryset()
    # =============================================================================
    
    # Package listing and detail views
    # GET /package/packages/ - List packages (filtered by user role)
    # GET /package/packages/{id}/ - Get package details (increments view count)
    path('package/', include(router.urls)),
    
    # Custom actions for public users (role-based filtering applied)
    # GET /package/packages/featured/ - Get featured packages
    path('package/packages/featured/', PackageViewSet.as_view({'get': 'featured'}), name='packages-featured'),
    
    # GET /package/packages/popular/ - Get popular packages (based on views and leads)
    path('package/packages/popular/', PackageViewSet.as_view({'get': 'popular'}), name='packages-popular'),
    
    # GET /package/packages/recent/ - Get recently added packages
    path('package/packages/recent/', PackageViewSet.as_view({'get': 'recent'}), name='packages-recent'),
    
    # GET /package/packages/{id}/availability/ - Get package availability calendar
    path('package/packages/<int:pk>/availability/', PackageViewSet.as_view({'get': 'availability'}), name='package-availability'),
    
    
    # =============================================================================
    # PROVIDER URLS - Accessible to authenticated service providers
    # Same endpoints as public but with provider permissions for CUD operations
    # =============================================================================
    
    # Package CRUD operations for providers (same URLs, different permissions)
    # The viewset handles role-based access automatically
    # POST /package/packages/ - Create new package (PROVIDER role required)
    # PUT /package/packages/{id}/ - Update package (PROVIDER role + ownership required)
    # PATCH /package/packages/{id}/ - Partial update package (PROVIDER role + ownership required)
    # DELETE /package/packages/{id}/ - Delete package (PROVIDER role + ownership required)
    
    # Provider-specific actions
    # GET /package/packages/stats/ - Get package statistics for logged-in provider
    path('package/packages/stats/', PackageViewSet.as_view({'get': 'stats'}), name='provider-package-stats'),
    
    # POST /package/packages/{id}/update-availability/ - Update package availability
    path('package/packages/<int:pk>/update-availability/', 
         PackageViewSet.as_view({'post': 'update_availability'}), 
         name='provider-package-update-availability'),
    
    # Package image management for providers
    # GET /package/packages/{package_id}/images/ - List package images
    # POST /package/packages/{package_id}/images/ - Upload new image
    # PUT /package/packages/{package_id}/images/{id}/ - Update image
    # DELETE /package/packages/{package_id}/images/{id}/ - Delete image
    path('package/', include(packages_router.urls)),
    
    
    # =============================================================================
    # ADMIN URLS - Accessible to admin and super_admin users only
    # =============================================================================
    
    # Admin package management
    # GET /package/admin/packages/ - List all packages (all statuses)
    # GET /package/admin/packages/{id}/ - Get package details (admin view)
    path('package/admin/', include(admin_router.urls)),
    
    # Package approval workflow
    # GET /package/admin/packages/pending-approval/ - Get packages pending approval
    path('package/admin/packages/pending-approval/', 
         PackageAdminViewSet.as_view({'get': 'pending_approval'}), 
         name='admin-packages-pending'),
    
    # POST /package/admin/packages/{id}/approve/ - Approve a package (set to verified)
    path('package/admin/packages/<int:pk>/approve/', 
         PackageAdminViewSet.as_view({'post': 'approve'}), 
         name='admin-package-approve'),
    
    # POST /package/admin/packages/{id}/reject/ - Reject a package
    path('package/admin/packages/<int:pk>/reject/', 
         PackageAdminViewSet.as_view({'post': 'reject'}), 
         name='admin-package-reject'),
    
    # NEW: Publish a verified package
    # POST /package/admin/packages/{id}/publish/ - Publish a verified package
    path('package/admin/packages/<int:pk>/publish/', 
         PackageAdminViewSet.as_view({'post': 'publish'}), 
         name='admin-package-publish'),
    
    # Package status management
    # POST /package/admin/packages/{id}/update-status/ - Update package status (any status)
    path('package/admin/packages/<int:pk>/update-status/', 
         PackageViewSet.as_view({'post': 'update_status'}), 
         name='admin-package-update-status'),
    
    # POST /package/admin/packages/{id}/toggle-featured/ - Toggle featured status
    path('package/admin/packages/<int:pk>/toggle-featured/', 
         PackageViewSet.as_view({'post': 'toggle_featured'}), 
         name='admin-package-toggle-featured'),
    
    # Analytics and reporting
    # GET /package/admin/packages/analytics/ - Get package analytics and statistics
    path('package/admin/packages/analytics/', 
         PackageAdminViewSet.as_view({'get': 'analytics'}), 
         name='admin-packages-analytics'),
]

# =============================================================================
# URL PATTERNS SUMMARY WITH ROLE-BASED ACCESS
# =============================================================================
"""
PUBLIC/USER ENDPOINTS (Role-based filtering applied automatically):
- GET /package/packages/ - List packages
  * Anonymous: Published + Active packages only
  * PILGRIM: Verified + Published + Active packages only  
  * PROVIDER: Published + Active packages + Own packages (any status)
  * ADMIN/SUPER_ADMIN: All packages (any status)

- GET /package/packages/{id}/ - Package details
  * Same role-based filtering as above

- GET /package/packages/featured/ - Featured packages
  * Filtered based on user role

- GET /package/packages/popular/ - Popular packages  
  * Filtered based on user role

- GET /package/packages/recent/ - Recent packages
  * Filtered based on user role

- GET /package/packages/{id}/availability/ - Package availability
  * Available for all visible packages

PROVIDER ENDPOINTS (Same URLs as public, different permissions):
- POST /package/packages/ - Create package (PROVIDER role required)
- PUT/PATCH /package/packages/{id}/ - Update package (PROVIDER + ownership required)
- DELETE /package/packages/{id}/ - Delete package (PROVIDER + ownership required)
- GET /package/packages/stats/ - Provider statistics (PROVIDER role required)
- POST /package/packages/{id}/update-availability/ - Update availability (PROVIDER + ownership)
- GET/POST/PUT/DELETE /package/packages/{id}/images/ - Image management (PROVIDER + ownership)

ADMIN ENDPOINTS (ADMIN/SUPER_ADMIN roles only):
- GET /package/admin/packages/ - All packages (admin view)
- GET /package/admin/packages/{id}/ - Package details (admin view)
- GET /package/admin/packages/pending-approval/ - Pending packages
- POST /package/admin/packages/{id}/approve/ - Approve package (pending → verified)
- POST /package/admin/packages/{id}/reject/ - Reject package
- POST /package/admin/packages/{id}/publish/ - Publish package (verified → published)
- POST /package/admin/packages/{id}/update-status/ - Update status (any status change)
- POST /package/admin/packages/{id}/toggle-featured/ - Toggle featured
- GET /package/admin/packages/analytics/ - Analytics dashboard

ROLE-BASED ACCESS SUMMARY:
- ANONYMOUS: Published + Active packages only
- PILGRIM: Verified + Published + Active packages only
- PROVIDER: All published + own packages (any status) + full CRUD on owned packages
- ADMIN/SUPER_ADMIN: Full access to all packages + status management
"""