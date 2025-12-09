from venv import logger
from rest_framework.views import APIView
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from datetime import timedelta
import re
from django.core.exceptions import ValidationError, PermissionDenied
from apps.notifications.services import NotificationService

from .models import (
    ServiceCategory, ServiceImage, Service, ServiceAvailability, 
    ServiceFAQ, ServiceView, ServiceType, ServiceStatus
)
from .serializers import (
    ServiceCategorySerializer, ServiceImageSerializer, ServiceListSerializer,
    ServiceDetailSerializer, ServiceCreateUpdateSerializer, ServiceStatusUpdateSerializer,
    ServiceAvailabilitySerializer, ServiceFAQSerializer, ServiceViewSerializer,
    ServiceStatsSerializer, ServiceSearchSerializer, AirTicketServiceSerializer,
    ZamzamWaterServiceSerializer, HotelServiceSerializer, TransportServiceSerializer
)
from .filters import ServiceFilter
from apps.core.permissions import (
    IsOwnerOrReadOnly, IsServiceProvider, IsAdmin, IsSuperAdmin,
    IsAdminOrSuperAdmin, IsProviderOrAdmin, IsVerifiedProvider,
    IsActiveSubscription, CanManageService
)
from apps.authentication.models import ServiceProviderProfile
from apps.core.pagination import LargeResultsSetPagination
from apps.core.utils import get_client_ip


class ServiceCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Service Categories (Read-only for all users, auth or anonymous)
    Provides CRUD operations for service categories with filtering capabilities.
    """
    queryset = ServiceCategory.objects.filter(is_active=True)
    serializer_class = ServiceCategorySerializer
    permission_classes = [AllowAny]
    filter_backends = [OrderingFilter, SearchFilter]
    ordering_fields = ['name', 'display_order', 'created_at']
    ordering = ['display_order', 'name']
    search_fields = ['name', 'description']
    
    def get_queryset(self):
        """
        Optimize queryset with prefetch_related and exclude specific categories
        """
        qs = self.queryset.prefetch_related('services', 'images')
        
        # Exclude Hajj Package and Umrah Package by name
        excluded_categories = ["Hajj Package", "Umrah Package"]
        qs = qs.exclude(name__in=excluded_categories)
        
        # Filter by service type if provided
        service_type = self.request.query_params.get('service_type')
        if service_type:
            qs = qs.filter(services__service_type=service_type).distinct()
            
        return qs
        
    @action(detail=True, methods=['get'])
    def services(self, request, pk=None):
        """
        Get all published services for a specific category with filtering and pagination
        """
        category = self.get_object()
        services = Service.objects.filter(
            category=category,
            status=ServiceStatus.PUBLISHED
        ).select_related(
            'provider', 'provider__user', 'category', 'featured_image'
        ).prefetch_related('images')
        
        # Apply filters using ServiceFilter
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        
        # Apply additional filtering based on query parameters
        search_query = request.GET.get('q')
        if search_query:
            filtered_services = filtered_services.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(short_description__icontains=search_query)
            )
        
        # Pagination
        paginator = LargeResultsSetPagination()
        page = paginator.paginate_queryset(filtered_services, request)
        
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """
        Get categories with most services
        """
        categories = self.get_queryset().annotate(
            published_services_count=Count(
                'services', 
                filter=Q(services__status=ServiceStatus.PUBLISHED)
            )
        ).filter(published_services_count__gt=0).order_by('-published_services_count')[:10]
        
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)


class ServiceImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Service Images:
    - SuperAdmin/Admin can upload and manage images
    - Providers can view available images for their services
    - Supports base64 image uploads
    """
    queryset = ServiceImage.objects.filter(is_active=True)
    serializer_class = ServiceImageSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'alt_text']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']
    pagination_class = LargeResultsSetPagination

    def get_queryset(self):
        """
        Optimize queryset with category selection
        """
        return self.queryset.select_related('category')

    def get_permissions(self):
        """
        Dynamic permissions based on action
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """
        Get images grouped by category
        """
        category_id = request.GET.get('category_id')
        if category_id:
            images = self.get_queryset().filter(category_id=category_id)
        else:
            images = self.get_queryset()
        
        # Group images by category
        from collections import defaultdict
        grouped_images = defaultdict(list)
        
        for image in images:
            grouped_images[image.category.name].append(
                ServiceImageSerializer(image, context={'request': request}).data
            )
        
        return Response(dict(grouped_images))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def service_type_choices(request):
    """
    Get available service type choices for forms
    """
    choices = [
        {
            'value': choice.value, 
            'label': choice.label,
            'description': f"Services related to {choice.label.lower()}"
        } 
        for choice in ServiceType
    ]
    return Response({
        'choices': choices,
        'count': len(choices)
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def service_status_choices(request):
    """
    Get available service status choices
    """
    choices = [
        {
            'value': choice.value, 
            'label': choice.label
        } 
        for choice in ServiceStatus
    ]
    return Response({
        'choices': choices,
        'count': len(choices)
    })


class ServiceViewSet(viewsets.ModelViewSet):
    """
    Comprehensive ViewSet for Services with role-based access control,
    conditional field support, and advanced filtering capabilities.
    """
    queryset = Service.objects.all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ServiceFilter
    search_fields = [
        'title', 'description', 'short_description', 'city', 'state',
        'provider__business_name', 'provider__user__first_name', 
        'provider__user__last_name'
    ]
    ordering_fields = [
        'price', 'created_at', 'views_count', 'title', 'is_featured',
        'departure_date', 'hotel_star_rating', 'water_capacity_liters'
    ]
    ordering = ['-is_featured', '-created_at']
    pagination_class = LargeResultsSetPagination

    def get_user_role(self):
        """
        Determine user role for permission handling
        """
        user = self.request.user
        if not user.is_authenticated:
            return 'anonymous'
        
        if hasattr(user, 'user_type'):
            return user.user_type
        
        if user.is_superuser:
            return 'super_admin'
        elif user.is_staff:
            return 'admin'
        elif hasattr(user, 'service_provider_profile'):
            return 'provider'
        return 'pilgrim'

    def get_queryset(self):
        """
        Filter queryset based on user role and permissions
        """
        user = self.request.user
        role = self.get_user_role()
        
        # Optimize base queryset with select_related and prefetch_related
        base_queryset = self.queryset.select_related(
            'provider', 'provider__user', 'category', 'featured_image', 'verified_by'
        ).prefetch_related('images', 'availabilities', 'faqs')

        if role in ['admin', 'super_admin']:
            # Admins can see all services
            return base_queryset
        elif role == 'provider':
            # Providers can only see their own services
            if hasattr(user, 'service_provider_profile'):
                return base_queryset.filter(provider=user.service_provider_profile)
            return Service.objects.none()
        else:
            # Anonymous users and pilgrims can only see published services
            return base_queryset.filter(status=ServiceStatus.PUBLISHED)

    def get_serializer_class(self):
        """
        Return appropriate serializer based on action and service type
        """
        if self.action == 'list':
            return ServiceListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ServiceCreateUpdateSerializer
        elif self.action == 'update_status':
            return ServiceStatusUpdateSerializer
        elif self.action == 'retrieve':
            # Use specialized serializers based on service type
            service_id = self.kwargs.get('pk')
            if service_id:
                try:
                    service = self.get_queryset().get(pk=service_id)
                    service_type = service.service_type
                    
                    serializer_map = {
                        ServiceType.AIR_TICKET: AirTicketServiceSerializer,
                        ServiceType.JAM_JAM_WATER: ZamzamWaterServiceSerializer,
                        ServiceType.HOTEL: HotelServiceSerializer,
                        ServiceType.TRANSPORT: TransportServiceSerializer,
                    }
                    
                    return serializer_map.get(service_type, ServiceDetailSerializer)
                except Service.DoesNotExist:
                    pass
            
            return ServiceDetailSerializer
        
        return ServiceDetailSerializer

    def get_permissions(self):
        """
        Dynamic permissions based on action
        """
        if self.action == 'list':
            permission_classes = [AllowAny]
        elif self.action == 'retrieve':
            permission_classes = [AllowAny]
        elif self.action == 'create':
            permission_classes = [IsAuthenticated, IsActiveSubscription, IsVerifiedProvider, IsServiceProvider]
        elif self.action in ['partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsActiveSubscription]
        elif self.action == 'update_status':
            permission_classes = [IsSuperAdmin]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]

    def check_service_permissions(self, user, data=None):
        """
        Check if user has permission to create/update services
        This validates both subscription and business type restrictions
        """
        try:
            provider_profile = user.service_provider_profile
        except ServiceProviderProfile.DoesNotExist:
            raise ValidationError("Only registered service providers can manage services.")
        
        # The IsActiveSubscription permission already checks for active subscription
        # So we don't need to check it again here
        
        # Check service type permission
        service_type = data.get('service_type') if data else None
        if service_type:
            has_permission, error_message = provider_profile.check_service_upload_permission(service_type)
            if not has_permission:
                raise ValidationError(error_message)
        
        # Check upload limits
        has_limit, error_message = provider_profile.check_upload_limits('service')
        if not has_limit:
            raise ValidationError(error_message)
        
        return provider_profile

    def perform_create(self, serializer):
        """
        Create service with proper provider assignment and validation
        """
        user = self.request.user
        
        # Check service permissions (includes subscription check via permission class)
        provider_profile = self.check_service_permissions(user, self.request.data)
        
        serializer.save(provider=provider_profile)

    def perform_update(self, serializer):
        """
        Update service with proper validation
        """
        user = self.request.user
        
        # Check service permissions (includes subscription check via permission class)
        provider_profile = self.check_service_permissions(user, self.request.data)
        
        # Ensure the service belongs to the provider
        if serializer.instance.provider != provider_profile:
            raise ValidationError("You can only update your own services.")
        
        serializer.save()

    def perform_destroy(self, instance):
        """
        Delete service with validation
        """
        user = self.request.user
        
        # Check service permissions (includes subscription check via permission class)
        provider_profile = self.check_service_permissions(user)
        
        # Ensure the service belongs to the provider
        if instance.provider != provider_profile:
            raise ValidationError("You can only delete your own services.")
        
        instance.delete()

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve single service with view tracking
        """
        instance = self.get_object()
        user_role = self.get_user_role()

        # Increment views only if not provider viewing their own service
        should_track_view = not (
            user_role == 'provider' and
            hasattr(request.user, 'service_provider_profile') and
            instance.provider == request.user.service_provider_profile
        )

        if should_track_view:
            try:
                instance.increment_views()
                ServiceView.objects.create(
                    service=instance,
                    user=request.user if request.user.is_authenticated else None,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
                )
            except Exception as e:
                # Log error but don't fail the request
                print(f"Error tracking service view: {e}")

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrSuperAdmin])
    def update_status(self, request, pk=None):
        """    
        Update service status with notifications    
        """
        try:
            service = Service.objects.get(pk=pk)
        except Service.DoesNotExist:
            return Response({'error': 'Service not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get the old status before update
        old_status = service.status
        # Get the requested new status directly from request
        requested_status = request.data.get('status')

        serializer = ServiceStatusUpdateSerializer(service, data=request.data, context={'request': request})
        if serializer.is_valid():
            try:
                # First send notifications based on status change
                if old_status != requested_status:
                    if requested_status == 'published':
                        NotificationService.send_service_approved_notification(service)
                    elif requested_status == 'rejected':
                        rejection_reason = request.data.get(
                            'rejection_reason', 
                            'Please review and improve your service details.'
                        )
                        NotificationService.send_service_rejected_notification(service, rejection_reason)
                        
            except Exception as notification_error:
                logger.error(f"Failed to send service status notification: {notification_error}")
            
            # Now save the new status in DB
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def my_services(self, request):
        """
        Get current provider's services
        """
        user_role = self.get_user_role()
        if user_role != 'provider':
            return Response(
                {'error': 'Only service providers can access this endpoint'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        if not hasattr(request.user, 'service_provider_profile'):
            return Response(
                {'error': 'Service provider profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        services = self.get_queryset()
        
        # Apply filters
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        
        # Additional filtering by status if requested
        status_filter = request.GET.get('status')
        if status_filter:
            filtered_services = filtered_services.filter(status=status_filter)

        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='admin-services')
    def admin_services(self, request):
        """
        Get all services for admin management
        """
        role = self.get_user_role()
        if role not in ['admin', 'super_admin']:
            return Response(
                {'error': 'Only administrators can access this endpoint'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        services = Service.objects.select_related(
            'provider', 'provider__user', 'category', 'featured_image', 'verified_by'
        ).prefetch_related('images')
        
        # Apply filters
        filtered_services = ServiceFilter(request.GET, queryset=services).qs

        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='get-service-by-id')
    def get_by_id(self, request):
        """
        Get service by ID with proper access control
        """
        service_id = request.query_params.get('id')
        if not service_id:
            return Response(
                {"error": "Service ID is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = self.get_queryset().get(id=service_id)
            serializer = self.get_serializer(service)
            return Response(serializer.data)
        except Service.DoesNotExist:
            return Response(
                {"error": "Service not found or access denied"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {"error": "Invalid service ID format"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """
        Get featured services
        """
        services = self.get_queryset().filter(is_featured=True)
        
        # Apply additional filters
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        
        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """
        Get popular services based on views and leads
        """
        services = self.get_queryset().filter(
            views_count__gt=0
        ).order_by('-views_count', '-leads_count', '-created_at')
        
        # Apply filters
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        
        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Advanced search with service-specific filters
        """
        search_serializer = ServiceSearchSerializer(data=request.GET)
        if not search_serializer.is_valid():
            return Response(search_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        filters = search_serializer.validated_data
        services = self.get_queryset()

        # General text search
        if filters.get('q'):
            search_query = filters['q']
            services = services.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(short_description__icontains=search_query) |
                Q(city__icontains=search_query) |
                Q(provider__business_name__icontains=search_query)
            )

        # Basic filters
        if filters.get('service_type'):
            services = services.filter(service_type=filters['service_type'])
        if filters.get('category'):
            services = services.filter(category_id=filters['category'])
        if filters.get('city'):
            services = services.filter(city__icontains=filters['city'])
        if filters.get('min_price'):
            services = services.filter(price__gte=filters['min_price'])
        if filters.get('max_price'):
            services = services.filter(price__lte=filters['max_price'])

        # Date availability filters
        if filters.get('date_from') or filters.get('date_to'):
            date_from = filters.get('date_from')
            date_to = filters.get('date_to')
            
            date_q = Q(is_always_available=True)
            if date_from:
                date_q |= Q(available_from__lte=date_from)
            if date_to:
                date_q |= Q(available_to__gte=date_to)
            
            services = services.filter(date_q)

        # Air Ticket specific filters
        if filters.get('flight_from'):
            services = services.filter(
                Q(flight_from__icontains=filters['flight_from']) |
                Q(departure_city__icontains=filters['flight_from'])
            )
        if filters.get('flight_to'):
            services = services.filter(
                Q(flight_to__icontains=filters['flight_to']) |
                Q(arrival_city__icontains=filters['flight_to'])
            )
        if filters.get('departure_date'):
            services = services.filter(departure_date=filters['departure_date'])
        if filters.get('return_date'):
            services = services.filter(return_date=filters['return_date'])
        if filters.get('flight_class'):
            services = services.filter(flight_class=filters['flight_class'])
        if filters.get('airline'):
            services = services.filter(airline__icontains=filters['airline'])

        # Zamzam Water specific filters
        if filters.get('min_water_capacity'):
            services = services.filter(water_capacity_liters__gte=filters['min_water_capacity'])
        if filters.get('max_water_capacity'):
            services = services.filter(water_capacity_liters__lte=filters['max_water_capacity'])
        if filters.get('packaging_type'):
            services = services.filter(packaging_type=filters['packaging_type'])

        # Hotel specific filters
        if filters.get('min_star_rating'):
            services = services.filter(hotel_star_rating__gte=filters['min_star_rating'])
        if filters.get('max_star_rating'):
            services = services.filter(hotel_star_rating__lte=filters['max_star_rating'])
        if filters.get('hotel_room_type'):
            services = services.filter(hotel_room_type__icontains=filters['hotel_room_type'])

        # Transport specific filters
        if filters.get('transport_type'):
            services = services.filter(transport_type=filters['transport_type'])
        if filters.get('min_vehicle_capacity'):
            services = services.filter(vehicle_capacity__gte=filters['min_vehicle_capacity'])
        if filters.get('max_vehicle_capacity'):
            services = services.filter(vehicle_capacity__lte=filters['max_vehicle_capacity'])
        if filters.get('pickup_location'):
            services = services.filter(pickup_location__icontains=filters['pickup_location'])
        if filters.get('drop_location'):
            services = services.filter(drop_location__icontains=filters['drop_location'])

        # Additional filters
        if filters.get('is_featured'):
            services = services.filter(is_featured=True)
        if filters.get('is_popular'):
            services = services.filter(is_popular=True)
        if filters.get('min_rating'):
            services = services.annotate(
                avg_rating=Avg('reviews__rating')
            ).filter(avg_rating__gte=filters['min_rating'])
        if filters.get('has_availability'):
            today = timezone.now().date()
            services = services.filter(
                Q(is_always_available=True) |
                Q(availabilities__date__gte=today, availabilities__is_available=True)
            ).distinct()

        # Ordering
        ordering = filters.get('ordering', '-created_at')
        services = services.order_by(ordering)

        page = self.paginate_queryset(services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrSuperAdmin])
    def stats(self, request):
        """
        Get comprehensive service statistics
        """
        cache_key = 'service_stats_v2'
        stats = cache.get(cache_key)

        if not stats:
            # Basic counts
            total_services = Service.objects.count()
            published_services = Service.objects.filter(status=ServiceStatus.PUBLISHED).count()
            pending_services = Service.objects.filter(status=ServiceStatus.PENDING).count()
            verified_services = Service.objects.filter(status=ServiceStatus.VERIFIED).count()
            rejected_services = Service.objects.filter(status=ServiceStatus.REJECTED).count()

            # Analytics
            total_views = Service.objects.aggregate(Sum('views_count'))['views_count__sum'] or 0
            total_leads = Service.objects.aggregate(Sum('leads_count'))['leads_count__sum'] or 0
            total_bookings = Service.objects.aggregate(Sum('bookings_count'))['bookings_count__sum'] or 0

            # Popular categories
            popular_categories = list(
                ServiceCategory.objects.annotate(
                    services_count=Count('services', filter=Q(services__status=ServiceStatus.PUBLISHED))
                ).filter(services_count__gt=0)
                .order_by('-services_count')[:5]
                .values('name', 'services_count')
            )

            # Service type distribution
            service_type_distribution = list(
                Service.objects.filter(status=ServiceStatus.PUBLISHED)
                .values('service_type')
                .annotate(count=Count('id'))
                .order_by('-count')
            )

            # Recent services
            recent_services = Service.objects.select_related(
                'provider', 'category', 'featured_image'
            ).order_by('-created_at')[:10]

            # Top providers
            top_providers = list(
                ServiceProviderProfile.objects.annotate(
                    published_services_count=Count(
                        'services', 
                        filter=Q(services__status=ServiceStatus.PUBLISHED)
                    ),
                    total_views=Sum('services__views_count'),
                ).filter(published_services_count__gt=0)
                .order_by('-published_services_count')[:10]
                .values(
                    'business_name', 'published_services_count', 
                    'total_views', 'user__first_name', 'user__last_name'
                )
            )

            stats = {
                'total_services': total_services,
                'published_services': published_services,
                'pending_services': pending_services,
                'verified_services': verified_services,
                'rejected_services': rejected_services,
                'total_views': total_views,
                'total_leads': total_leads,
                'total_bookings': total_bookings,
                'popular_categories': popular_categories,
                'service_type_distribution': service_type_distribution,
                'recent_services': recent_services,
                'top_providers': top_providers,
            }
            
            cache.set(cache_key, stats, timeout=300)

        # Serialize recent services
        stats['recent_services'] = ServiceListSerializer(
            stats['recent_services'], many=True, context={'request': request}
        ).data

        serializer = ServiceStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_to_favorites(self, request, pk=None):
        """
        Add service to user's favorites
        """
        if self.get_user_role() not in ['pilgrim', 'provider']:
            return Response(
                {'error': 'Only pilgrims can add services to favorites'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        service = self.get_object()
        
        if hasattr(request.user, 'pilgrim_profile'):
            try:
                request.user.pilgrim_profile.favorite_services.add(service)
                return Response({'message': 'Service added to favorites'})
            except Exception as e:
                return Response(
                    {'error': f'Failed to add to favorites: {str(e)}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'error': 'Pilgrim profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=True, methods=['post'])
    def remove_from_favorites(self, request, pk=None):
        """
        Remove service from user's favorites
        """
        if self.get_user_role() not in ['pilgrim', 'provider']:
            return Response(
                {'error': 'Only pilgrims can manage favorites'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        service = self.get_object()
        
        if hasattr(request.user, 'pilgrim_profile'):
            try:
                request.user.pilgrim_profile.favorite_services.remove(service)
                return Response({'message': 'Service removed from favorites'})
            except Exception as e:
                return Response(
                    {'error': f'Failed to remove from favorites: {str(e)}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'error': 'Pilgrim profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=True, methods=['post'])
    def increment_lead(self, request, pk=None):
        """
        Increment lead count for a service
        """
        service = self.get_object()
        try:
            service.increment_leads()
            return Response({
                'message': 'Lead count incremented',
                'leads_count': service.leads_count
            })
        except Exception as e:
            return Response(
                {'error': f'Failed to increment lead: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def by_service_type(self, request):
        """
        Get services filtered by service type with type-specific fields
        """
        service_type = request.GET.get('service_type')
        if not service_type:
            return Response(
                {'error': 'service_type parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if service_type not in [choice.value for choice in ServiceType]:
            return Response(
                {'error': 'Invalid service type'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        services = self.get_queryset().filter(service_type=service_type)
        
        # Apply additional filters
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        
        page = self.paginate_queryset(filtered_services)
        
        # Use specialized serializer based on service type
        serializer_map = {
            ServiceType.AIR_TICKET: AirTicketServiceSerializer,
            ServiceType.JAM_JAM_WATER: ZamzamWaterServiceSerializer,
            ServiceType.HOTEL: HotelServiceSerializer,
            ServiceType.TRANSPORT: TransportServiceSerializer,
        }
        
        serializer_class = serializer_map.get(service_type, ServiceListSerializer)
        serializer = serializer_class(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def provider_stats(self, request):
        """
        Get service statistics for current provider
        """
        user_role = self.get_user_role()
        if user_role != 'provider':
            return Response(
                {'error': 'Only service providers can access provider statistics'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        if not hasattr(request.user, 'service_provider_profile'):
            return Response(
                {'error': 'Service provider profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        provider_profile = request.user.service_provider_profile
        services = Service.objects.filter(provider=provider_profile)
        
        # Get active subscription to show limits
        subscription = provider_profile.get_active_subscription()
        
        stats = {
            'total_services': services.count(),
            'published_services': services.filter(status=ServiceStatus.PUBLISHED).count(),
            'pending_services': services.filter(status=ServiceStatus.PENDING).count(),
            'verified_services': services.filter(status=ServiceStatus.VERIFIED).count(),
            'rejected_services': services.filter(status=ServiceStatus.REJECTED).count(),
            'total_views': services.aggregate(total=Sum('views_count'))['total'] or 0,
            'total_leads': services.aggregate(total=Sum('leads_count'))['total'] or 0,
            'total_bookings': services.aggregate(total=Sum('bookings_count'))['total'] or 0,
            'average_rating': services.aggregate(avg=Avg('reviews__rating'))['avg'] or 0,
            'featured_services': services.filter(is_featured=True).count(),
        }
        
        # Add subscription info if available
        if subscription:
            plan = subscription.plan
            stats['subscription_info'] = {
                'plan_name': plan.name,
                'plan_type': plan.plan_type,
                'service_limit': plan.max_services,
                'remaining_services': max(0, plan.max_services - services.count()),
                'is_ultra_premium': plan.plan_type == 'ultra_premium',
                'unlimited_uploads': plan.unlimited_uploads,
                'unlimited_business_types': plan.unlimited_business_types,
            }
        
        return Response(stats)

class ServiceAvailabilityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Service Availability management
    Allows providers to manage availability slots for their services
    """
    queryset = ServiceAvailability.objects.all()
    serializer_class = ServiceAvailabilitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['service', 'date', 'is_available']
    ordering_fields = ['date', 'created_at']
    ordering = ['date']
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        """
        Filter availability based on user role
        """
        user = self.request.user
        base_queryset = self.queryset.select_related('service', 'service__provider')
        
        if hasattr(user, 'user_type'):
            if user.user_type in ['admin', 'super_admin']:
                return base_queryset
            elif user.user_type == 'provider' and hasattr(user, 'service_provider_profile'):
                return base_queryset.filter(service__provider=user.service_provider_profile)
        elif hasattr(user, 'service_provider_profile'):
            return base_queryset.filter(service__provider=user.service_provider_profile)
        
        return ServiceAvailability.objects.none()
    
    def get_permissions(self):
        """
        Dynamic permissions based on action
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsProviderOrAdmin]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Create availability with proper validation
        """
        service = serializer.validated_data['service']
        user = self.request.user
        
        # Ensure the service belongs to the current provider (unless admin)
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            service.provider != user.service_provider_profile):
            raise ValidationError("You can only create availability for your own services")
        
        serializer.save()

    def perform_update(self, serializer):
        """
        Update availability with validation
        """
        instance = serializer.instance
        user = self.request.user
        # Ensure the service belongs to the current provider (unless admin)
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            instance.service.provider != user.service_provider_profile):
            raise ValidationError("You can only update availability for your own services")
        
        serializer.save()

    @action(detail=False, methods=['get'])
    def by_service(self, request):
        """
        Get availability for a specific service
        """
        service_id = request.GET.get('service_id')
        if not service_id:
            return Response(
                {'error': 'service_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = Service.objects.get(id=service_id)
        except Service.DoesNotExist:
            return Response(
                {'error': 'Service not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user can view this service's availability
        user = self.request.user
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            service.provider != user.service_provider_profile):
            return Response(
                {'error': 'Access denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        availabilities = self.get_queryset().filter(service=service)
        
        # Filter by date range if provided
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        if date_from:
            try:
                date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
                availabilities = availabilities.filter(date__gte=date_from)
            except ValueError:
                return Response(
                    {'error': 'Invalid date_from format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if date_to:
            try:
                date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
                availabilities = availabilities.filter(date__lte=date_to)
            except ValueError:
                return Response(
                    {'error': 'Invalid date_to format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        page = self.paginate_queryset(availabilities)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Create multiple availability slots at once
        """
        service_id = request.data.get('service_id')
        date_from = request.data.get('date_from')
        date_to = request.data.get('date_to')
        available_slots = request.data.get('available_slots', 1)
        price_override = request.data.get('price_override')

        if not all([service_id, date_from, date_to]):
            return Response(
                {'error': 'service_id, date_from, and date_to are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = Service.objects.get(id=service_id)
            date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
        except (Service.DoesNotExist, ValueError) as e:
            return Response(
                {'error': f'Invalid data: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check permissions
        user = self.request.user
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            service.provider != user.service_provider_profile):
            return Response(
                {'error': 'You can only create availability for your own services'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Create availability slots
        created_slots = []
        current_date = date_from
        
        while current_date <= date_to:
            availability, created = ServiceAvailability.objects.get_or_create(
                service=service,
                date=current_date,
                defaults={
                    'available_slots': available_slots,
                    'price_override': price_override,
                    'is_available': True
                }
            )
            
            if created:
                created_slots.append(availability)
            
            current_date += timedelta(days=1)

        serializer = self.get_serializer(created_slots, many=True)
        return Response({
            'message': f'Created {len(created_slots)} availability slots',
            'created_slots': serializer.data
        }, status=status.HTTP_201_CREATED)

class PublicServiceDetailView(APIView):
    """
    Public API to fetch a service by ID
    Accessible by anyone (login or not)
    """
    permission_classes = [AllowAny]  # 👈 Anyone can access

    def get(self, request, *args, **kwargs):
        service_id = request.query_params.get("id")
        if not service_id:
            return Response(
                {"error": "Service ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = Service.objects.get(id=service_id)  # 👈 no access filter
            serializer = ServiceDetailSerializer(service, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Service.DoesNotExist:
            return Response(
                {"error": "Service not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {"error": "Invalid service ID format"},
                status=status.HTTP_400_BAD_REQUEST
            )

class ServiceFAQViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Service FAQs
    Allows providers to manage FAQs for their services
    """
    queryset = ServiceFAQ.objects.all()
    serializer_class = ServiceFAQSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['service']
    ordering_fields = ['display_order', 'created_at']
    ordering = ['display_order']
    
    def get_queryset(self):
        """
        Filter FAQs based on user role
        """
        user = self.request.user
        base_queryset = self.queryset.select_related('service', 'service__provider')
        
        if hasattr(user, 'user_type'):
            if user.user_type in ['admin', 'super_admin']:
                return base_queryset
            elif user.user_type == 'provider' and hasattr(user, 'service_provider_profile'):
                return base_queryset.filter(service__provider=user.service_provider_profile)
            else:
                # Pilgrims can see FAQs for published services only
                return base_queryset.filter(service__status=ServiceStatus.PUBLISHED)
        elif hasattr(user, 'service_provider_profile'):
            return base_queryset.filter(service__provider=user.service_provider_profile)
        else:
            # Anonymous or pilgrim users
            return base_queryset.filter(service__status=ServiceStatus.PUBLISHED)
    
    def get_permissions(self):
        """
        Dynamic permissions based on action
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsProviderOrAdmin]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Create FAQ with proper validation
        """
        service = serializer.validated_data['service']
        user = self.request.user
        
        # Ensure the service belongs to the current provider (unless admin)
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            service.provider != user.service_provider_profile):
            raise ValidationError("You can only create FAQs for your own services")
        
        serializer.save()

    def perform_update(self, serializer):
        """
        Update FAQ with validation
        """
        instance = serializer.instance
        user = self.request.user
        
        # Ensure the service belongs to the current provider (unless admin)
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            instance.service.provider != user.service_provider_profile):
            raise ValidationError("You can only update FAQs for your own services")
        
        serializer.save()

    @action(detail=False, methods=['get'])
    def by_service(self, request):
        """
        Get FAQs for a specific service
        """
        service_id = request.GET.get('service_id')
        if not service_id:
            return Response(
                {'error': 'service_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = Service.objects.get(id=service_id)
        except Service.DoesNotExist:
            return Response(
                {'error': 'Service not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        faqs = self.get_queryset().filter(service=service)
        serializer = self.get_serializer(faqs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Create multiple FAQs at once
        """
        service_id = request.data.get('service_id')
        faqs_data = request.data.get('faqs', [])

        if not service_id or not faqs_data:
            return Response(
                {'error': 'service_id and faqs array are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = Service.objects.get(id=service_id)
        except Service.DoesNotExist:
            return Response(
                {'error': 'Service not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permissions
        user = self.request.user
        if (hasattr(user, 'service_provider_profile') and 
            not hasattr(user, 'user_type') and
            service.provider != user.service_provider_profile):
            return Response(
                {'error': 'You can only create FAQs for your own services'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Create FAQs
        created_faqs = []
        for faq_data in faqs_data:
            faq_data['service'] = service.id
            serializer = self.get_serializer(data=faq_data)
            if serializer.is_valid():
                faq = serializer.save()
                created_faqs.append(faq)
            else:
                return Response(
                    {'error': f'Invalid FAQ data: {serializer.errors}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = self.get_serializer(created_faqs, many=True)
        return Response({
            'message': f'Created {len(created_faqs)} FAQs',
            'created_faqs': serializer.data
        }, status=status.HTTP_201_CREATED)


class ServiceViewViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Service View Analytics
    Provides analytics on service views for admins and providers
    """
    queryset = ServiceView.objects.all()
    serializer_class = ServiceViewSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['service', 'user']
    ordering_fields = ['viewed_at']
    ordering = ['-viewed_at']
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        """
        Filter views based on user role
        """
        user = self.request.user
        base_queryset = self.queryset.select_related('service', 'user')
        
        if hasattr(user, 'user_type'):
            if user.user_type in ['admin', 'super_admin']:
                return base_queryset
            elif user.user_type == 'provider' and hasattr(user, 'service_provider_profile'):
                return base_queryset.filter(service__provider=user.service_provider_profile)
        elif hasattr(user, 'service_provider_profile'):
            return base_queryset.filter(service__provider=user.service_provider_profile)
        
        return ServiceView.objects.none()

    def get_permissions(self):
        """
        Only admins and providers can view analytics
        """
        return [IsProviderOrAdmin()]
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """
        Get comprehensive view analytics
        """
        # Get date range
        days = int(request.GET.get('days', 30))
        date_from = timezone.now() - timedelta(days=days)
        
        queryset = self.get_queryset().filter(viewed_at__gte=date_from)
        
        # Basic analytics
        total_views = queryset.count()
        unique_viewers = queryset.values('ip_address').distinct().count()
        
        # Top services by views
        top_services = list(
            queryset.values(
                'service__title', 'service__id', 'service__provider__company_name'
            ).annotate(
                view_count=Count('id')
            ).order_by('-view_count')[:10]
        )
        
        # Views by date
        views_by_date = list(
            queryset.extra(
                select={'date': 'DATE(viewed_at)'}
            ).values('date').annotate(
                view_count=Count('id')
            ).order_by('date')
        )
        
        # Views by hour (for today)
        today = timezone.now().date()
        views_by_hour = list(
            queryset.filter(viewed_at__date=today)
            .extra(select={'hour': 'HOUR(viewed_at)'})
            .values('hour')
            .annotate(view_count=Count('id'))
            .order_by('hour')
        )
        
        # Top referrers (based on user agent)
        top_user_agents = list(
            queryset.exclude(user_agent='')
            .values('user_agent')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        
        analytics_data = {
            'date_range': {
                'from': date_from.date(),
                'to': timezone.now().date(),
                'days': days
            },
            'summary': {
                'total_views': total_views,
                'unique_viewers': unique_viewers,
                'avg_views_per_day': round(total_views / days, 2) if days > 0 else 0
            },
            'top_services': top_services,
            'views_by_date': views_by_date,
            'views_by_hour': views_by_hour,
            'top_user_agents': top_user_agents
        }
        
        return Response(analytics_data)

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """
        Export view data as CSV
        """
        import csv
        from django.http import HttpResponse
        
        # Get filtered queryset
        queryset = self.get_queryset()
        
        # Apply date filter if provided
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        if date_from:
            try:
                date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(viewed_at__date__gte=date_from)
            except ValueError:
                return Response(
                    {'error': 'Invalid date_from format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if date_to:
            try:
                date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(viewed_at__date__lte=date_to)
            except ValueError:
                return Response(
                    {'error': 'Invalid date_to format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="service_views.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Service Title', 'Provider', 'Viewer', 'IP Address', 
            'User Agent', 'Viewed At'
        ])
        
        for view in queryset.select_related('service', 'service__provider', 'user')[:10000]:  # Limit to 10k rows
            writer.writerow([
                view.service.title,
                view.service.provider.company_name if view.service.provider else '',
                view.user.get_full_name() if view.user else 'Anonymous',
                view.ip_address,
                view.user_agent[:100],  # Truncate long user agents
                view.viewed_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response


# Additional utility views

@api_view(['GET'])
@permission_classes([AllowAny])
def service_stats_public(request):
    """
    Public statistics for services (cached)
    """
    cache_key = 'public_service_stats'
    stats = cache.get(cache_key)
    
    if not stats:
        stats = {
            'total_published_services': Service.objects.filter(
                status=ServiceStatus.PUBLISHED
            ).count(),
            'total_categories': ServiceCategory.objects.filter(
                is_active=True
            ).count(),
            'total_providers': ServiceProviderProfile.objects.filter(
                services__status=ServiceStatus.PUBLISHED
            ).distinct().count(),
            'popular_service_types': list(
                Service.objects.filter(status=ServiceStatus.PUBLISHED)
                .values('service_type')
                .annotate(count=Count('id'))
                .order_by('-count')[:5]
            ),
            'cities_covered': list(
                Service.objects.filter(status=ServiceStatus.PUBLISHED)
                .exclude(city='')
                .values('city')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
            )
        }
        cache.set(cache_key, stats, timeout=3600)  # Cache for 1 hour
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_service_action(request):
    """
    Perform bulk actions on services (Admin only)
    """
    user = request.user
    if not hasattr(user, 'user_type') or user.user_type not in ['admin', 'super_admin']:
        return Response(
            {'error': 'Only administrators can perform bulk actions'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    action = request.data.get('action')
    service_ids = request.data.get('service_ids', [])
    
    if not action or not service_ids:
        return Response(
            {'error': 'action and service_ids are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    valid_actions = ['publish', 'reject', 'delete', 'feature', 'unfeature']
    if action not in valid_actions:
        return Response(
            {'error': f'Invalid action. Valid actions: {valid_actions}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        services = Service.objects.filter(id__in=service_ids)
        updated_count = 0
        
        if action == 'publish':
            updated_count = services.update(
                status=ServiceStatus.PUBLISHED,
                verified_by=user,
                verified_at=timezone.now()
            )
        elif action == 'reject':
            reason = request.data.get('reason', 'Bulk rejection by admin')
            updated_count = services.update(
                status=ServiceStatus.REJECTED,
                rejection_reason=reason,
                verified_by=user,
                verified_at=timezone.now()
            )
        elif action == 'delete':
            updated_count = services.count()
            services.delete()
        elif action == 'feature':
            updated_count = services.update(is_featured=True)
        elif action == 'unfeature':
            updated_count = services.update(is_featured=False)
        
        return Response({
            'message': f'Successfully {action}ed {updated_count} services',
            'updated_count': updated_count
        })
        
    except Exception as e:
        return Response(
            {'error': f'Bulk action failed: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )