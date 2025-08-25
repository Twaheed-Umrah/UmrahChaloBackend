from django.db.models import Q, F, Count, Avg
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from apps.core.permissions import IsOwnerOrReadOnly, IsProviderOrReadOnly
from apps.core.pagination import LargeResultsSetPagination
from apps.core.permissions import IsServiceProvider, IsSuperAdmin,IsActiveSubscription
from .models import Package, PackageImage, PackageAvailability
from .serializers import (
    PackageListSerializer, PackageDetailSerializer,
    PackageCreateUpdateSerializer, PackageStatusUpdateSerializer,
    PackageImageSerializer, PackageAvailabilitySerializer
)
from .filters import PackageFilter, PackageAdminFilter
from apps.notifications.services import NotificationService 

class PackageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing packages with role-based access control
    """
    queryset = Package.objects.select_related('provider').prefetch_related(
        'images', 'inclusions', 'exclusions', 'itineraries', 'policies'
    )
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PackageFilter
    search_fields = ['name', 'description', 'provider__business_name']
    ordering_fields = [
        'created_at', 'updated_at', 'name', 'base_price', 'start_date',
        'rating', 'views_count', 'leads_count', 'is_featured'
    ]
    ordering = ['-is_featured', '-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return PackageListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PackageCreateUpdateSerializer
        elif self.action == 'update_status':
            return PackageStatusUpdateSerializer
        else:
            return PackageDetailSerializer
    
    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ['create']:
            return [IsAuthenticated(), IsServiceProvider(),IsActiveSubscription()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(),IsActiveSubscription()]
        elif self.action == 'update_status':
            return [IsAuthenticated(), self.get_admin_permission()]
        else:
            return [permissions.AllowAny()]
    
    def get_admin_permission(self):
        """Helper method to check if user is admin or super admin"""
        user = self.request.user
        if hasattr(user, 'user_type'):
            return user.user_type in ['admin', 'super_admin']
        return user.is_staff or user.is_superuser
    
    def get_user_role(self):
        """Get the user role from user_type field or fallback to staff status"""
        if not self.request.user.is_authenticated:
            return 'anonymous'
        
        user = self.request.user
        if hasattr(user, 'user_type'):
            return user.user_type
        
        # Fallback for existing systems
        if user.is_superuser:
            return 'super_admin'
        elif user.is_staff:
            return 'admin'
        elif hasattr(user, 'service_provider_profile'):
            return 'provider'
        else:
            return 'pilgrim'
    
    def get_queryset(self):
        """Filter queryset based on user role"""
        queryset = super().get_queryset()
        user_role = self.get_user_role()
        # Anonymous users - only published and active packages
        if user_role == 'anonymous':
            return queryset.filter(
                status='published',
                is_active=True
            )
        
        # PROVIDER role - show packages with any status if they own it
        # For listing: show published packages + own packages (any status)
        # For CUD operations: only own packages
        if user_role == 'provider':
            # Check if user has a service_provider profile
            if not hasattr(self.request.user, 'service_provider_profile'):
                # If no service provider profile, treat as regular user
                return queryset.filter(
                    status='published',
                    is_active=True
                )
            
            provider_profile = self.request.user.service_provider_profile
            if self.action in ['list', 'retrieve']:
                # Show published packages + own packages (any status)
                return queryset.filter(
                    Q(status='published', is_active=True) |
                    Q(provider=provider_profile)
                )
            else:
                # For CUD operations, only own packages
                return queryset.filter(
                    provider=provider_profile
                )
        
        # PILGRIM role - only verified and published packages
        if user_role == 'pilgrim':
            return queryset.filter(
                status__in=['verified', 'published'],
                is_active=True
            )
        
        # ADMIN and SUPER_ADMIN roles - show all packages with all statuses
        if user_role in ['admin', 'super_admin']:
            return queryset
        
        # Default fallback - published packages only
        return queryset.filter(status='published', is_active=True)
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve package and increment view count"""
        instance = self.get_object()
        
        # Increment view count
        Package.objects.filter(id=instance.id).update(
            views_count=F('views_count') + 1
        )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    @action(detail=False, methods=['get'], url_path='get-package-by-id')
    def get_by_id(self, request):
        """Custom endpoint to get package by ID (using query params and role-based filtering)"""
        package_id = request.query_params.get('id')

        if not package_id:
            return Response({"error": "ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get the queryset with role-based filtering
            package = self.get_queryset().get(id=package_id)

            # Use detail serializer
            serializer = PackageDetailSerializer(package)
            return Response(serializer.data)

        except Package.DoesNotExist:
            return Response({"error": "Package not found"}, status=status.HTTP_404_NOT_FOUND)
  
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update package status (admin and super_admin only)"""
        user_role = self.get_user_role()
        
        # Only admin and super_admin can update status
        if user_role not in ['admin', 'super_admin']:
            return Response(
                {'error': 'Permission denied. Only admins can update package status.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        package = self.get_object()
        
        # Get the old status before update
        old_status = package.status
        
        serializer = self.get_serializer(package, data=request.data)
        
        if serializer.is_valid():
            # Get the new status from validated data
            new_status = serializer.validated_data.get('status')
            
            # Update verification fields if status is being changed to verified/published
            if new_status in ['verified', 'published'] and package.status != new_status:
                serializer.save(
                    verified_by=request.user,
                    verified_at=timezone.now()
                )
            else:
                serializer.save()
            
            # Send notifications based on status change
            try:
                if old_status != new_status:
                    if new_status in ['approved', 'verified', 'published']:
                        # Send approval notification
                        NotificationService.create_notification(
                            recipient=package.provider.user,
                            notification_type='package_approved',
                            title="Package Approved!",
                            message=f"Your package '{package.name}' has been approved and is now live on Umrah Chalo.",
                            data={
                                'package_name': package.name,
                                'package_id': package.id,
                                'provider_name': getattr(package.provider, 'business_name', package.provider.user.full_name),
                                'approval_date': timezone.now().strftime('%Y-%m-%d'),
                                'package_duration': f"{package.duration_days} days" if hasattr(package, 'duration_days') else 'N/A',
                                'package_price': f"₹{package.base_price}" if package.base_price else 'Contact for pricing',
                                'package_url': f"{getattr(settings, 'FRONTEND_URL', '')}/packages/{package.id}/",
                                'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/dashboard/",
                                'verified_by': request.user.full_name or request.user.email,
                            },
                            related_object=package,
                            priority='high'
                        )
                        
                    elif new_status == 'rejected':
                        # Send rejection notification
                        rejection_reason = request.data.get('rejection_reason', 'Please review and improve your package details.')
                        
                        NotificationService.create_notification(
                            recipient=package.provider.user,
                            notification_type='package_rejected',
                            title="Package Needs Attention",
                            message=f"Your package '{package.name}' requires some improvements before it can be approved.",
                            data={
                                'package_name': package.name,
                                'package_id': package.id,
                                'provider_name': getattr(package.provider, 'business_name', package.provider.user.full_name),
                                'rejection_reason': rejection_reason,
                                'rejection_date': timezone.now().strftime('%Y-%m-%d'),
                                'edit_package_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/packages/{package.id}/edit/",
                                'dashboard_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/dashboard/",
                                'support_url': f"{getattr(settings, 'FRONTEND_URL', '')}/support/",
                                'resubmit_guidelines_url': f"{getattr(settings, 'FRONTEND_URL', '')}/provider/guidelines/",
                            },
                            related_object=package,
                            priority='high'
                        )
                        
            except Exception as notification_error:
                # Log the error but don't fail the status update
                logger.error(f"Failed to send package status notification: {notification_error}")
            
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def toggle_featured(self, request, pk=None):
        """Toggle featured status (admin and super_admin only)"""
        user_role = self.get_user_role()
        
        if user_role not in ['admin', 'super_admin']:
            return Response(
                {'error': 'Permission denied. Only admins can toggle featured status.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        package = self.get_object()
        package.is_featured = not package.is_featured
        package.save()
        
        return Response({
            'is_featured': package.is_featured,
            'message': f'Package {"featured" if package.is_featured else "unfeatured"} successfully'
        })
    
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Get package availability calendar"""
        package = self.get_object()
        availabilities = package.availabilities.all()
        serializer = PackageAvailabilitySerializer(availabilities, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def update_availability(self, request, pk=None):
        """Update package availability (provider only for their own packages)"""
        package = self.get_object()
        user_role = self.get_user_role()
        
        # Check if user is the package owner (for providers)
        if user_role == 'provider':
            if (not hasattr(request.user, 'service_provider_profile') or 
                package.provider != request.user.service_provider_profile):
                return Response(
                    {'error': 'Permission denied. You can only update availability for your own packages.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif user_role not in ['admin', 'super_admin']:
            return Response(
                {'error': 'Permission denied.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        availabilities_data = request.data.get('availabilities', [])
        
        # Clear existing availabilities
        package.availabilities.all().delete()
        
        # Create new availabilities
        for availability_data in availabilities_data:
            availability_data['package'] = package.id
            serializer = PackageAvailabilitySerializer(data=availability_data)
            if serializer.is_valid():
                serializer.save()
        
        return Response({'message': 'Availability updated successfully'})
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured packages - filtered based on user role"""
        user_role = self.get_user_role()
        
        if user_role == 'pilgrim':
            # Pilgrims see only verified and published featured packages
            featured_packages = self.get_queryset().filter(
                is_featured=True,
                status__in=['verified', 'published'],
                is_active=True
            )[:10]
        elif user_role in ['admin', 'super_admin']:
            # Admins see all featured packages
            featured_packages = Package.objects.filter(is_featured=True)[:10]
        else:
            # Others see published featured packages
            featured_packages = self.get_queryset().filter(
                is_featured=True,
                status='published',
                is_active=True
            )[:10]
        
        serializer = PackageListSerializer(featured_packages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Get popular packages based on views and leads - filtered by user role"""
        user_role = self.get_user_role()
        
        if user_role == 'pilgrim':
            # Pilgrims see only verified and published packages
            popular_packages = self.get_queryset().filter(
                status__in=['verified', 'published'],
                is_active=True
            ).annotate(
                popularity_score=F('views_count') + F('leads_count') * 2
            ).order_by('-popularity_score')[:10]
        elif user_role in ['admin', 'super_admin']:
            # Admins see all packages
            popular_packages = Package.objects.annotate(
                popularity_score=F('views_count') + F('leads_count') * 2
            ).order_by('-popularity_score')[:10]
        else:
            # Others see published packages
            popular_packages = self.get_queryset().filter(
                status='published',
                is_active=True
            ).annotate(
                popularity_score=F('views_count') + F('leads_count') * 2
            ).order_by('-popularity_score')[:10]
        
        serializer = PackageListSerializer(popular_packages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recently added packages - filtered by user role"""
        user_role = self.get_user_role()
        
        if user_role == 'pilgrim':
            # Pilgrims see only verified and published packages
            recent_packages = self.get_queryset().filter(
                status__in=['verified', 'published'],
                is_active=True
            ).order_by('-created_at')[:10]
        elif user_role in ['admin', 'super_admin']:
            # Admins see all packages
            recent_packages = Package.objects.order_by('-created_at')[:10]
        else:
            # Others see published packages
            recent_packages = self.get_queryset().filter(
                status='published',
                is_active=True
            ).order_by('-created_at')[:10]
        
        serializer = PackageListSerializer(recent_packages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get package statistics (provider only)"""
        user_role = self.get_user_role()
        
        if user_role != 'provider':
            return Response(
                {'error': 'Permission denied. Only service providers can access package statistics.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not hasattr(request.user, 'service_provider_profile'):
            return Response(
                {'error': 'Service provider profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        provider_profile = request.user.service_provider_profile
        packages = Package.objects.filter(provider=provider_profile)
        
        stats = {
            'total_packages': packages.count(),
            'published_packages': packages.filter(status='published').count(),
            'verified_packages': packages.filter(status='verified').count(),
            'pending_packages': packages.filter(status='pending').count(),
            'rejected_packages': packages.filter(status='rejected').count(),
            'total_views': packages.aggregate(total=Count('views_count'))['total'] or 0,
            'total_leads': packages.aggregate(total=Count('leads_count'))['total'] or 0,
            'average_rating': packages.aggregate(avg=Avg('rating'))['avg'] or 0,
            'featured_packages': packages.filter(is_featured=True).count(),
        }
        
        return Response(stats)
class PublicPackageDetailView(APIView):
    """
    Public API to fetch a package by ID
    Accessible by anyone (login or not)
    """
    permission_classes = [AllowAny]  # 👈 Allow access without authentication

    def get(self, request, *args, **kwargs):
        package_id = request.query_params.get("id")

        if not package_id:
            return Response(
                {"error": "Package ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            package = Package.objects.get(id=package_id)  # 👈 no role-based filter
            serializer = PackageDetailSerializer(package)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Package.DoesNotExist:
            return Response(
                {"error": "Package not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {"error": "Invalid package ID format"},
                status=status.HTTP_400_BAD_REQUEST
            )

class PackageImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing package images
    """
    serializer_class = PackageImageSerializer
    permission_classes = [IsAuthenticated, IsProviderOrReadOnly]
    
    def get_queryset(self):
        """Filter images by package"""
        package_id = self.kwargs.get('package_pk')
        return PackageImage.objects.filter(package_id=package_id)
    
    def perform_create(self, serializer):
        """Create image for specific package"""
        package_id = self.kwargs.get('package_pk')
        package = get_object_or_404(Package, id=package_id)
        
        # Check if user owns the package or is admin
        user_role = self.get_user_role()
        
        if user_role == 'provider':
            if (not hasattr(self.request.user, 'service_provider_profile') or 
                package.provider != self.request.user.service_provider_profile):
                raise permissions.PermissionDenied("You don't own this package")
        elif user_role not in ['admin', 'super_admin']:
            raise permissions.PermissionDenied("Permission denied")
        
        serializer.save(package=package)
    
    def get_user_role(self):
        """Get the user role from user_type field or fallback to staff status"""
        if not self.request.user.is_authenticated:
            return 'anonymous'
        
        user = self.request.user
        if hasattr(user, 'user_type'):
            return user.user_type
        
        # Fallback for existing systems
        if user.is_superuser:
            return 'super_admin'
        elif user.is_staff:
            return 'admin'
        elif hasattr(user, 'service_provider_profile'):
            return 'provider'
        else:
            return 'pilgrim'


class PackageAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin viewset for package management (admin and super_admin only)
    """
    queryset = Package.objects.select_related('provider', 'verified_by')
    serializer_class = PackageDetailSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PackageAdminFilter
    search_fields = ['name', 'description', 'provider__business_name']
    ordering_fields = [
        'created_at', 'updated_at', 'name', 'status', 'verified_at',
        'views_count', 'leads_count', 'rating'
    ]
    ordering = ['-created_at']
    
    def get_user_role(self):
        """Get the user role"""
        if not self.request.user.is_authenticated:
            return 'anonymous'
        
        user = self.request.user
        if hasattr(user, 'user_type'):
            return user.user_type
        
        # Fallback for existing systems
        if user.is_superuser:
            return 'super_admin'
        elif user.is_staff:
            return 'admin'
        else:
            return 'other'
    
    def check_permissions(self, request):
        """Override to add custom permission check"""
        super().check_permissions(request)
        
        # Check admin privileges
        user_role = self.get_user_role()
        if user_role not in ['admin', 'super_admin']:
            raise PermissionDenied('Permission denied. Admin access required.')
    
    @action(detail=False, methods=['get'])
    def pending_approval(self, request):
        """Get packages pending approval"""
        pending_packages = self.get_queryset().filter(status='pending')
        
        page = self.paginate_queryset(pending_packages)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(pending_packages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Get package analytics"""
        queryset = self.get_queryset()
        
        # Status distribution
        status_stats = {}
        for choice in Package.STATUS_CHOICES:
            status_stats[choice[0]] = queryset.filter(status=choice[0]).count()
        
        # Package type distribution
        type_stats = {}
        for choice in Package.PACKAGE_TYPES:
            type_stats[choice[0]] = queryset.filter(package_type=choice[0]).count()
        
        # Top performing packages
        top_packages = queryset.filter(
            status='published'
        ).order_by('-views_count')[:5]
        
        # Recent activity
        recent_activity = queryset.order_by('-updated_at')[:10]
        
        analytics = {
            'total_packages': queryset.count(),
            'status_distribution': status_stats,
            'type_distribution': type_stats,
            'top_packages': PackageListSerializer(top_packages, many=True).data,
            'recent_activity': PackageListSerializer(recent_activity, many=True).data,
            'average_rating': queryset.aggregate(avg=Avg('rating'))['avg'] or 0,
            'total_views': queryset.aggregate(total=Count('views_count'))['total'] or 0,
            'total_leads': queryset.aggregate(total=Count('leads_count'))['total'] or 0,
        }
        
        return Response(analytics)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a package (set status to verified)"""
        package = self.get_object()
        
        if package.status != 'pending':
            return Response(
                {'error': 'Package is not pending approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        package.status = 'published'  # Changed from 'published' to 'verified'
        package.verified_by = request.user
        package.verified_at = timezone.now()
        package.save()
        
        return Response({
            'message': 'Package approved successfully',
            'status': package.status
        })
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a package"""
        package = self.get_object()
        rejection_reason = request.data.get('rejection_reason')
        
        if not rejection_reason:
            return Response(
                {'error': 'Rejection reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        package.status = 'rejected'
        package.rejection_reason = rejection_reason
        package.verified_by = request.user
        package.verified_at = timezone.now()
        package.save()
        
        return Response({
            'message': 'Package rejected successfully',
            'status': package.status,
            'rejection_reason': rejection_reason
        })
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a verified package"""
        package = self.get_object()
        
        if package.status != 'verified':
            return Response(
                {'error': 'Package must be verified before publishing'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        package.status = 'published'
        package.save()
        
        return Response({
            'message': 'Package published successfully',
            'status': package.status
        })