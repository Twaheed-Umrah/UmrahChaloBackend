import math
from rest_framework import viewsets, generics, status, filters
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from .permissions import PublicReadAdminWrite
from .models import Banner, PopularDestination, BannerType
from .serializers import (
    BannerSerializer, 
    PopularDestinationSerializer,
    PopularDestinationListSerializer
)

User = get_user_model()

def calculate_haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in kilometers between two GPS points"""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371.0  # Earth's radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2)**2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except (TypeError, ValueError, ZeroDivisionError):
        return None

class BannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.filter(is_active=True)
    serializer_class = BannerSerializer
    permission_classes = [PublicReadAdminWrite]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['banner_type', 'is_active']
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

    def get_default_fallback_banners(self, request, banner_type=None, limit=None):
        """
        When no location-specific banners match, return ALL active banners from the database
        so every uploaded database banner image is shown by default.
        """
        now = timezone.now()
        active_qs = Banner.objects.filter(is_active=True).filter(
            Q(start_date__lte=now) | Q(start_date__isnull=True),
            Q(end_date__gte=now) | Q(end_date__isnull=True)
        ).order_by('-priority_weight', 'display_order', '-created_at')

        if not active_qs.exists():
            active_qs = Banner.objects.filter(is_active=True).order_by('-priority_weight', 'display_order', '-created_at')

        if active_qs.exists():
            # If a banner_type is requested, place matching banner_type first,
            # followed by ALL other active database banners so all database banners are shown by default.
            if banner_type:
                typed = list(active_qs.filter(banner_type=banner_type))
                others = list(active_qs.exclude(banner_type=banner_type))
                all_banners = typed + others
                return all_banners[:limit] if limit else all_banners
            return list(active_qs[:limit] if limit else active_qs)

        return []

    def get_location_based_banners(self, request_or_user=None, banner_type=None, limit=None):
        """
        Get banners filtered by client location (area, pincode, km radius, city).
        If no banner matches the client's location, returns ALL database banners by default.
        """
        queryset = self.get_queryset()
        
        if banner_type:
            queryset = queryset.filter(banner_type=banner_type)
        
        request = None
        user = None
        if hasattr(request_or_user, 'query_params'):
            request = request_or_user
            user = request.user if (hasattr(request, 'user') and request.user.is_authenticated) else None
        elif hasattr(request_or_user, 'is_authenticated'):
            user = request_or_user
            request = getattr(self, 'request', None)
        else:
            request = getattr(self, 'request', None)
            user = request.user if (request and hasattr(request, 'user') and request.user.is_authenticated) else None

        client_lat = None
        client_lng = None
        client_city = ''
        client_state = ''
        client_country = ''
        client_area = ''
        client_pincode = ''

        if request:
            client_lat = request.query_params.get('latitude') or request.query_params.get('lat')
            client_lng = request.query_params.get('longitude') or request.query_params.get('lng')
            client_city = (request.query_params.get('city') or '').strip().lower()
            client_state = (request.query_params.get('state') or '').strip().lower()
            client_country = (request.query_params.get('country') or '').strip().lower()
            client_area = (request.query_params.get('area') or request.query_params.get('sector') or '').strip().lower()
            client_pincode = (request.query_params.get('pincode') or request.query_params.get('pin') or '').strip().lower()

        # If user is a provider browsing, fallback to their profile location
        provider_profile = None
        if user and getattr(user, 'user_type', None) == 'provider':
            try:
                provider_profile = user.service_provider_profile
                if not client_city and provider_profile.business_city:
                    client_city = provider_profile.business_city.lower()
                if not client_state and provider_profile.business_state:
                    client_state = provider_profile.business_state.lower()
                if not client_pincode and provider_profile.business_pincode:
                    client_pincode = provider_profile.business_pincode.lower()
            except Exception:
                pass

        has_location_filter = bool(client_lat or client_lng or client_city or client_area or client_pincode)

        location_matched = []
        universal_banners = []

        for banner in queryset:
            # 1. Provider business type check (if browsing user is provider)
            if provider_profile and banner.provider_business_type:
                if not banner.matches_provider_business(provider_profile.business_type):
                    continue

            # 2. Check if banner has NO location targeting at all
            has_targeting = bool(
                banner.target_city or 
                banner.target_state or 
                banner.target_country or 
                banner.target_area or 
                banner.target_pincode or 
                (banner.target_latitude is not None and banner.target_longitude is not None)
            )

            if not has_targeting:
                score = 1 + (banner.priority_weight or 1)
                universal_banners.append((score, banner))
                continue

            # 3. Banner has targeting -> check against client location
            match_score = 0
            is_matched = False

            # A. GPS Coordinates & KM Radius Check
            if client_lat and client_lng and banner.target_latitude is not None and banner.target_longitude is not None:
                dist = calculate_haversine(client_lat, client_lng, banner.target_latitude, banner.target_longitude)
                radius = float(banner.radius_km or 25.0)
                if dist is not None and dist <= radius:
                    is_matched = True
                    match_score = max(match_score, 100 - min(dist, 50) + (banner.priority_weight * 5))
                elif dist is not None and dist > radius:
                    continue

            # B. Pincode Match
            if client_pincode and banner.target_pincode:
                if client_pincode == banner.target_pincode.strip().lower():
                    is_matched = True
                    match_score = max(match_score, 80 + (banner.priority_weight * 5))

            # C. Area / Sector Match
            if client_area and banner.target_area:
                b_area = banner.target_area.strip().lower()
                if client_area in b_area or b_area in client_area:
                    is_matched = True
                    match_score = max(match_score, 70 + (banner.priority_weight * 5))

            # D. City Match
            if client_city and banner.target_city:
                b_city = banner.target_city.strip().lower()
                if client_city in b_city or b_city in client_city:
                    if not banner.target_area and banner.target_latitude is None and not banner.target_pincode:
                        is_matched = True
                        match_score = max(match_score, 40 + (banner.priority_weight * 5))
                else:
                    continue

            # E. State Match
            if client_state and banner.target_state and not banner.target_city and not banner.target_area:
                b_state = banner.target_state.strip().lower()
                if client_state in b_state or b_state in client_state:
                    is_matched = True
                    match_score = max(match_score, 20 + (banner.priority_weight * 5))

            if is_matched:
                location_matched.append((match_score, banner))

        # USER REQUIREMENT:
        # If there are NO banners matching the location (or no location specified),
        # show ALL database banners by default!
        if has_location_filter and location_matched:
            # Sort location-matched banners first
            location_matched.sort(key=lambda item: (
                -item[0],
                -(item[1].priority_weight or 1),
                item[1].display_order,
                -item[1].created_at.timestamp() if item[1].created_at else 0
            ))
            # Also include universal database banners after location-specific banners
            universal_banners.sort(key=lambda item: (
                -item[0],
                -(item[1].priority_weight or 1),
                item[1].display_order,
                -item[1].created_at.timestamp() if item[1].created_at else 0
            ))
            result = [item[1] for item in location_matched] + [item[1] for item in universal_banners]
        else:
            # No banner according to location -> show ALL database banners by default!
            result = self.get_default_fallback_banners(request, banner_type=banner_type)

        if limit:
            result = result[:limit]
        return result
    
    def list(self, request, *args, **kwargs):
        """Get all banners for current user/client location context"""
        banners = self.get_location_based_banners(request)
        if not banners:
            banners = self.get_default_fallback_banners(request)

        page = self.paginate_queryset(banners)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(banners, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def main_screen(self, request):
        """Get main screen banners. When no location banner matches, returns ALL database banners by default."""
        banners = self.get_location_based_banners(request, banner_type='main_screen')
        if not banners:
            banners = self.get_default_fallback_banners(request)
        serializer = self.get_serializer(banners, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def offers(self, request):
        """Get offer banners. When no location banner matches, returns ALL database banners by default."""
        banners = self.get_location_based_banners(request, banner_type='offer')
        if not banners:
            banners = self.get_default_fallback_banners(request)
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
            if not banners:
                banners = self.get_default_fallback_banners(request, limit=10)
            
            serializer = self.get_serializer(banners[:10], many=True)
            return Response(serializer.data)
            
        except Exception:
            return Response(
                {'error': 'Provider profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def by_location(self, request):
        """Get banners for specific location"""
        banners = self.get_location_based_banners(request, limit=20)
        if not banners:
            return Response(self.get_synthetic_default_banner(request))
        serializer = self.get_serializer(banners, many=True)
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
        
        main_banners = banner_viewset.get_location_based_banners(request, 'main_screen', 5)
        offer_banners = banner_viewset.get_location_based_banners(request, 'offer', 3)
        
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