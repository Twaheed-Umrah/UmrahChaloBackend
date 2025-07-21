import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import Lead, LeadDistribution


class LeadFilter(django_filters.FilterSet):
    """
    Filter set for Lead model
    """
    status = django_filters.MultipleChoiceFilter(
        choices=Lead.STATUS_CHOICES,
        widget=django_filters.widgets.CSVWidget
    )
    
    lead_type = django_filters.MultipleChoiceFilter(
        choices=Lead.LEAD_TYPE_CHOICES,
        widget=django_filters.widgets.CSVWidget
    )
    
    # Date filters
    created_after = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__gte'
    )
    
    created_before = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__lte'
    )
    
    preferred_date_from = django_filters.DateFilter(
        field_name='preferred_date',
        lookup_expr='gte'
    )
    
    preferred_date_to = django_filters.DateFilter(
        field_name='preferred_date',
        lookup_expr='lte'
    )
    
    # Location filters
    departure_city = django_filters.CharFilter(
        field_name='departure_city',
        lookup_expr='icontains'
    )
    
    # Budget filters
    budget_min = django_filters.NumberFilter(
        method='filter_budget_min'
    )
    
    budget_max = django_filters.NumberFilter(
        method='filter_budget_max'
    )
    
    # People count filters
    people_count_min = django_filters.NumberFilter(
        field_name='number_of_people',
        lookup_expr='gte'
    )
    
    people_count_max = django_filters.NumberFilter(
        field_name='number_of_people',
        lookup_expr='lte'
    )
    
    # Distribution status
    is_distributed = django_filters.BooleanFilter()
    
    # Expiry filters
    is_expired = django_filters.BooleanFilter(
        method='filter_is_expired'
    )
    
    expires_soon = django_filters.BooleanFilter(
        method='filter_expires_soon'
    )
    
    # Provider filters (for admin)
    provider = django_filters.NumberFilter(
        method='filter_provider'
    )
    
    # Service/Package filters
    service_type = django_filters.CharFilter(
        method='filter_service_type'
    )
    
    package_category = django_filters.CharFilter(
        method='filter_package_category'
    )
    
    # Priority filter
    priority = django_filters.NumberFilter()
    
    priority_min = django_filters.NumberFilter(
        field_name='priority',
        lookup_expr='gte'
    )
    
    # Search filter
    search = django_filters.CharFilter(
        method='filter_search'
    )
    
    class Meta:
        model = Lead
        fields = [
            'status', 'lead_type', 'is_distributed', 'priority',
            'departure_city', 'number_of_people'
        ]
    
    def filter_budget_min(self, queryset, name, value):
        """
        Filter leads with budget greater than or equal to value
        """
        # This is a simplified filter - you might need to parse budget_range
        return queryset.filter(
            budget_range__icontains=str(value)
        )
    
    def filter_budget_max(self, queryset, name, value):
        """
        Filter leads with budget less than or equal to value
        """
        # This is a simplified filter - you might need to parse budget_range
        return queryset.filter(
            budget_range__icontains=str(value)
        )
    
    def filter_is_expired(self, queryset, name, value):
        """
        Filter expired leads
        """
        if value:
            return queryset.filter(
                expires_at__lt=timezone.now()
            )
        return queryset.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now())
        )
    
    def filter_expires_soon(self, queryset, name, value):
        """
        Filter leads expiring in next 7 days
        """
        if value:
            week_from_now = timezone.now() + timezone.timedelta(days=7)
            return queryset.filter(
                expires_at__lte=week_from_now,
                expires_at__gte=timezone.now()
            )
        return queryset
    
    def filter_provider(self, queryset, name, value):
        """
        Filter leads by provider
        """
        return queryset.filter(
            Q(package__provider_id=value) | Q(service__provider_id=value)
        )
    
    def filter_service_type(self, queryset, name, value):
        """
        Filter leads by service type
        """
        return queryset.filter(
            Q(service__service_type=value) |
            Q(selected_services__has_key=value)
        )
    
    def filter_package_category(self, queryset, name, value):
        """
        Filter leads by package category
        """
        return queryset.filter(
            package__category=value
        )
    
    def filter_search(self, queryset, name, value):
        """
        General search filter
        """
        return queryset.filter(
            Q(full_name__icontains=value) |
            Q(email__icontains=value) |
            Q(phone__icontains=value) |
            Q(departure_city__icontains=value) |
            Q(special_requirements__icontains=value) |
            Q(custom_message__icontains=value)
        )


