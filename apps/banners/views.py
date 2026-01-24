from rest_framework import viewsets, generics, status, filters
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model
from .permissions import PublicReadAdminWrite
from .models import Banner, PopularDestination
from .serializers import (
    BannerSerializer, 
    PopularDestinationSerializer,
    PopularDestinationListSerializer
)

User = get_user_model()

class BannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.filter(is_active=True)
    serializer_class = BannerSerializer
    permission_classes = [PublicReadAdminWrite]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['priority_weight', 'display_order', 'created_at']
    
    def get_queryset(self):
        queryset = Banner.objects.filter(is_active=True)
        now = timezone.now()
        
        # Filter active banners based on dates
        queryset = queryset.filter(
            Q(start_date__lte=now) | Q(start_date__isnull=True),
            Q(end_date__gte=now) | Q(end_date__isnull=True)
        )
        
        # Filter by banner type
        banner_type = self.request.query_params.get('banner_type', None)
        if banner_type:
            queryset = queryset.filter(banner_type=banner_type)
        
        return queryset
    
    def get_location_based_banners(self, user, banner_type=None, limit=None):
        """Get banners filtered by provider location and business type"""
        queryset = self.get_queryset()
        
        if banner_type:
            queryset = queryset.filter(banner_type=banner_type)
        
        # Get banners for current user context
        if user and user.is_authenticated:
            banners = []
            
            for banner in queryset:
                
                # For providers, check business type and location
                if user.user_type == 'provider':
                    try:
                        profile = user.service_provider_profile
                        
                        # Check business type match
                        if not banner.matches_provider_business(profile.business_type):
                            continue
                        
                        # Check location match
                        if not banner.matches_location(profile):
                            continue
                        
                        banners.append(banner)
                    except:
                        # Provider doesn't have profile, skip
                        continue
                else:
                    # For pilgrims, just add if user type matches
                    banners.append(banner)
            
            # Sort by priority weight and display order
            banners.sort(key=lambda x: (-x.priority_weight, x.display_order))
            
            if limit:
                banners = banners[:limit]
            
            return banners
        
        # For anonymous users, return banners with no user type restriction
        # or only those targeting 'anonymous'
        banners = []
        for banner in queryset:
            banners.append(banner)
        
        banners.sort(key=lambda x: (-x.priority_weight, x.display_order))
        
        if limit:
            banners = banners[:limit]
        
        return banners
    
    def list(self, request, *args, **kwargs):
        """Get all banners for current user context"""
        user = request.user if request.user.is_authenticated else None
        banners = self.get_location_based_banners(user)
        
        page = self.paginate_queryset(banners)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(banners, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def main_screen(self, request):
        """Get main screen banners based on user context"""
        user = request.user if request.user.is_authenticated else None
        banners = self.get_location_based_banners(user, 'main_screen', limit=5)
        serializer = self.get_serializer(banners, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def offers(self, request):
        """Get offer banners based on user context"""
        user = request.user if request.user.is_authenticated else None
        banners = self.get_location_based_banners(user, 'offer', limit=3)
        serializer = self.get_serializer(banners, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_provider(self, request):
        """Get banners specifically for providers"""
        user = request.user
        
        if not user.is_authenticated or user.user_type != 'provider':
            return Response(
                {'error': 'Only providers can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            profile = user.service_provider_profile
            
            # Get banners that match provider's business type and location
            queryset = self.get_queryset().filter(
                Q(provider_business_type='') | Q(provider_business_type=profile.business_type)
            )
            
            # Filter by location match
            banners = []
            for banner in queryset:
                if banner.matches_location(profile):
                    banners.append(banner)
            
            banners.sort(key=lambda x: (-x.priority_weight, x.display_order))
            
            serializer = self.get_serializer(banners[:10], many=True)
            return Response(serializer.data)
            
        except User.service_provider_profile.RelatedObjectDoesNotExist:
            return Response(
                {'error': 'Provider profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def by_location(self, request):
        """Get banners for specific location"""
        city = request.query_params.get('city')
        state = request.query_params.get('state')
        country = request.query_params.get('country')
        
        if not any([city, state, country]):
            return Response(
                {'error': 'Please provide at least one location parameter (city, state, or country)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset()
        
        # Build location filters
        filters = Q()
        if city:
            filters |= Q(target_city__iexact=city)
        if state:
            filters |= Q(target_state__iexact=state)
        if country:
            filters |= Q(target_country__iexact=country)
        
        # Also include banners with no location targeting
        filters |= Q(target_city='', target_state='', target_country='')
        
        banners = queryset.filter(filters).order_by('-priority_weight', 'display_order')
        serializer = self.get_serializer(banners[:20], many=True)
        
        return Response(serializer.data)

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import status

class PopularDestinationViewSet(viewsets.ModelViewSet):
    queryset = PopularDestination.objects.all()
    serializer_class = PopularDestinationSerializer
    permission_classes = [PublicReadAdminWrite]
    # ADD THIS LINE - CRITICAL for file uploads
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'short_description', 'detailed_description', 'location']
    ordering_fields = ['view_count', 'display_order', 'created_at']
    ordering = ['display_order', '-is_featured']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PopularDestinationListSerializer
        return PopularDestinationSerializer
    
    def create(self, request, *args, **kwargs):
        """Override create to handle file uploads properly"""
        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Override update to handle partial updates with files"""
        return super().update(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.view_count += 1
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def hajj_destinations(self, request):
        """Get all Hajj destinations"""
        destinations = self.get_queryset().filter(destination_type='hajj')
        serializer = self.get_serializer(destinations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def umrah_destinations(self, request):
        """Get all Umrah destinations"""
        destinations = self.get_queryset().filter(destination_type='umrah')
        serializer = self.get_serializer(destinations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def ziyarat_destinations(self, request):
        """Get all Ziyarat destinations"""
        destinations = self.get_queryset().filter(destination_type='ziyarat')
        serializer = self.get_serializer(destinations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured destinations"""
        destinations = self.get_queryset().filter(is_featured=True)[:6]
        serializer = self.get_serializer(destinations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def search_by_type(self, request):
        """Search destinations by type"""
        destination_type = request.query_params.get('type')
        ziyarat_type = request.query_params.get('ziyarat_type')
        
        if not destination_type and not ziyarat_type:
            return Response(
                {'error': 'Please provide type or ziyarat_type parameter'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset()
        
        if destination_type:
            queryset = queryset.filter(destination_type=destination_type)
        
        if ziyarat_type:
            queryset = queryset.filter(ziyarat_type=ziyarat_type)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
class HomeView(generics.GenericAPIView):
    """Home view with banners and destinations"""
    
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        
        # Get banners
        banner_viewset = BannerViewSet()
        banner_viewset.request = request
        
        main_banners = banner_viewset.get_location_based_banners(user, 'main_screen', 5)
        offer_banners = banner_viewset.get_location_based_banners(user, 'offer', 3)
        
        # Get destinations
        featured_destinations = PopularDestination.objects.filter(
            is_active=True,
            is_featured=True
        )[:6]
        
        top_viewed = PopularDestination.objects.filter(
            is_active=True
        ).order_by('-view_count')[:5]
        
        data = {
            'main_screen_banners': BannerSerializer(
                main_banners, 
                many=True, 
                context={'request': request}
            ).data,
            'offer_banners': BannerSerializer(
                offer_banners, 
                many=True, 
                context={'request': request}
            ).data,
            'featured_destinations': PopularDestinationListSerializer(
                featured_destinations,
                many=True,
                context={'request': request}
            ).data,
            'top_viewed_destinations': PopularDestinationListSerializer(
                top_viewed,
                many=True,
                context={'request': request}
            ).data,
        }
        
        return Response(data)