from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from .models import (
    ServiceCategory, ServiceImage, Service, ServiceAvailability, 
    ServiceFAQ, ServiceView, ServiceType, ServiceStatus
)
from .serializers import (
    ServiceCategorySerializer, ServiceImageSerializer, ServiceListSerializer,
    ServiceDetailSerializer, ServiceCreateUpdateSerializer, ServiceStatusUpdateSerializer,
    ServiceAvailabilitySerializer, ServiceFAQSerializer, ServiceViewSerializer,
    ServiceStatsSerializer, ServiceSearchSerializer
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
    ViewSet for Service Categories (Read-only for all users)
    """
    queryset = ServiceCategory.objects.filter(is_active=True)
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [OrderingFilter]
    ordering_fields = ['name', 'display_order']
    ordering = ['display_order', 'name']
    
    def get_queryset(self):
        qs = self.queryset.prefetch_related('services')

        # Exclude Hajj Package and Umrah Package by name
        return qs.exclude(name__in=["Hajj Package", "Umrah Package"])
        
    @action(detail=True, methods=['get'])
    def services(self, request, pk=None):
        """
        Get all services for a specific category
        """
        category = self.get_object()
        services = Service.objects.filter(
            category=category,
            status=ServiceStatus.PUBLISHED
        ).select_related('provider', 'category', 'featured_image')
        
        # Apply filters
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        
        # Pagination
        paginator = LargeResultsSetPagination()
        page = paginator.paginate_queryset(filtered_services, request)
        
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

class ServiceImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Service Images:
    - SuperAdmin/Admin can upload images
    - Providers can view images
    """
    queryset = ServiceImage.objects.filter(is_active=True)
    serializer_class = ServiceImageSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category']
    search_fields = ['name', 'alt_text']

    def get_queryset(self):
        return self.queryset.select_related('category')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrSuperAdmin()]
        return [permissions.IsAuthenticated()]

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def service_type_choices(request):
    choices = [{'value': choice.value, 'label': choice.label} for choice in ServiceType]
    return Response(choices)

