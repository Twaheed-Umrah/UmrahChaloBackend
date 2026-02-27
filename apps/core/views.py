from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import MasterPincode
from .serializers import MasterPincodeSerializer

class MasterPincodeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing and searching master pincodes
    """
    queryset = MasterPincode.objects.all()
    serializer_class = MasterPincodeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(pincode__icontains=search) |
                Q(area_name__icontains=search) |
                Q(city__icontains=search)
            )
        return queryset

    @action(detail=False, methods=['get'])
    def suggestions(self, request):
        """
        Get 20 localized pincode suggestions based on the provider's location
        """
        user = request.user
        profile = getattr(user, 'service_provider_profile', None)
        
        if not profile:
            return Response(
                {"error": "Only service providers can get localized suggestions."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Build query filters using Q objects to avoid "Cannot combine unique query" error
        query_filter = Q()
        
        # 1. By Coordinates (if provider has location)
        if user.latitude and user.longitude:
            try:
                lat = float(user.latitude)
                lng = float(user.longitude)
                lat_range = 0.5
                lng_range = 0.5
                query_filter |= Q(
                    latitude__gte=lat - lat_range,
                    latitude__lte=lat + lat_range,
                    longitude__gte=lng - lng_range,
                    longitude__lte=lng + lng_range
                )
            except (ValueError, TypeError):
                pass

        # 2. By City
        if profile.business_city:
            query_filter |= Q(city__icontains=profile.business_city)

        # 3. By State
        if profile.business_state:
            query_filter |= Q(state__icontains=profile.business_state)

        # Execute query
        suggestions = MasterPincode.objects.filter(query_filter).distinct()

        # Fallback if no suggestions found or empty filters
        if not suggestions.exists():
            suggestions = MasterPincode.objects.all()[:20]
        else:
            suggestions = suggestions[:20]

        serializer = self.get_serializer(suggestions, many=True)
        return Response(serializer.data)
