from django.db.models import Q, F, Count, Avg
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.core.permissions import IsOwnerOrReadOnly, IsProviderOrReadOnly
from apps.core.pagination import LargeResultsSetPagination
from apps.core.permissions import IsServiceProvider, IsAdmin
from .models import Package, PackageImage, PackageAvailability
from .serializers import (
    PackageListSerializer, PackageDetailSerializer,
    PackageCreateUpdateSerializer, PackageStatusUpdateSerializer,
    PackageImageSerializer, PackageAvailabilitySerializer
)
from .filters import PackageFilter, PackageAdminFilter


class PackageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing packages
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
        'rating', 'views_count', 'leads_count'
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
            return [IsAuthenticated(), IsServiceProvider()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsProviderOrReadOnly()]
        elif self.action == 'update_status':
            return [IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.AllowAny()]
    
    def get_queryset(self):
        """Filter queryset based on user role"""
        queryset = super().get_queryset()
        
        # For regular users, only show published and active packages
        if not self.request.user.is_authenticated:
            return queryset.filter(
                status='published',
                is_active=True
            )
        
        # For service providers, show their own packages
        if (hasattr(self.request.user, 'service_provider') and 
            not self.request.user.is_staff):
            if self.action in ['list', 'retrieve']:
                # Show published packages + own packages
                return queryset.filter(
                    Q(status='published', is_active=True) |
                    Q(provider=self.request.user.service_provider)
                )
            else:
                # For CUD operations, only own packages
                return queryset.filter(
                    provider=self.request.user.service_provider
                )
        
        # For admin users, show all packages
        if self.request.user.is_staff:
            return queryset
        
        # Default: published packages only
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
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update package status (admin only)"""
        package = self.get_object()
        serializer = self.get_serializer(package, data=request.data)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def toggle_featured(self, request, pk=None):
        """Toggle featured status (admin only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
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
        """Update package availability"""
        package = self.get_object()
        
        # Check if user is the package owner
        if (not hasattr(request.user, 'service_provider') or 
            package.provider != request.user.service_provider):
            return Response(
                {'error': 'Permission denied'},
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
        """Get featured packages"""
        featured_packages = self.get_queryset().filter(
            is_featured=True,
            status='published',
            is_active=True
        )[:10]
        
        serializer = PackageListSerializer(featured_packages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Get popular packages based on views and leads"""
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
        """Get recently added packages"""
        recent_packages = self.get_queryset().filter(
            status='published',
            is_active=True
        ).order_by('-created_at')[:10]
        
        serializer = PackageListSerializer(recent_packages, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get package statistics (provider only)"""
        if not hasattr(request.user, 'service_provider'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        provider = request.user.service_provider
        packages = Package.objects.filter(provider=provider)
        
        stats = {
            'total_packages': packages.count(),
            'published_packages': packages.filter(status='published').count(),
            'pending_packages': packages.filter(status='pending').count(),
            'rejected_packages': packages.filter(status='rejected').count(),
            'total_views': packages.aggregate(total=Count('views_count'))['total'] or 0,
            'total_leads': packages.aggregate(total=Count('leads_count'))['total'] or 0,
            'average_rating': packages.aggregate(avg=Avg('rating'))['avg'] or 0,
            'featured_packages': packages.filter(is_featured=True).count(),
        }
        
        return Response(stats)


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
        
        # Check if user owns the package
        if package.provider != self.request.user.service_provider:
            raise permissions.PermissionDenied("You don't own this package")
        
        serializer.save(package=package)


class PackageAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin viewset for package management
    """
    queryset = Package.objects.select_related('provider', 'verified_by')
    serializer_class = PackageDetailSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PackageAdminFilter
    search_fields = ['name', 'description', 'provider__business_name']
    ordering_fields = [
        'created_at', 'updated_at', 'name', 'status', 'verified_at',
        'views_count', 'leads_count', 'rating'
    ]
    ordering = ['-created_at']
    
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
        """Approve a package"""
        package = self.get_object()
        
        if package.status != 'pending':
            return Response(
                {'error': 'Package is not pending approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        package.status = 'published'
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