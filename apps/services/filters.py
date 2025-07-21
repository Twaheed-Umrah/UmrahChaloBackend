import django_filters
from django.db.models import Q, Avg, F
from django.utils import timezone
from django.apps import apps

class ServiceFilter(django_filters.FilterSet):
    """
    Filter class for Service model with comprehensive filtering options
    """
    
    # Text search
    search = django_filters.CharFilter(method='filter_search', label='Search')
    
    # Service type filter
    service_type = django_filters.ChoiceFilter(
        method='filter_service_type',
        label='Service Type'
    )
    
    # Category filter
    category = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        field_name='category',
        label='Category'
    )
    
    # Location filters
    city = django_filters.CharFilter(
        field_name='city',
        lookup_expr='icontains',
        label='City'
    )
    
    state = django_filters.CharFilter(
        field_name='state',
        lookup_expr='icontains',
        label='State'
    )
    
    country = django_filters.CharFilter(
        field_name='country',
        lookup_expr='icontains',
        label='Country'
    )
    
    # Price filters
    min_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='gte',
        label='Minimum Price'
    )
    
    max_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='lte',
        label='Maximum Price'
    )
    
    price_range = django_filters.RangeFilter(
        field_name='price',
        label='Price Range'
    )
    
    # Date filters
    available_from = django_filters.DateFilter(
        method='filter_available_from',
        label='Available From'
    )
    
    available_to = django_filters.DateFilter(
        method='filter_available_to',
        label='Available To'
    )
    
    date_range = django_filters.DateFromToRangeFilter(
        method='filter_date_range',
        label='Date Range'
    )
    
    # Duration filters
    min_duration_days = django_filters.NumberFilter(
        field_name='duration_in_days',
        lookup_expr='gte',
        label='Minimum Duration (Days)'
    )
    
    max_duration_days = django_filters.NumberFilter(
        field_name='duration_in_days',
        lookup_expr='lte',
        label='Maximum Duration (Days)'
    )
    
    # Air ticket specific filters
    departure_city = django_filters.CharFilter(
        field_name='departure_city',
        lookup_expr='icontains',
        label='Departure City'
    )
    
    arrival_city = django_filters.CharFilter(
        field_name='arrival_city',
        lookup_expr='icontains',
        label='Arrival City'
    )
    
    departure_date = django_filters.DateFilter(
        field_name='departure_date',
        label='Departure Date'
    )
    
    return_date = django_filters.DateFilter(
        field_name='return_date',
        label='Return Date'
    )
    
    airline = django_filters.CharFilter(
        field_name='airline',
        lookup_expr='icontains',
        label='Airline'
    )
    
    # Provider filters
    provider = django_filters.NumberFilter(
        field_name='provider__id',
        label='Provider ID'
    )
    
    provider_name = django_filters.CharFilter(
        method='filter_provider_name',
        label='Provider Name'
    )
    
    # Status filters
    status = django_filters.ChoiceFilter(
        method='filter_status',
        label='Status'
    )
    
    # Boolean filters
    is_featured = django_filters.BooleanFilter(
        field_name='is_featured',
        label='Featured'
    )
    
    is_popular = django_filters.BooleanFilter(
        field_name='is_popular',
        label='Popular'
    )
    
    is_premium = django_filters.BooleanFilter(
        field_name='is_premium',
        label='Premium'
    )
    
    is_always_available = django_filters.BooleanFilter(
        field_name='is_always_available',
        label='Always Available'
    )
    
    has_discount = django_filters.BooleanFilter(
        method='filter_has_discount',
        label='Has Discount'
    )
    
    # Rating filter
    min_rating = django_filters.NumberFilter(
        method='filter_min_rating',
        label='Minimum Rating'
    )
    
    # View count filters
    min_views = django_filters.NumberFilter(
        field_name='views_count',
        lookup_expr='gte',
        label='Minimum Views'
    )
    
    # Created date filters
    created_after = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__gte',
        label='Created After'
    )
    
    created_before = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__lte',
        label='Created Before'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('updated_at', 'updated_at'),
            ('price', 'price'),
            ('title', 'title'),
            ('views_count', 'views_count'),
            ('leads_count', 'leads_count'),
            ('departure_date', 'departure_date'),
        ),
        field_labels={
            'created_at': 'Created Date',
            'updated_at': 'Updated Date',
            'price': 'Price',
            'title': 'Title',
            'views_count': 'Views Count',
            'leads_count': 'Leads Count',
            'departure_date': 'Departure Date',
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamically set querysets for ModelChoiceFilter fields
        try:
            ServiceCategory = apps.get_model('services', 'ServiceCategory')
            self.filters['category'].queryset = ServiceCategory.objects.filter(is_active=True)
        except LookupError:
            # Handle case where model is not yet loaded
            pass
        
        # Set choices for ChoiceFilter fields
        try:
            from .models import ServiceType, ServiceStatus
            self.filters['service_type'].extra['choices'] = ServiceType.choices
            self.filters['status'].extra['choices'] = ServiceStatus.choices
        except ImportError:
            pass
    
    class Meta:
        model = None  # Will be set dynamically
        fields = {
            'service_type': ['exact'],
            'category': ['exact'],
            'city': ['exact', 'icontains'],
            'state': ['exact', 'icontains'],
            'price': ['exact', 'gte', 'lte'],
            'duration_in_days': ['exact', 'gte', 'lte'],
            'departure_date': ['exact', 'gte', 'lte'],
            'return_date': ['exact', 'gte', 'lte'],
            'status': ['exact'],
            'is_featured': ['exact'],
            'is_popular': ['exact'],
            'is_premium': ['exact'],
            'created_at': ['exact', 'gte', 'lte', 'date'],
            'updated_at': ['exact', 'gte', 'lte', 'date'],
        }
    
    def filter_service_type(self, queryset, name, value):
        """Filter by service type"""
        if value:
            return queryset.filter(service_type=value)
        return queryset
    
    def filter_status(self, queryset, name, value):
        """Filter by status"""
        if value:
            return queryset.filter(status=value)
        return queryset
    
    def filter_search(self, queryset, name, value):
        """
        Search across multiple fields
        """
        if value:
            return queryset.filter(
                Q(title__icontains=value) |
                Q(description__icontains=value) |
                Q(short_description__icontains=value) |
                Q(city__icontains=value) |
                Q(state__icontains=value) |
                Q(provider__company_name__icontains=value) |
                Q(provider__user__first_name__icontains=value) |
                Q(provider__user__last_name__icontains=value) |
                Q(features__icontains=value) |
                Q(inclusions__icontains=value)
            ).distinct()
        return queryset
    
    def filter_provider_name(self, queryset, name, value):
        """
        Filter by provider name (company name or user name)
        """
        if value:
            return queryset.filter(
                Q(provider__company_name__icontains=value) |
                Q(provider__user__first_name__icontains=value) |
                Q(provider__user__last_name__icontains=value)
            ).distinct()
        return queryset
    
    def filter_available_from(self, queryset, name, value):
        """
        Filter services available from a specific date
        """
        if value:
            return queryset.filter(
                Q(is_always_available=True) |
                Q(available_from__lte=value)
            )
        return queryset
    
    def filter_available_to(self, queryset, name, value):
        """
        Filter services available to a specific date
        """
        if value:
            return queryset.filter(
                Q(is_always_available=True) |
                Q(available_to__gte=value)
            )
        return queryset
    
    def filter_date_range(self, queryset, name, value):
        """
        Filter services available in a date range
        """
        if value:
            start_date = value.start
            end_date = value.stop
            
            if start_date and end_date:
                return queryset.filter(
                    Q(is_always_available=True) |
                    Q(available_from__lte=end_date, available_to__gte=start_date)
                )
            elif start_date:
                return self.filter_available_from(queryset, name, start_date)
            elif end_date:
                return self.filter_available_to(queryset, name, end_date)
        return queryset
    
    def filter_has_discount(self, queryset, name, value):
        """
        Filter services that have a discount
        """
        if value:
            return queryset.filter(
                original_price__gt=F('price')
            )
        return queryset
    
    def filter_min_rating(self, queryset, name, value):
        """
        Filter services with minimum rating
        """
        if value:
            return queryset.annotate(
                avg_rating=Avg('reviews__rating')
            ).filter(avg_rating__gte=value)
        return queryset
    
    @property
    def qs(self):
        """
        Override queryset to add default filters for published services
        """
        queryset = super().qs
        
        # Get the request from the parent filter
        request = getattr(self, 'request', None)
        if request and hasattr(request, 'user'):
            user = request.user
            
            # If user is not admin/provider, only show published services
            if hasattr(user, 'profile'):
                if user.profile.role not in ['admin', 'super_admin', 'provider']:
                    try:
                        from .models import ServiceStatus
                        queryset = queryset.filter(status=ServiceStatus.PUBLISHED)
                    except ImportError:
                        pass
                elif user.profile.role == 'provider':
                    # Providers can see their own services and published services from others
                    try:
                        from .models import ServiceStatus
                        queryset = queryset.filter(
                            Q(provider=user.profile) | Q(status=ServiceStatus.PUBLISHED)
                        )
                    except ImportError:
                        pass
            else:
                # Unauthenticated users can only see published services
                try:
                    from .models import ServiceStatus
                    queryset = queryset.filter(status=ServiceStatus.PUBLISHED)
                except ImportError:
                    pass
        
        return queryset


# Create a factory function to properly initialize filters
def create_service_filter():
    """Factory function to create ServiceFilter with proper model"""
    try:
        Service = apps.get_model('services', 'Service')
        ServiceFilter._meta.model = Service
        return ServiceFilter
    except LookupError:
        return ServiceFilter


class ServiceAdminFilter(ServiceFilter):
    """
    Extended filter for admin users with additional filters
    """
    
    # Admin specific filters
    verified_by = django_filters.NumberFilter(
        field_name='verified_by__id',
        label='Verified By'
    )
    
    verified_date = django_filters.DateFilter(
        field_name='verified_at',
        lookup_expr='date',
        label='Verified Date'
    )
    
    has_rejection_reason = django_filters.BooleanFilter(
        method='filter_has_rejection_reason',
        label='Has Rejection Reason'
    )
    
    subscription_status = django_filters.ChoiceFilter(
        method='filter_subscription_status',
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('expired', 'Expired'),
        ],
        label='Provider Subscription Status'
    )
    
    def filter_has_rejection_reason(self, queryset, name, value):
        """
        Filter services with/without rejection reason
        """
        if value:
            return queryset.exclude(rejection_reason='')
        else:
            return queryset.filter(rejection_reason='')
    
    def filter_subscription_status(self, queryset, name, value):
        """
        Filter by provider subscription status
        """
        if value == 'active':
            return queryset.filter(
                provider__subscriptions__is_active=True
            )
        elif value == 'inactive':
            return queryset.exclude(
                provider__subscriptions__is_active=True
            )
        elif value == 'expired':
            return queryset.filter(
                provider__subscriptions__is_active=False,
                provider__subscriptions__end_date__lt=timezone.now()
            )
        return queryset


