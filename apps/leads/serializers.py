from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from apps.authentication.serializers import UserProfileSerializer, ServiceProviderProfileSerializer
from apps.services.serializers import ServiceListSerializer
from apps.packages.serializers import PackageListSerializer
from apps.authentication.models import ServiceProviderProfile
from .models import Lead, LeadDistribution, LeadInteraction, LeadNote


class LeadSerializer(serializers.ModelSerializer):
    """
    Serializer for Lead model with auto-distribution functionality
    """
    user_details = UserProfileSerializer(source='user', read_only=True)
    package_details = PackageListSerializer(source='package', read_only=True)
    service_details = ServiceListSerializer(source='service', read_only=True)
    target_providers = serializers.ReadOnlyField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'user', 'user_details', 'package', 'package_details', 
            'service', 'service_details', 'lead_type', 'status',
            'full_name', 'email', 'phone', 'preferred_date', 
            'number_of_people', 'budget_range', 'departure_city',
            'special_requirements', 'selected_services', 'is_distributed',
            'distribution_date', 'expires_at', 'source', 'priority', 'target_providers', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'is_distributed', 'distribution_date', 'created_at', 'updated_at']
    
    def validate(self, data):
        """
        Custom validation for Lead
        """
        # Either package or service must be provided for non-custom leads
        if data.get('lead_type') != 'custom':
            if not data.get('package') and not data.get('service'):
                raise serializers.ValidationError(
                    "Either package or service must be provided for non-custom leads"
                )
            
            # Both package and service cannot be provided
            if data.get('package') and data.get('service'):
                raise serializers.ValidationError(
                    "Both package and service cannot be provided"
                )
        
        # Validate preferred date
        if data.get('preferred_date') and data['preferred_date'] < timezone.now().date():
            raise serializers.ValidationError(
                "Preferred date cannot be in the past"
            )
        
        # Validate number of people
        if data.get('number_of_people', 1) < 1:
            raise serializers.ValidationError(
                "Number of people must be at least 1"
            )
        
        return data
    
    def get_target_business_types(self, lead):
        """
        Determine target business types based on lead type and content
        """
        target_types = []
        
        if lead.lead_type == 'package':
            if lead.package:
                # Get business type from package provider
                target_types = [lead.package.provider.business_type]
            else:
                # Default package-related business types
                target_types = ['umrah_packages', 'hajj_package', 'agency']
        
        elif lead.lead_type == 'service':
            if lead.service:
                # Get business type from service provider
                target_types = [lead.service.provider.business_type]
            else:
                # Default service-related business types
                target_types = ['agency', 'individual', 'company']
        
        elif lead.lead_type == 'custom':
            # For custom leads, determine based on selected services or requirements
            custom_types = []
            
            # Check selected services
            if lead.selected_services:
                service_keywords = str(lead.selected_services).lower()
                if 'visa' in service_keywords:
                    custom_types.append('visa')
                if 'hotel' in service_keywords:
                    custom_types.append('hotels')
                if 'transport' in service_keywords:
                    custom_types.append('transport')
                if 'food' in service_keywords:
                    custom_types.append('food')
                if 'umrah' in service_keywords:
                    custom_types.extend(['umrah_packages', 'umrah_guide', 'umrah_kit'])
                if 'hajj' in service_keywords:
                    custom_types.append('hajj_package')
                if 'ticket' in service_keywords or 'flight' in service_keywords:
                    custom_types.append('air_ticket_group_fare_umrah')
            
            # Check special requirements and custom message
            requirements_text = f"{lead.special_requirements or ''}".lower()
            if 'visa' in requirements_text:
                custom_types.append('visa')
            if 'hotel' in requirements_text:
                custom_types.append('hotels')
            if 'transport' in requirements_text:
                custom_types.append('transport')
            if 'umrah' in requirements_text:
                custom_types.extend(['umrah_packages', 'umrah_guide'])
            if 'hajj' in requirements_text:
                custom_types.append('hajj_package')
            
            target_types = list(set(custom_types)) if custom_types else ['agency', 'company']
        
        # Always include 'agency' as they can handle most requests
        if 'agency' not in target_types:
            target_types.append('agency')
        
        return target_types
    
    def distribute_lead(self, lead):
        """
        Automatically distribute lead to relevant service providers based on business_type
        """
        target_business_types = self.get_target_business_types(lead)
        
        # Get verified and active service providers with matching business types
        target_providers = ServiceProviderProfile.objects.filter(
            business_type__in=target_business_types,
            verification_status='verified',
            is_active=True
        ).exclude(
            # Exclude providers who already received this lead
            id__in=LeadDistribution.objects.filter(lead=lead).values_list('provider_id', flat=True)
        ).order_by('-is_featured', '-average_rating', '-total_bookings')
        
        # Limit to top providers (can be configured)
        max_providers = 10  # You can make this configurable
        target_providers = target_providers[:max_providers]
        
        # Create lead distributions
        distributions = []
        for provider in target_providers:
            distribution = LeadDistribution.objects.create(
                lead=lead,
                provider=provider,
                status='sent'
            )
            distributions.append(distribution)
        
        # Update lead status
        if distributions:
            lead.is_distributed = True
            lead.distribution_date = timezone.now()
            lead.save()
        
        return distributions
    
    def create(self, validated_data):
        """
        Create a new lead and automatically distribute it
        """
        with transaction.atomic():
            validated_data['user'] = self.context['request'].user
            lead = super().create(validated_data)
            
            # Auto-distribute the lead
            self.distribute_lead(lead)
            
            return lead


class LeadCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating leads (minimal fields) with auto-distribution
    """
    class Meta:
        model = Lead
        fields = [
            'package', 'service', 'lead_type', 'full_name', 'email', 'phone',
            'preferred_date', 'number_of_people', 'budget_range', 'departure_city',
             'special_requirements',
            'selected_services', 'source', 'priority'
        ]
    
    def validate(self, data):
        """
        Custom validation for Lead creation
        """
        # Either package or service must be provided for non-custom leads
        if data.get('lead_type') != 'custom':
            if not data.get('package') and not data.get('service'):
                raise serializers.ValidationError(
                    "Either package or service must be provided for non-custom leads"
                )
            
            # Both package and service cannot be provided
            if data.get('package') and data.get('service'):
                raise serializers.ValidationError(
                    "Both package and service cannot be provided"
                )
        
        # Validate preferred date
        if data.get('preferred_date') and data['preferred_date'] < timezone.now().date():
            raise serializers.ValidationError(
                "Preferred date cannot be in the future"
            )
        
        return data
    
    def get_target_business_types(self, lead):
        """
        Determine target business types based on lead type and content
        """
        target_types = []
        
        if lead.lead_type == 'package':
            if lead.package:
                # Get business type from package provider
                target_types = [lead.package.provider.business_type]
            else:
                # Default package-related business types
                target_types = ['umrah_packages', 'hajj_package', 'agency']
        
        elif lead.lead_type == 'service':
            if lead.service:
                # Get business type from service provider
                target_types = [lead.service.provider.business_type]
            else:
                # Default service-related business types
                target_types = ['agency', 'individual', 'company']
        
        elif lead.lead_type == 'custom':
            # For custom leads, determine based on selected services or requirements
            custom_types = []
            
            # Check selected services
            if lead.selected_services:
                service_keywords = str(lead.selected_services).lower()
                if 'visa' in service_keywords:
                    custom_types.append('visa')
                if 'hotel' in service_keywords:
                    custom_types.append('hotels')
                if 'transport' in service_keywords:
                    custom_types.append('transport')
                if 'food' in service_keywords:
                    custom_types.append('food')
                if 'laundry' in service_keywords:
                    custom_types.append('laundry')
                if 'umrah' in service_keywords:
                    custom_types.extend(['umrah_packages', 'umrah_guide', 'umrah_kit'])
                if 'hajj' in service_keywords:
                    custom_types.append('hajj_package')
                if 'ticket' in service_keywords or 'flight' in service_keywords:
                    custom_types.append('air_ticket_group_fare_umrah')
                if 'water' in service_keywords or 'zam' in service_keywords:
                    custom_types.append('jam_jam_water')
            
            # Check special requirements and custom message
            requirements_text = f"{lead.special_requirements or ''}".lower()
            if 'visa' in requirements_text:
                custom_types.append('visa')
            if 'hotel' in requirements_text:
                custom_types.append('hotels')
            if 'transport' in requirements_text or 'taxi' in requirements_text:
                custom_types.append('transport')
            if 'umrah' in requirements_text:
                custom_types.extend(['umrah_packages', 'umrah_guide'])
            if 'hajj' in requirements_text:
                custom_types.append('hajj_package')
            if 'food' in requirements_text or 'meal' in requirements_text:
                custom_types.append('food')
            
            target_types = list(set(custom_types)) if custom_types else ['agency', 'company']
        
        # Always include 'agency' as they can handle most requests
        if 'agency' not in target_types:
            target_types.append('agency')
        
        return target_types
    
    def distribute_lead(self, lead):
        """
        Automatically distribute lead to relevant service providers based on business_type
        """
        target_business_types = self.get_target_business_types(lead)
        
        # Get verified and active service providers with matching business types
        target_providers = ServiceProviderProfile.objects.filter(
            business_type__in=target_business_types,
            verification_status='verified',
            is_active=True
        ).exclude(
            # Exclude providers who already received this lead
            id__in=LeadDistribution.objects.filter(lead=lead).values_list('provider_id', flat=True)
        ).order_by('-is_featured', '-average_rating', '-total_bookings')
        
        # Limit to top providers (can be configured)
        max_providers = 10  # You can make this configurable
        target_providers = target_providers[:max_providers]
        
        # Create lead distributions
        distributions = []
        for provider in target_providers:
            distribution = LeadDistribution.objects.create(
                lead=lead,
                provider=provider,
                status='sent'
            )
            distributions.append(distribution)
        
        # Update lead status
        if distributions:
            lead.is_distributed = True
            lead.distribution_date = timezone.now()
            lead.save()
        
        return distributions
    
    def create(self, validated_data):
        """
        Create a new lead and automatically distribute it
        """
        with transaction.atomic():
            validated_data['user'] = self.context['request'].user
            lead = super().create(validated_data)
            
            # Auto-distribute the lead
            self.distribute_lead(lead)
            
            return lead


class LeadDistributionSerializer(serializers.ModelSerializer):
    """
    Serializer for LeadDistribution model
    """
    lead_details = LeadSerializer(source='lead', read_only=True)
    provider_details = ServiceProviderProfileSerializer(source='provider', read_only=True)
    
    class Meta:
        model = LeadDistribution
        fields = [
            'id', 'lead', 'lead_details', 'provider', 'provider_details',
            'status', 'sent_at', 'viewed_at', 'responded_at',
            'response_message', 'quoted_price',  'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'sent_at', 'viewed_at', 'responded_at', 'created_at', 'updated_at'
        ]


class LeadDistributionResponseSerializer(serializers.ModelSerializer):
    """
    Serializer for provider response to lead
    """
    class Meta:
        model = LeadDistribution
        fields = ['response_message', 'quoted_price']
    
    def validate_quoted_price(self, value):
        """
        Validate quoted price
        """
        if value is not None and value <= 0:
            raise serializers.ValidationError("Quoted price must be greater than 0")
        return value
    
    def update(self, instance, validated_data):
        """
        Update lead distribution with response
        """
        instance.mark_as_responded(
            message=validated_data.get('response_message'),
            quoted_price=validated_data.get('quoted_price')
        )
        return instance


class LeadInteractionSerializer(serializers.ModelSerializer):
    """
    Serializer for LeadInteraction model
    """
    lead_details = LeadSerializer(source='lead', read_only=True)
    provider_details = ServiceProviderProfileSerializer(source='provider', read_only=True)
    
    class Meta:
        model = LeadInteraction
        fields = [
            'id', 'lead', 'lead_details', 'provider', 'provider_details',
            'interaction_type', 'notes', 'interaction_date', 'follow_up_date',
            'follow_up_notes', 'is_successful', 'outcome_notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'provider', 'created_at', 'updated_at']
    
    def validate_interaction_date(self, value):
        """
        Validate interaction date
        """
        if value > timezone.now():
            raise serializers.ValidationError("Interaction date cannot be in the future")
        return value
    
    def validate_follow_up_date(self, value):
        """
        Validate follow-up date
        """
        if value and value < timezone.now():
            raise serializers.ValidationError("Follow-up date cannot be in the past")
        return value
    
    def create(self, validated_data):
        """
        Create interaction and set provider from request
        """
        validated_data['provider'] = self.context['request'].user.service_provider_profile
        return super().create(validated_data)


class LeadNoteSerializer(serializers.ModelSerializer):
    """
    Serializer for LeadNote model
    """
    provider_details = ServiceProviderProfileSerializer(source='provider', read_only=True)
    
    class Meta:
        model = LeadNote
        fields = [
            'id', 'lead', 'provider', 'provider_details', 'note', 'is_private',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'provider', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """
        Create note and set provider from request
        """
        validated_data['provider'] = self.context['request'].user.service_provider_profile
        return super().create(validated_data)


class LeadManualDistributionSerializer(serializers.Serializer):
    """
    Serializer for manual lead distribution by superadmin
    """
    lead_id = serializers.IntegerField()
    business_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        help_text="List of business types to target. If not provided, auto-determined based on lead content."
    )
    provider_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Specific provider IDs to distribute to. Takes precedence over business_types."
    )
    max_providers = serializers.IntegerField(default=10, min_value=1, max_value=50)
    
    def validate_lead_id(self, value):
        """
        Validate lead exists
        """
        try:
            lead = Lead.objects.get(id=value)
        except Lead.DoesNotExist:
            raise serializers.ValidationError("Lead not found")
        return value
    
    def validate_business_types(self, value):
        """
        Validate business types
        """
        valid_types = [choice[0] for choice in ServiceProviderProfile.BUSINESS_TYPES]
        for business_type in value:
            if business_type not in valid_types:
                raise serializers.ValidationError(f"Invalid business type: {business_type}")
        return value
    
    def validate_provider_ids(self, value):
        """
        Validate provider IDs exist and are active
        """
        existing_ids = ServiceProviderProfile.objects.filter(
            id__in=value,
            verification_status='verified',
            is_active=True
        ).values_list('id', flat=True)
        
        missing_ids = set(value) - set(existing_ids)
        if missing_ids:
            raise serializers.ValidationError(f"Invalid or inactive provider IDs: {list(missing_ids)}")
        return value
    
    def distribute_lead(self):
        """
        Perform manual lead distribution
        """
        lead_id = self.validated_data['lead_id']
        business_types = self.validated_data.get('business_types')
        provider_ids = self.validated_data.get('provider_ids')
        max_providers = self.validated_data['max_providers']
        
        lead = Lead.objects.get(id=lead_id)
        
        with transaction.atomic():
            target_providers = None
            
            if provider_ids:
                # Use specific provider IDs
                target_providers = ServiceProviderProfile.objects.filter(
                    id__in=provider_ids,
                    verification_status='verified',
                    is_active=True
                )
            elif business_types:
                # Use specified business types
                target_providers = ServiceProviderProfile.objects.filter(
                    business_type__in=business_types,
                    verification_status='verified',
                    is_active=True
                )
            else:
                # Auto-determine business types based on lead content
                serializer = LeadCreateSerializer()
                target_business_types = serializer.get_target_business_types(lead)
                target_providers = ServiceProviderProfile.objects.filter(
                    business_type__in=target_business_types,
                    verification_status='verified',
                    is_active=True
                )
            
            # Exclude providers who already received this lead
            target_providers = target_providers.exclude(
                id__in=LeadDistribution.objects.filter(lead=lead).values_list('provider_id', flat=True)
            ).order_by('-is_featured', '-average_rating', '-total_bookings')[:max_providers]
            
            # Create lead distributions
            distributions = []
            for provider in target_providers:
                distribution = LeadDistribution.objects.create(
                    lead=lead,
                    provider=provider,
                    status='sent'
                )
                distributions.append(distribution)
            
            # Update lead status
            if distributions:
                lead.is_distributed = True
                lead.distribution_date = timezone.now()
                lead.save()
            
            return {
                'lead': lead,
                'distributions': distributions,
                'message': f'Lead distributed to {len(distributions)} providers'
            }


class LeadStatsSerializer(serializers.Serializer):
    """
    Serializer for lead statistics
    """
    total_leads = serializers.IntegerField()
    pending_leads = serializers.IntegerField()
    contacted_leads = serializers.IntegerField()
    converted_leads = serializers.IntegerField()
    rejected_leads = serializers.IntegerField()
    expired_leads = serializers.IntegerField()
    conversion_rate = serializers.FloatField()
    response_rate = serializers.FloatField()
    today_leads = serializers.IntegerField()
    this_week_leads = serializers.IntegerField()
    this_month_leads = serializers.IntegerField()


from apps.authentication.serializers import UserProfileSerializer
from apps.services.serializers import ServiceListSerializer
from apps.packages.serializers import PackageListSerializer

class LeadSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for lead summary with full details
    """
    user_details = UserProfileSerializer(source='user', read_only=True)
    package_details = PackageListSerializer(source='package', read_only=True)
    service_details = ServiceListSerializer(source='service', read_only=True)

    class Meta:
        model = Lead
        fields = [
            'id',
            'user_details',        # full user profile info
            'package_details',     # full package details
            'service_details',     # full service details
            'lead_type',
            'status',
            'full_name',
            'phone',
            'preferred_date',
            'number_of_people',
            'budget_range',
            'created_at'
        ]
