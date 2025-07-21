import django_filters
from django.db import models
from django.utils import timezone
from .models import Package


class PackageFilter(django_filters.FilterSet):
    """Filter for packages with various search options"""
    
    # Basic filters
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains'
    )
    
    package_type = django_filters.ChoiceFilter(
        field_name='package_type',
        choices=Package.PACKAGE_TYPES
    )
    
    # Price range filters
    min_price = django_filters.NumberFilter(
        method='filter_min_price',
        label='Minimum Price'
    )
    
    max_price = django_filters.NumberFilter(
        method='filter_max_price',
        label='Maximum Price'
    )
    
    # Date filters
    start_date_from = django_filters.DateFilter(
        field_name='start_date',
        lookup_expr='gte'
    )
    
    start_date_to = django_filters.DateFilter(
        field_name='start_date',
        lookup_expr='lte'
    )
    
    end_date_from = django_filters.DateFilter(
        field_name='end_date',
        lookup_expr='gte'
    )
    
    end_date_to = django_filters.DateFilter(
        field_name='end_date',
        lookup_expr='lte'
    )
    
    # Duration filters
    min_duration = django_filters.NumberFilter(
        field_name='duration_days',
        lookup_expr='gte'
    )
    
    max_duration = django_filters.NumberFilter(
        field_name='duration_days',
        lookup_expr='lte'
    )
    
    # Rating filter
    min_rating = django_filters.NumberFilter(
        field_name='rating',
        lookup_expr='gte'
    )
    
    # Provider filters
    provider = django_filters.CharFilter(
        field_name='provider__business_name',
        lookup_expr='icontains'
    )
    
    provider_id = django_filters.NumberFilter(
        field_name='provider__id'
    )
    
    provider_location = django_filters.CharFilter(
        field_name='provider__city',
        lookup_expr='icontains'
    )
    
    # Status filters
    status = django_filters.ChoiceFilter(
        field_name='status',
        choices=Package.STATUS_CHOICES
    )
    
    # Availability filters
    is_available = django_filters.BooleanFilter(
        method='filter_is_available'
    )
    
    available_from = django_filters.DateFilter(
        method='filter_available_from'
    )
    
    # Feature filters
    is_featured = django_filters.BooleanFilter(
        field_name='is_featured'
    )
    
    has_discount = django_filters.BooleanFilter(
        method='filter_has_discount'
    )
    
    # Capacity filters
    min_capacity = django_filters.NumberFilter(
        field_name='max_capacity',
        lookup_expr='gte'
    )
    
    available_slots = django_filters.NumberFilter(
        method='filter_available_slots'
    )
    
    # Search filter
    search = django_filters.CharFilter(
        method='filter_search'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('updated_at', 'updated_at'),
            ('name', 'name'),
            ('base_price', 'price'),
            ('start_date', 'start_date'),
            ('end_date', 'end_date'),
            ('duration_days', 'duration'),
            ('rating', 'rating'),
            ('views_count', 'views'),
            ('leads_count', 'leads'),
            ('is_featured', 'featured'),
        )
    )
    
    class Meta:
        model = Package
        fields = [
            'name', 'package_type', 'status', 'is_featured',
            'provider_id', 'is_available'
        ]
    
    def filter_min_price(self, queryset, name, value):
        """Filter packages with minimum price (considering discounts)"""
        if value is not None:
            return queryset.filter(
                models.Q(discounted_price__gte=value) |
                models.Q(discounted_price__isnull=True, base_price__gte=value)
            )
        return queryset
    
    def filter_max_price(self, queryset, name, value):
        """Filter packages with maximum price (considering discounts)"""
        if value is not None:
            return queryset.filter(
                models.Q(discounted_price__lte=value) |
                models.Q(discounted_price__isnull=True, base_price__lte=value)
            )
        return queryset
    
    def filter_is_available(self, queryset, name, value):
        """Filter available packages"""
        if value:
            now = timezone.now().date()
            return queryset.filter(
                status='published',
                is_active=True,
                booking_deadline__gte=now,
                current_bookings__lt=models.F('max_capacity')
            )
        return queryset
    
    def filter_available_from(self, queryset, name, value):
        """Filter packages available from a specific date"""
        if value:
            return queryset.filter(
                booking_deadline__gte=value,
                start_date__gte=value
            )
        return queryset
    
    def filter_has_discount(self, queryset, name, value):
        """Filter packages with discount"""
        if value:
            return queryset.filter(discounted_price__isnull=False)
        else:
            return queryset.filter(discounted_price__isnull=True)
        return queryset
    
    def filter_available_slots(self, queryset, name, value):
        """Filter packages with minimum available slots"""
        if value is not None:
            return queryset.filter(
                max_capacity__gte=models.F('current_bookings') + value
            )
        return queryset
    
    def filter_search(self, queryset, name, value):
        """Search across multiple fields"""
        if value:
            return queryset.filter(
                models.Q(name__icontains=value) |
                models.Q(description__icontains=value) |
                models.Q(provider__business_name__icontains=value) |
                models.Q(provider__city__icontains=value) |
                models.Q(inclusions__title__icontains=value) |
                models.Q(itineraries__title__icontains=value) |
                models.Q(itineraries__description__icontains=value)
            ).distinct()
        return queryset


class PackageAdminFilter(PackageFilter):
    """Extended filter for admin panel"""
    
    # Additional admin filters
    verified_by = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        field_name='verified_by'
    )
    
    verified_date_from = django_filters.DateFilter(
        field_name='verified_at',
        lookup_expr='date__gte'
    )
    
    verified_date_to = django_filters.DateFilter(
        field_name='verified_at',
        lookup_expr='date__lte'
    )
    
    created_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__gte'
    )
    
    created_to = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__lte'
    )
    
    has_rejection_reason = django_filters.BooleanFilter(
        method='filter_has_rejection_reason'
    )
    
    min_views = django_filters.NumberFilter(
        field_name='views_count',
        lookup_expr='gte'
    )
    
    min_leads = django_filters.NumberFilter(
        field_name='leads_count',
        lookup_expr='gte'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set queryset for verified_by field
        from apps.authentication.models import User
        self.filters['verified_by'].queryset = User.objects.filter(
            is_staff=True
        )
    
    def filter_has_rejection_reason(self, queryset, name, value):
        """Filter packages with or without rejection reason"""
        if value:
            return queryset.exclude(rejection_reason='')
        else:
            return queryset.filter(rejection_reason='')
        return queryset