class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ServiceFilter
    search_fields = ['title', 'description', 'city', 'state']
    ordering_fields = ['price', 'created_at', 'views_count', 'title']
    ordering = ['-created_at']
    pagination_class = LargeResultsSetPagination

    def get_user_role(self):
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
        user = self.request.user
        role = self.get_user_role()
        base_queryset = self.queryset.select_related('provider', 'category', 'featured_image')
        if role in ['admin', 'super_admin']:
            return base_queryset
        elif role == 'provider':
            if hasattr(user, 'service_provider_profile'):
                return base_queryset.filter(provider=user.service_provider_profile)
            return self.queryset.none()
        elif role == 'pilgrim':
            return base_queryset.filter(
                status=ServiceStatus.PUBLISHED,
                provider__subscriptions__is_active=True
            )
        return self.queryset.none()

    def get_serializer_class(self):
        if self.action == 'list':
            return ServiceListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ServiceCreateUpdateSerializer
        elif self.action == 'update_status':
            return ServiceStatusUpdateSerializer
        return ServiceDetailSerializer

    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'retrieve':
            permission_classes = [IsVerifiedProvider, IsActiveSubscription]
        elif self.action == 'create':
            permission_classes = [IsVerifiedProvider, IsActiveSubscription]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [CanManageService]
        elif self.action == 'update_status':
            permission_classes = [IsAdminOrSuperAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        try:
            profile = self.request.user.service_provider_profile
        except ServiceProviderProfile.DoesNotExist:
            raise ValidationError("Only providers can create services.")
    
        serializer.save(provider=profile)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user_role = self.get_user_role()

        if not (user_role == 'provider' and
                hasattr(request.user, 'service_provider_profile') and
                instance.provider == request.user.service_provider_profile):
            instance.increment_views()
            ServiceView.objects.create(
                service=instance,
                user=request.user if request.user.is_authenticated else None,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, 'service_provider_profile'):
            raise ValidationError("Only providers can update services.")
        serializer.save(provider=self.request.user.service_provider_profile)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrSuperAdmin])
    def update_status(self, request, pk=None):
        try:
                     service = Service.objects.get(pk=pk)
        except Service.DoesNotExist:
                      return Response({'error': 'Service not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ServiceStatusUpdateSerializer(service, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def my_services(self, request):
        if not (hasattr(request.user, 'service_provider_profile') and self.get_user_role() == 'provider'):
            return Response({'error': 'Only providers can access this endpoint'}, status=status.HTTP_403_FORBIDDEN)

        services = self.get_queryset().filter(provider=request.user.service_provider_profile)
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)
    @action(detail=False, methods=['get'], url_path='admin-services')
    def admin_services(self, request):
        role = self.get_user_role()

        if role not in ['admin', 'super_admin']:
            return Response({'error': 'Only admins can access this endpoint'}, status=status.HTTP_403_FORBIDDEN)

        services = self.get_queryset()
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)
    @action(detail=False, methods=['get'], url_path='get-service-by-id')
    def get_by_id(self, request):
        service_id = request.query_params.get('id')
        if not service_id:
            return Response({"error": "ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            service = self.get_queryset().get(id=service_id)
            serializer = self.get_serializer(service)
            return Response(serializer.data)
        except Service.DoesNotExist:
            return Response({"error": "Service not found"}, status=status.HTTP_404_NOT_FOUND)
    @action(detail=False, methods=['get'])
    def featured(self, request):
        services = self.get_queryset().filter(is_featured=True, status=ServiceStatus.PUBLISHED)
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def popular(self, request):
        services = self.get_queryset().filter(status=ServiceStatus.PUBLISHED).order_by('-views_count', '-leads_count')
        filtered_services = ServiceFilter(request.GET, queryset=services).qs
        page = self.paginate_queryset(filtered_services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        search_serializer = ServiceSearchSerializer(data=request.GET)
        if not search_serializer.is_valid():
            return Response(search_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        filters = search_serializer.validated_data
        services = self.get_queryset().filter(status=ServiceStatus.PUBLISHED)

        if filters.get('q'):
            services = services.filter(
                Q(title__icontains=filters['q']) |
                Q(description__icontains=filters['q']) |
                Q(city__icontains=filters['q']) |
                Q(provider__company_name__icontains=filters['q'])
            )
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
        if filters.get('date_from'):
            services = services.filter(Q(is_always_available=True) | Q(available_from__lte=filters['date_from']))
        if filters.get('date_to'):
            services = services.filter(Q(is_always_available=True) | Q(available_to__gte=filters['date_to']))
        if filters.get('departure_city'):
            services = services.filter(departure_city__icontains=filters['departure_city'])
        if filters.get('arrival_city'):
            services = services.filter(arrival_city__icontains=filters['arrival_city'])
        if filters.get('departure_date'):
            services = services.filter(departure_date=filters['departure_date'])
        if filters.get('is_featured'):
            services = services.filter(is_featured=True)
        if filters.get('is_popular'):
            services = services.filter(is_popular=True)
        if filters.get('min_rating'):
            services = services.annotate(avg_rating=Avg('reviews__rating')).filter(avg_rating__gte=filters['min_rating'])

        ordering = filters.get('ordering', '-created_at')
        services = services.order_by(ordering)

        page = self.paginate_queryset(services)
        serializer = ServiceListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrSuperAdmin])
    def stats(self, request):
        cache_key = 'service_stats'
        stats = cache.get(cache_key)

        if not stats:
            stats = {
                'total_services': Service.objects.count(),
                'published_services': Service.objects.filter(status=ServiceStatus.PUBLISHED).count(),
                'pending_services': Service.objects.filter(status=ServiceStatus.PENDING).count(),
                'total_views': Service.objects.aggregate(Sum('views_count'))['views_count__sum'] or 0,
                'total_leads': Service.objects.aggregate(Sum('leads_count'))['leads_count__sum'] or 0,
                'popular_categories': list(
                    ServiceCategory.objects.annotate(
                        services_count=Count('services')
                    ).order_by('-services_count')[:5].values('name', 'services_count')
                ),
                'recent_services': Service.objects.order_by('-created_at')[:10]
            }
            cache.set(cache_key, stats, timeout=300)

        stats['recent_services'] = ServiceListSerializer(
            stats['recent_services'], many=True, context={'request': request}
        ).data

        serializer = ServiceStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_to_favorites(self, request, pk=None):
        if self.get_user_role() != 'pilgrim':
            return Response({'error': 'Only pilgrims can add services to favorites'}, status=status.HTTP_403_FORBIDDEN)
        service = self.get_object()
        if hasattr(request.user, 'pilgrim_profile'):
            request.user.pilgrim_profile.favorite_services.add(service)
            return Response({'message': 'Service added to favorites'})
        return Response({'error': 'Pilgrim profile not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def remove_from_favorites(self, request, pk=None):
        if self.get_user_role() != 'pilgrim':
            return Response({'error': 'Only pilgrims can remove services from favorites'}, status=status.HTTP_403_FORBIDDEN)
        service = self.get_object()
        if hasattr(request.user, 'pilgrim_profile'):
            request.user.pilgrim_profile.favorite_services.remove(service)
            return Response({'message': 'Service removed from favorites'})
        return Response({'error': 'Pilgrim profile not found'}, status=status.HTTP_404_NOT_FOUND)
  
class ServiceAvailabilityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Service Availability management
    """
    queryset = ServiceAvailability.objects.all()
    serializer_class = ServiceAvailabilitySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['service', 'date', 'is_available']
    ordering_fields = ['date']
    ordering = ['date']
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'service_provider_profile'):
            if user.service_provider_profile.role  in ['admin', 'super_admin']:
                return self.queryset.select_related('service')
            elif user.service_provider_profile.role == 'provider':
                return self.queryset.filter(
                    service__provider=user.service_provider_profile
                ).select_related('service')
        
        return ServiceAvailability.objects.none()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsProviderOrAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        # Ensure the service belongs to the current provider
        service = serializer.validated_data['service']
        if (hasattr(self.request.user, 'service_provider_profile') and 
            self.request.user.service_provider_profile.role == 'provider' and 
            service.provider != self.request.user.service_provider_profile):
            raise serializers.ValidationError(
                "You can only create availability for your own services"
            )
        
        serializer.save()

class ServiceFAQViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Service FAQs
    """
    queryset = ServiceFAQ.objects.all()
    serializer_class = ServiceFAQSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['service']
    ordering_fields = ['display_order']
    ordering = ['display_order']
    
    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'profile'):
            if user.service_provider_profile.role  in ['admin', 'super_admin']:
                return self.queryset.select_related('service')
            elif user.service_provider_profile.role == 'provider':
                return self.queryset.filter(
                    service__provider=user.service_provider_profile
                ).select_related('service')
            else:
                # Pilgrims can see FAQs for published services only
                return self.queryset.filter(
                    service__status=ServiceStatus.PUBLISHED
                ).select_related('service')
        
        return ServiceFAQ.objects.none()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsProviderOrAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        user = self.request.user

        try:
            provider_profile = user.service_provider_profile  # One-to-one or reverse relation
        except ServiceProviderProfile.DoesNotExist:
            raise ValidationError("You must create a ServiceProviderProfile before creating a service.")

        serializer.save(provider=provider_profile)

class ServiceViewViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Service View Analytics (Admin only)
    """
    queryset = ServiceView.objects.all()
    serializer_class = ServiceViewSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['service', 'user']
    ordering_fields = ['viewed_at']
    ordering = ['-viewed_at']
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        return self.queryset.select_related('service', 'user')
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """
        Get view analytics summary
        """
        from django.db.models import Count
        from django.utils import timezone
        from datetime import timedelta
        
        # Get date range
        days = int(request.GET.get('days', 30))
        date_from = timezone.now() - timedelta(days=days)
        
        analytics = {
            'total_views': self.get_queryset().count(),
            'recent_views': self.get_queryset().filter(viewed_at__gte=date_from).count(),
            'top_services': list(
                self.get_queryset().filter(viewed_at__gte=date_from)
                .values('service__title', 'service__id')
                .annotate(view_count=Count('id'))
                .order_by('-view_count')[:10]
            ),
            'views_by_date': list(
                self.get_queryset().filter(viewed_at__gte=date_from)
                .extra(select={'date': 'DATE(viewed_at)'})
                .values('date')
                .annotate(view_count=Count('id'))
                .order_by('date')
            )
        }
        
        return Response(analytics)