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
    # =============================================================================
    
    # Package listing and detail views
    # GET /api/packages/ - List all published packages
    # GET /api/packages/{id}/ - Get package details (increments view count)
    path('api/', include(router.urls)),
    
    # Custom actions for public users
    # GET /api/packages/featured/ - Get featured packages
    path('api/packages/featured/', PackageViewSet.as_view({'get': 'featured'}), name='packages-featured'),
    
    # GET /api/packages/popular/ - Get popular packages (based on views and leads)
    path('api/packages/popular/', PackageViewSet.as_view({'get': 'popular'}), name='packages-popular'),
    
    # GET /api/packages/recent/ - Get recently added packages
    path('api/packages/recent/', PackageViewSet.as_view({'get': 'recent'}), name='packages-recent'),
    
    # GET /api/packages/{id}/availability/ - Get package availability calendar
    path('api/packages/<int:pk>/availability/', PackageViewSet.as_view({'get': 'availability'}), name='package-availability'),
    
    
    # =============================================================================
    # PROVIDER URLS - Accessible to authenticated service providers
    # =============================================================================
    
    # Package CRUD operations for providers
    # POST /api/provider/packages/ - Create new package (IsServiceProvider required)
    # PUT /api/provider/packages/{id}/ - Update package (IsProviderOrReadOnly required)
    # PATCH /api/provider/packages/{id}/ - Partial update package (IsProviderOrReadOnly required)
    # DELETE /api/provider/packages/{id}/ - Delete package (IsProviderOrReadOnly required)
    path('api/provider/', include(router.urls)),
    
    # Provider-specific actions
    # GET /api/provider/packages/stats/ - Get package statistics for logged-in provider
    path('api/provider/packages/stats/', PackageViewSet.as_view({'get': 'stats'}), name='provider-package-stats'),
    
    # POST /api/provider/packages/{id}/update-availability/ - Update package availability
    path('api/provider/packages/<int:pk>/update-availability/', 
         PackageViewSet.as_view({'post': 'update_availability'}), 
         name='provider-package-update-availability'),
    
    # Package image management for providers
    # GET /api/provider/packages/{package_id}/images/ - List package images
    # POST /api/provider/packages/{package_id}/images/ - Upload new image
    # PUT /api/provider/packages/{package_id}/images/{id}/ - Update image
    # DELETE /api/provider/packages/{package_id}/images/{id}/ - Delete image
    path('api/provider/', include(packages_router.urls)),
    
    
    # =============================================================================
    # ADMIN URLS - Accessible to admin users only
    # =============================================================================
    
    # Admin package management
    # GET /api/admin/packages/ - List all packages (all statuses)
    # GET /api/admin/packages/{id}/ - Get package details (admin view)
    path('api/admin/', include(admin_router.urls)),
    
    # Package approval workflow
    # GET /api/admin/packages/pending-approval/ - Get packages pending approval
    path('api/admin/packages/pending-approval/', 
         PackageAdminViewSet.as_view({'get': 'pending_approval'}), 
         name='admin-packages-pending'),
    
    # POST /api/admin/packages/{id}/approve/ - Approve a package
    path('api/admin/packages/<int:pk>/approve/', 
         PackageAdminViewSet.as_view({'post': 'approve'}), 
         name='admin-package-approve'),
    
    # POST /api/admin/packages/{id}/reject/ - Reject a package
    path('api/admin/packages/<int:pk>/reject/', 
         PackageAdminViewSet.as_view({'post': 'reject'}), 
         name='admin-package-reject'),
    
    # Package status management
    # POST /api/admin/packages/{id}/update-status/ - Update package status
    path('api/admin/packages/<int:pk>/update-status/', 
         PackageViewSet.as_view({'post': 'update_status'}), 
         name='admin-package-update-status'),
    
    # POST /api/admin/packages/{id}/toggle-featured/ - Toggle featured status
    path('api/admin/packages/<int:pk>/toggle-featured/', 
         PackageViewSet.as_view({'post': 'toggle_featured'}), 
         name='admin-package-toggle-featured'),
    
    # Analytics and reporting
    # GET /api/admin/packages/analytics/ - Get package analytics and statistics
    path('api/admin/packages/analytics/', 
         PackageAdminViewSet.as_view({'get': 'analytics'}), 
         name='admin-packages-analytics'),
]

# =============================================================================
# URL PATTERNS SUMMARY
# =============================================================================
"""
PUBLIC/USER ENDPOINTS:
- GET /api/packages/ - List published packages
- GET /api/packages/{id}/ - Package details
- GET /api/packages/featured/ - Featured packages
- GET /api/packages/popular/ - Popular packages
- GET /api/packages/recent/ - Recent packages
- GET /api/packages/{id}/availability/ - Package availability

PROVIDER ENDPOINTS:
- POST /api/provider/packages/ - Create package
- PUT/PATCH /api/provider/packages/{id}/ - Update package
- DELETE /api/provider/packages/{id}/ - Delete package
- GET /api/provider/packages/stats/ - Provider statistics
- POST /api/provider/packages/{id}/update-availability/ - Update availability
- GET/POST/PUT/DELETE /api/provider/packages/{id}/images/ - Image management

ADMIN ENDPOINTS:
- GET /api/admin/packages/ - All packages (admin view)
- GET /api/admin/packages/{id}/ - Package details (admin view)
- GET /api/admin/packages/pending-approval/ - Pending packages
- POST /api/admin/packages/{id}/approve/ - Approve package
- POST /api/admin/packages/{id}/reject/ - Reject package
- POST /api/admin/packages/{id}/update-status/ - Update status
- POST /api/admin/packages/{id}/toggle-featured/ - Toggle featured
- GET /api/admin/packages/analytics/ - Analytics dashboard
"""