class LeadDistributionFilter(django_filters.FilterSet):
    """
    Filter set for LeadDistribution model
    """
    status = django_filters.MultipleChoiceFilter(
        choices=LeadDistribution.STATUS_CHOICES,
        widget=django_filters.widgets.CSVWidget
    )
    
    # Date filters
    sent_after = django_filters.DateTimeFilter(
        field_name='sent_at',
        lookup_expr='gte'
    )
    
    sent_before = django_filters.DateTimeFilter(
        field_name='sent_at',
        lookup_expr='lte'
    )
    
    viewed_after = django_filters.DateTimeFilter(
        field_name='viewed_at',
        lookup_expr='gte'
    )
    
    viewed_before = django_filters.DateTimeFilter(
        field_name='viewed_at',
        lookup_expr='lte'
    )
    
    responded_after = django_filters.DateTimeFilter(
        field_name='responded_at',
        lookup_expr='gte'
    )
    
    responded_before = django_filters.DateTimeFilter(
        field_name='responded_at',
        lookup_expr='lte'
    )
    
    # Lead filters
    lead_status = django_filters.CharFilter(
        field_name='lead__status'
    )
    
    lead_type = django_filters.CharFilter(
        field_name='lead__lead_type'
    )
    
    # Provider filters
    provider = django_filters.NumberFilter(
        field_name='provider'
    )
    
    # Response filters
    has_response = django_filters.BooleanFilter(
        method='filter_has_response'
    )
    
    quoted_price_min = django_filters.NumberFilter(
        field_name='quoted_price',
        lookup_expr='gte'
    )
    
    quoted_price_max = django_filters.NumberFilter(
        field_name='quoted_price',
        lookup_expr='lte'
    )
    
    # Notification filters
    email_sent = django_filters.BooleanFilter()
    sms_sent = django_filters.BooleanFilter()
    app_notification_sent = django_filters.BooleanFilter()
    
    # Time-based filters
    today = django_filters.BooleanFilter(
        method='filter_today'
    )
    
    this_week = django_filters.BooleanFilter(
        method='filter_this_week'
    )
    
    this_month = django_filters.BooleanFilter(
        method='filter_this_month'
    )
    
    class Meta:
        model = LeadDistribution
        fields = [
            'status', 'provider', 'email_sent', 'sms_sent',
            'app_notification_sent'
        ]
    
    def filter_has_response(self, queryset, name, value):
        """
        Filter distributions with response
        """
        if value:
            return queryset.filter(
                Q(response_message__isnull=False) |
                Q(quoted_price__isnull=False)
            )
        return queryset.filter(
            response_message__isnull=True,
            quoted_price__isnull=True
        )
    
    def filter_today(self, queryset, name, value):
        """
        Filter distributions from today
        """
        if value:
            today = timezone.now().date()
            return queryset.filter(sent_at__date=today)
        return queryset
    
    def filter_this_week(self, queryset, name, value):
        """
        Filter distributions from this week
        """
        if value:
            week_ago = timezone.now() - timezone.timedelta(days=7)
            return queryset.filter(sent_at__gte=week_ago)
        return queryset
    
    def filter_this_month(self, queryset, name, value):
        """
        Filter distributions from this month
        """
        if value:
            month_ago = timezone.now() - timezone.timedelta(days=30)
            return queryset.filter(sent_at__gte=month_ago)
        return queryset