class ServiceAnalyticsFilter(django_filters.FilterSet):
    """
    Filter for service analytics and reporting
    """
    
    date_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__gte',
        label='From Date'
    )
    
    date_to = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__lte',
        label='To Date'
    )
    
    # Service type analytics
    service_type = django_filters.ChoiceFilter(
        method='filter_service_type',
        label='Service Type'
    )
    
    # Category analytics
    category = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        field_name='category',
        label='Category'
    )
    
    # Location analytics
    city = django_filters.CharFilter(
        field_name='city',
        lookup_expr='icontains',
        label='City'
    )
    
    state = django_filters.CharFilter(
        field_name='state',
        lookup_expr='icontains',
        label='State'
    )
    
    # Provider analytics
    provider = django_filters.NumberFilter(
        field_name='provider__id',
        label='Provider ID'
    )
    
    # Status analytics
    status = django_filters.ChoiceFilter(
        method='filter_status',
        label='Status'
    )
    
    # Performance filters
    min_views = django_filters.NumberFilter(
        field_name='views_count',
        lookup_expr='gte',
        label='Minimum Views'
    )
    
    max_views = django_filters.NumberFilter(
        field_name='views_count',
        lookup_expr='lte',
        label='Maximum Views'
    )
    
    min_leads = django_filters.NumberFilter(
        field_name='leads_count',
        lookup_expr='gte',
        label='Minimum Leads'
    )
    
    max_leads = django_filters.NumberFilter(
        field_name='leads_count',
        lookup_expr='lte',
        label='Maximum Leads'
    )
    
    # Price range for analytics
    min_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='gte',
        label='Minimum Price'
    )
    
    max_price = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='lte',
        label='Maximum Price'
    )
    
    # Boolean filters for analytics
    is_featured = django_filters.BooleanFilter(
        field_name='is_featured',
        label='Featured Services'
    )
    
    is_popular = django_filters.BooleanFilter(
        field_name='is_popular',
        label='Popular Services'
    )
    
    is_premium = django_filters.BooleanFilter(
        field_name='is_premium',
        label='Premium Services'
    )
    
    has_discount = django_filters.BooleanFilter(
        method='filter_has_discount',
        label='Services with Discount'
    )
    
    # Rating analytics
    min_rating = django_filters.NumberFilter(
        method='filter_min_rating',
        label='Minimum Rating'
    )
    
    # Ordering for analytics
    ordering = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('updated_at', 'updated_at'),
            ('price', 'price'),
            ('views_count', 'views_count'),
            ('leads_count', 'leads_count'),
            ('title', 'title'),
        ),
        field_labels={
            'created_at': 'Created Date',
            'updated_at': 'Updated Date',
            'price': 'Price',
            'views_count': 'Views Count',
            'leads_count': 'Leads Count',
            'title': 'Title',
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamically set querysets for ModelChoiceFilter fields
        try:
            ServiceCategory = apps.get_model('services', 'ServiceCategory')
            self.filters['category'].queryset = ServiceCategory.objects.filter(is_active=True)
        except LookupError:
            pass
        
        # Set choices for ChoiceFilter fields
        try:
            from .models import ServiceType, ServiceStatus
            self.filters['service_type'].extra['choices'] = ServiceType.choices
            self.filters['status'].extra['choices'] = ServiceStatus.choices
        except ImportError:
            pass
    
    class Meta:
        model = None  # Will be set dynamically
        fields = {
            'service_type': ['exact'],
            'category': ['exact'],
            'city': ['exact', 'icontains'],
            'state': ['exact', 'icontains'],
            'status': ['exact'],
            'provider': ['exact'],
            'price': ['exact', 'gte', 'lte'],
            'views_count': ['exact', 'gte', 'lte'],
            'leads_count': ['exact', 'gte', 'lte'],
            'is_featured': ['exact'],
            'is_popular': ['exact'],
            'is_premium': ['exact'],
            'created_at': ['exact', 'gte', 'lte', 'date'],
            'updated_at': ['exact', 'gte', 'lte', 'date'],
        }
    
    def filter_service_type(self, queryset, name, value):
        """Filter by service type"""
        if value:
            return queryset.filter(service_type=value)
        return queryset
    
    def filter_status(self, queryset, name, value):
        """Filter by status"""
        if value:
            return queryset.filter(status=value)
        return queryset
    
    def filter_has_discount(self, queryset, name, value):
        """
        Filter services that have a discount
        """
        if value:
            return queryset.filter(
                original_price__gt=F('price')
            )
        return queryset
    
    def filter_min_rating(self, queryset, name, value):
        """
        Filter services with minimum rating
        """
        if value:
            return queryset.annotate(
                avg_rating=Avg('reviews__rating')
            ).filter(avg_rating__gte=value)
        return queryset


# Factory function for ServiceAnalyticsFilter
def create_service_analytics_filter():
    """Factory function to create ServiceAnalyticsFilter with proper model"""
    try:
        Service = apps.get_model('services', 'Service')
        ServiceAnalyticsFilter._meta.model = Service
        return ServiceAnalyticsFilter
    except LookupError:
        return ServiceAnalyticsFilter


class ServiceCategoryFilter(django_filters.FilterSet):
    """
    Filter for Service Categories
    """
    
    # Name search
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Category Name'
    )
    
    # Description search
    description = django_filters.CharFilter(
        field_name='description',
        lookup_expr='icontains',
        label='Description'
    )
    
    # Active status
    is_active = django_filters.BooleanFilter(
        field_name='is_active',
        label='Active'
    )
    
    # Services count filter
    min_services = django_filters.NumberFilter(
        method='filter_min_services',
        label='Minimum Services Count'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('display_order', 'display_order'),
            ('created_at', 'created_at'),
        ),
        field_labels={
            'name': 'Name',
            'display_order': 'Display Order',
            'created_at': 'Created Date',
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set model dynamically
        try:
            ServiceCategory = apps.get_model('services', 'ServiceCategory')
            self._meta.model = ServiceCategory
        except LookupError:
            pass
    
    class Meta:
        model = None  # Will be set dynamically
        fields = {
            'name': ['exact', 'icontains'],
            'is_active': ['exact'],
            'display_order': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte', 'date'],
        }
    
    def filter_min_services(self, queryset, name, value):
        """
        Filter categories with minimum number of services
        """
        if value:
            from django.db.models import Count
            return queryset.annotate(
                services_count=Count('services')
            ).filter(services_count__gte=value)
        return queryset


class ServiceAvailabilityFilter(django_filters.FilterSet):
    """
    Filter for Service Availability
    """
    
    # Service filter
    service = django_filters.NumberFilter(
        field_name='service__id',
        label='Service ID'
    )
    
    # Date range filters
    date_from = django_filters.DateFilter(
        field_name='date',
        lookup_expr='gte',
        label='From Date'
    )
    
    date_to = django_filters.DateFilter(
        field_name='date',
        lookup_expr='lte',
        label='To Date'
    )
    
    # Availability status
    is_available = django_filters.BooleanFilter(
        field_name='is_available',
        label='Available'
    )
    
    # Capacity filters
    min_capacity = django_filters.NumberFilter(
        field_name='capacity',
        lookup_expr='gte',
        label='Minimum Capacity'
    )
    
    max_capacity = django_filters.NumberFilter(
        field_name='capacity',
        lookup_expr='lte',
        label='Maximum Capacity'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('date', 'date'),
            ('capacity', 'capacity'),
            ('created_at', 'created_at'),
        ),
        field_labels={
            'date': 'Date',
            'capacity': 'Capacity',
            'created_at': 'Created Date',
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set model dynamically
        try:
            ServiceAvailability = apps.get_model('services', 'ServiceAvailability')
            self._meta.model = ServiceAvailability
        except LookupError:
            pass
    
    class Meta:
        model = None  # Will be set dynamically
        fields = {
            'service': ['exact'],
            'date': ['exact', 'gte', 'lte'],
            'is_available': ['exact'],
            'capacity': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte', 'date'],
        }


class ServiceFAQFilter(django_filters.FilterSet):
    """
    Filter for Service FAQs
    """
    
    # Service filter
    service = django_filters.NumberFilter(
        field_name='service__id',
        label='Service ID'
    )
    
    # Question search
    question = django_filters.CharFilter(
        field_name='question',
        lookup_expr='icontains',
        label='Question'
    )
    
    # Answer search
    answer = django_filters.CharFilter(
        field_name='answer',
        lookup_expr='icontains',
        label='Answer'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('display_order', 'display_order'),
            ('created_at', 'created_at'),
        ),
        field_labels={
            'display_order': 'Display Order',
            'created_at': 'Created Date',
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set model dynamically
        try:
            ServiceFAQ = apps.get_model('services', 'ServiceFAQ')
            self._meta.model = ServiceFAQ
        except LookupError:
            pass
    
    class Meta:
        model = None  # Will be set dynamically
        fields = {
            'service': ['exact'],
            'question': ['icontains'],
            'answer': ['icontains'],
            'display_order': ['exact', 'gte', 'lte'],
            'created_at': ['exact', 'gte', 'lte', 'date'],
        }


class ServiceViewFilter(django_filters.FilterSet):
    """
    Filter for Service Views (Analytics)
    """
    
    # Service filter
    service = django_filters.NumberFilter(
        field_name='service__id',
        label='Service ID'
    )
    
    # User filter
    user = django_filters.NumberFilter(
        field_name='user__id',
        label='User ID'
    )
    
    # Date range filters
    viewed_from = django_filters.DateTimeFilter(
        field_name='viewed_at',
        lookup_expr='gte',
        label='Viewed From'
    )
    
    viewed_to = django_filters.DateTimeFilter(
        field_name='viewed_at',
        lookup_expr='lte',
        label='Viewed To'
    )
    
    # IP address filter
    ip_address = django_filters.CharFilter(
        field_name='ip_address',
        lookup_expr='exact',
        label='IP Address'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('viewed_at', 'viewed_at'),
            ('service__title', 'service_title'),
        ),
        field_labels={
            'viewed_at': 'Viewed Date',
            'service__title': 'Service Title',
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set model dynamically
        try:
            ServiceView = apps.get_model('services', 'ServiceView')
            self._meta.model = ServiceView
        except LookupError:
            pass
    
    class Meta:
        model = None  # Will be set dynamically
        fields = {
            'service': ['exact'],
            'user': ['exact'],
            'ip_address': ['exact'],
            'viewed_at': ['exact', 'gte', 'lte'],
        }