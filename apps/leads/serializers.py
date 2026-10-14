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
        # For partial updates, check existing values if they're not in data
        instance = getattr(self, 'instance', None)
        lead_type = data.get('lead_type', getattr(instance, 'lead_type', None))
        package = data.get('package', getattr(instance, 'package', None))
        service = data.get('service', getattr(instance, 'service', None))

        # Either package or service must be provided for non-custom leads
        if lead_type != 'custom':
            if not package and not service:
                raise serializers.ValidationError(
                    "Either package or service must be provided for non-custom leads"
                )
            
            # Both package and service cannot be provided
            if package and service:
                raise serializers.ValidationError(
                    "Both package and service cannot be provided"
                )
        
        # Validate preferred date
        preferred_date = data.get('preferred_date', getattr(instance, 'preferred_date', None))
        if preferred_date and preferred_date < timezone.now().date():
            raise serializers.ValidationError(
                "Preferred date cannot be in the past"
            )
        
        # Validate number of people
        number_of_people = data.get('number_of_people', getattr(instance, 'number_of_people', 1))
        if number_of_people < 1:
            raise serializers.ValidationError(
                "Number of people must be at least 1"
            )
        

        # Prevent duplicate leads from the same user for the same package/service within 15 minutes
        user = self.context.get('request').user if self.context.get('request') else None
        if user and user.is_authenticated:
            # Check if there's a recent lead with the same package/service by this user
            recent_leads = Lead.objects.filter(
                user=user,
                created_at__gte=timezone.now() - timezone.timedelta(minutes=15)
            )
            
            if package:
                recent_leads = recent_leads.filter(package=package)
            elif service:
                recent_leads = recent_leads.filter(service=service)
                
            # If lead_type is not custom, block if recent lead exists
            if lead_type != 'custom' and recent_leads.exists():
                raise serializers.ValidationError(
                    "You have already submitted an inquiry for this recently. Please wait 15 minutes before submitting again."
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
        Automatically distribute lead to relevant service providers.
        - Ultra/Growth: Providers within 500km of target, same type/category/biz_type.
        - Basic: Only providers of specific uploaded package/service.
        """
        from apps.core.utils import calculate_distance
        from apps.subscriptions.models import Subscription
        
        target_business_types = self.get_target_business_types(lead)
        
        # 1. Base Query: Verified and Active Providers with active subscriptions (Enterprise Scaled)
        from django.utils import timezone
        now = timezone.now()
        base_providers = ServiceProviderProfile.objects.filter(
            verification_status='verified',
            is_active=True,
            user__subscriptions__status='active',
            user__subscriptions__start_date__lte=now,
            user__subscriptions__end_date__gte=now
        ).select_related('user').prefetch_related('user__subscriptions__plan').exclude(
            id__in=LeadDistribution.objects.filter(lead=lead).values_list('provider_id', flat=True)
        ).distinct()

        # Determine target coordinates from the lead's associated package/service
        origin_lat = None
        origin_lng = None
        if lead.package and lead.package.provider and lead.package.provider.user:
            origin_lat = lead.package.provider.user.latitude
            origin_lng = lead.package.provider.user.longitude
        elif lead.service and lead.service.provider and lead.service.provider.user:
            origin_lat = lead.service.provider.user.latitude
            origin_lng = lead.service.provider.user.longitude

        filtered_providers = []
        
        # 2. Filter Providers based on Plan and Location
        for provider in base_providers:
            subscription = provider.get_active_subscription()
            if not subscription:
                continue
            
            plan_type = subscription.plan.plan_type
            
            # --- LEAD DISTRIBUTION LOGIC (Growth, Ultra, Premium, Basic) ---
            if plan_type in ['growth', 'ultra_premium', 'premium', 'basic']:
                # Geographic check (500km radius)
                if origin_lat and origin_lng and provider.user.latitude and provider.user.longitude:
                    distance = calculate_distance(
                        float(origin_lat), float(origin_lng),
                        float(provider.user.latitude), float(provider.user.longitude)
                    )
                    if distance > 500:
                        # EXCEPT if it's their own package/service (direct lead always delivered)
                        is_owner = (lead.package and lead.package.provider == provider) or \
                                   (lead.service and lead.service.provider == provider)
                        if not is_owner:
                            continue 
                
                # Matching Criteria: Same biz type and package/service category
                # Providers also get direct leads for their own items regardless of business_type mismatch (though unlikely)
                is_owner = (lead.package and lead.package.provider == provider) or \
                           (lead.service and lead.service.provider == provider)
                
                if is_owner or provider.business_type in target_business_types:
                    # Check for similar packages/services
                    if is_owner:
                        has_similar = True
                    elif lead.package:
                        has_similar = provider.packages.filter(
                            package_type=lead.package.package_type,
                            package_category=lead.package.package_category,
                            status='published'
                        ).exists()
                    else:
                        has_similar = provider.services.filter(
                            service_type=lead.service.service_type,
                            category=lead.service.category,
                            status='published'
                        ).exists()
                    
                    if has_similar:
                        filtered_providers.append(provider)

        # 3. Credit & Subscription-Based Ranking (1 Growth, 2 Ultra, 3 Premium, 4 Basic):
        def get_lead_priority(p):
            sub = p.get_active_subscription()
            plan_type = sub.plan.plan_type if (sub and sub.plan) else 'free'
            balance = getattr(p, 'credit_balance', 0)
            
            weight = 0
            if plan_type == 'growth' and balance > 0:
                weight = 4
            elif plan_type == 'ultra_premium':
                weight = 3
            elif plan_type == 'premium':
                weight = 2
            elif plan_type == 'basic':
                weight = 1
                
            return (
                weight,
                balance
            )

        filtered_providers.sort(key=get_lead_priority, reverse=True)
        
        # Limit targeting
        max_providers = 10
        target_providers = filtered_providers[:max_providers]
        
        # 4. Create Distributions
        distributions = []
        for provider in target_providers:
            distribution = LeadDistribution.objects.create(
                lead=lead,
                provider=provider,
                status='sent'
            )
            distributions.append(distribution)
            
            # Deduct credits (Consolidated 4-credit rule)
            try:
                from apps.subscriptions.tasks import deduct_lead_credits_task
                deduct_lead_credits_task.delay(provider.id, lead.id)
            except Exception:
                from apps.subscriptions.services import CreditService
                CreditService.deduct_lead_credits(provider, lead)
        
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


from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from .models import Lead, LeadDistribution, ServiceProviderProfile

import logging
logger = logging.getLogger(__name__)


class LeadCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating leads (minimal fields) with auto-distribution
    """
    class Meta:
        model = Lead
        fields = [
            'package', 'service', 'lead_type', 'full_name', 'email', 'phone',
            'preferred_date', 'number_of_people', 'budget_range', 'departure_city',
            'special_requirements', 'selected_services', 'source', 'priority'
        ]

    def validate(self, data):
        """
        Custom validation for Lead creation
        """
        # Validate lead_type presence
        lead_type = data.get('lead_type')
        package = data.get('package')
        service = data.get('service')

        if lead_type != 'custom':
            if not package and not service:
                raise serializers.ValidationError(
                    "Either package or service must be provided for non-custom leads."
                )
            if package and service:
                raise serializers.ValidationError(
                    "Both package and service cannot be provided simultaneously."
                )

        # Validate preferred date
        preferred_date = data.get('preferred_date')
        if preferred_date and preferred_date < timezone.now().date():
            raise serializers.ValidationError(
                "Preferred date cannot be in the past."
            )


        # Prevent duplicate leads from the same user for the same package/service within 15 minutes
        user = self.context.get('request').user if self.context.get('request') else None
        if user and user.is_authenticated:
            # Check if there's a recent lead with the same package/service by this user
            recent_leads = Lead.objects.filter(
                user=user,
                created_at__gte=timezone.now() - timezone.timedelta(minutes=15)
            )
            
            if package:
                recent_leads = recent_leads.filter(package=package)
            elif service:
                recent_leads = recent_leads.filter(service=service)
                
            # If lead_type is not custom, block if recent lead exists
            if lead_type != 'custom' and recent_leads.exists():
                raise serializers.ValidationError(
                    "You have already submitted an inquiry for this recently. Please wait 15 minutes before submitting again."
                )

        return data

    def get_target_business_types(self, lead):
        """
        Determine target business types based on lead type and content
        """
        target_types = []

        if lead.lead_type == 'package':
            if lead.package:
                target_types = [lead.package.provider.business_type]
            else:
                target_types = ['umrah_packages', 'hajj_package', 'agency']

        elif lead.lead_type == 'service':
            if lead.service:
                target_types = [lead.service.provider.business_type]
            else:
                target_types = ['agency', 'individual', 'company']

        elif lead.lead_type == 'custom':
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

            # Check special requirements
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

        # Always include 'agency'
        if 'agency' not in target_types:
            target_types.append('agency')

        return target_types

    def distribute_lead(self, lead):
        """
        Automatically distribute lead to relevant service providers.
        Uses same logic as LeadSerializer.
        """
        from apps.core.utils import calculate_distance
        from apps.subscriptions.models import CreditWallet
        
        target_business_types = self.get_target_business_types(lead)

        # Base Query (Enterprise Scaled)
        from django.utils import timezone
        now = timezone.now()
        base_providers = ServiceProviderProfile.objects.filter(
            verification_status='verified',
            is_active=True,
            user__subscriptions__status='active',
            user__subscriptions__start_date__lte=now,
            user__subscriptions__end_date__gte=now
        ).select_related('user').prefetch_related('user__subscriptions__plan').exclude(
            id__in=LeadDistribution.objects.filter(lead=lead).values_list('provider_id', flat=True)
        ).distinct()

        origin_lat = None
        origin_lng = None
        if lead.package and lead.package.provider and lead.package.provider.user:
            origin_lat = lead.package.provider.user.latitude
            origin_lng = lead.package.provider.user.longitude
        elif lead.service and lead.service.provider and lead.service.provider.user:
            origin_lat = lead.service.provider.user.latitude
            origin_lng = lead.service.provider.user.longitude

        filtered_providers = []
        for provider in base_providers:
            subscription = provider.get_active_subscription()
            if not subscription:
                continue
            
            plan_type = subscription.plan.plan_type
            
            # --- LEAD DISTRIBUTION LOGIC (Growth, Ultra, Premium, Basic) ---
            if plan_type in ['growth', 'ultra_premium', 'premium', 'basic']:
                if origin_lat and origin_lng and provider.user.latitude and provider.user.longitude:
                    distance = calculate_distance(
                        float(origin_lat), float(origin_lng),
                        float(provider.user.latitude), float(provider.user.longitude)
                    )
                    if distance > 500:
                        # EXCEPT if it's their own package/service (direct lead always delivered)
                        is_owner = (lead.package and lead.package.provider == provider) or \
                                   (lead.service and lead.service.provider == provider)
                        if not is_owner:
                            continue
                
                # Matching Criteria: Same biz type and package/service category
                is_owner = (lead.package and lead.package.provider == provider) or \
                           (lead.service and lead.service.provider == provider)

                if is_owner or provider.business_type in target_business_types:
                    if is_owner:
                        has_similar = True
                    elif lead.package:
                        has_similar = provider.packages.filter(
                            package_type=lead.package.package_type,
                            package_category=lead.package.package_category,
                            status='published'
                        ).exists()
                    else:
                        has_similar = provider.services.filter(
                            service_type=lead.service.service_type,
                            category=lead.service.category,
                            status='published'
                        ).exists()
                    
                    if has_similar:
                        filtered_providers.append(provider)

        # Credit & Subscription-Based Ranking (1 Growth, 2 Ultra, 3 Premium, 4 Basic):
        def get_lead_priority(p):
            sub = p.get_active_subscription()
            plan_type = sub.plan.plan_type if (sub and sub.plan) else 'free'
            balance = getattr(p, 'credit_balance', 0)
            
            weight = 0
            if plan_type == 'growth' and balance > 0:
                weight = 4
            elif plan_type == 'ultra_premium':
                weight = 3
            elif plan_type == 'premium':
                weight = 2
            elif plan_type == 'basic':
                weight = 1
                
            return (
                weight,
                balance
            )
        
        filtered_providers.sort(key=get_lead_priority, reverse=True)
        
        max_providers = 10
        target_providers = filtered_providers[:max_providers]

        distributions = []
        for provider in target_providers:
            distribution = LeadDistribution.objects.create(
                lead=lead,
                provider=provider,
                status='sent'
            )
            distributions.append(distribution)
            
            # Deduct credits
            try:
                from apps.subscriptions.tasks import deduct_lead_credits_task
                deduct_lead_credits_task.delay(provider.id, lead.id)
            except Exception:
                from apps.subscriptions.services import CreditService
                CreditService.deduct_lead_credits(provider, lead)

        # Update lead status
        if distributions:
            lead.is_distributed = True
            lead.distribution_date = timezone.now()
            lead.save()

        logger.info(f"Lead {lead.id} distributed to {len(distributions)} providers")
        return distributions

    def create(self, validated_data):
        """
        Create lead and auto-distribute
        """
        validated_data['user'] = self.context['request'].user

        # Auto-fill selected_services
        if validated_data.get('lead_type') == 'package' and not validated_data.get('selected_services') and validated_data.get('package'):
            validated_data['selected_services'] = {
                "package_id": validated_data['package'].id,
                "package_name": validated_data['package'].name
            }

        if validated_data.get('lead_type') == 'service' and not validated_data.get('selected_services') and validated_data.get('service'):
            validated_data['selected_services'] = {
                "service_id": validated_data['service'].id,
                "service_name": validated_data['service'].title
            }

        # Use transaction to ensure lead creation + distribution atomicity
        with transaction.atomic():
            lead = super().create(validated_data)
            self.distribute_lead(lead)

        logger.info(f"Lead {lead.id} created successfully")
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
    Serializer for manual lead distribution by superadmin/admin.
    Supports targeting subscribed providers, specific plan tiers, and provider selection.
    """
    lead_id = serializers.IntegerField()
    provider_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Specific provider IDs to distribute to. Takes precedence over business_types."
    )
    business_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        help_text="List of business types to target. If not provided, auto-determined based on lead content."
    )
    only_subscribed_providers = serializers.BooleanField(
        default=True,
        required=False,
        help_text="If True, only providers with an active paid subscription receive the lead."
    )
    plan_types = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        help_text="Filter by specific subscription plan types (growth, ultra_premium, premium, basic)."
    )
    deduct_credits = serializers.BooleanField(
        default=True,
        required=False,
        help_text="Whether to deduct lead credits from providers (default True, set False for complimentary leads)."
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
        if not value:
            return value
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
        Perform manual lead distribution with subscription and credit validation
        """
        lead_id = self.validated_data['lead_id']
        business_types = self.validated_data.get('business_types')
        provider_ids = self.validated_data.get('provider_ids')
        only_subscribed = self.validated_data.get('only_subscribed_providers', True)
        plan_types = self.validated_data.get('plan_types')
        deduct_credits = self.validated_data.get('deduct_credits', True)
        max_providers = self.validated_data.get('max_providers', 10)
        
        lead = Lead.objects.get(id=lead_id)
        now = timezone.now()
        
        with transaction.atomic():
            base_qs = ServiceProviderProfile.objects.filter(
                verification_status='verified',
                is_active=True
            ).select_related(
                'user', 'user__credit_wallet'
            ).prefetch_related(
                'user__subscriptions__plan'
            )
            
            if provider_ids:
                # Use specific provider IDs chosen by admin
                target_providers = base_qs.filter(id__in=provider_ids)
            elif business_types:
                # Use specified business types
                target_providers = base_qs.filter(business_type__in=business_types)
            else:
                # Auto-determine business types based on lead content
                serializer = LeadCreateSerializer()
                target_business_types = serializer.get_target_business_types(lead)
                target_providers = base_qs.filter(business_type__in=target_business_types)
            
            # Filter for active subscription if requested
            if only_subscribed:
                target_providers = target_providers.filter(
                    user__subscriptions__status='active',
                    user__subscriptions__start_date__lte=now,
                    user__subscriptions__end_date__gte=now
                )
            
            # Filter for specific plan types if requested
            if plan_types:
                target_providers = target_providers.filter(
                    user__subscriptions__status='active',
                    user__subscriptions__start_date__lte=now,
                    user__subscriptions__end_date__gte=now,
                    user__subscriptions__plan__plan_type__in=plan_types
                )
            
            # Exclude providers who already received this lead
            target_providers = target_providers.exclude(
                id__in=LeadDistribution.objects.filter(lead=lead).values_list('provider_id', flat=True)
            ).distinct()
            
            # Rank providers: 1 Growth (highest credits), 2 Ultra, 3 Premium, 4 Basic, 5 Free
            def get_priority(p):
                sub = p.get_active_subscription()
                ptype = sub.plan.plan_type if (sub and sub.plan) else 'free'
                bal = getattr(p, 'credit_balance', 0)
                if ptype == 'growth' and bal > 0:
                    tier = 1
                elif ptype == 'ultra_premium':
                    tier = 2
                elif ptype == 'premium':
                    tier = 3
                elif ptype == 'basic':
                    tier = 4
                else:
                    tier = 5
                return (tier, -bal if tier == 1 else 0, -float(p.average_rating or 0))
            
            provider_list = list(target_providers)
            provider_list.sort(key=get_priority)
            
            # Cap providers if provider_ids not explicitly selected
            if not provider_ids:
                provider_list = provider_list[:max_providers]
            
            # Create lead distributions idempotently
            distributions = []
            for provider in provider_list:
                dist, created = LeadDistribution.objects.get_or_create(
                    lead=lead,
                    provider=provider,
                    defaults={'status': 'sent'}
                )
                if created:
                    distributions.append(dist)
                    
                    # Deduct credits if requested
                    if deduct_credits:
                        try:
                            from apps.subscriptions.tasks import deduct_lead_credits_task
                            deduct_lead_credits_task.delay(provider.id, lead.id)
                        except Exception:
                            from apps.subscriptions.services import CreditService
                            CreditService.deduct_lead_credits(provider, lead)
                    
                    # Send lead notification to provider user
                    try:
                        from apps.notifications.services import NotificationService
                        if provider.user:
                            NotificationService.send_lead_received_notification(lead, provider.user)
                    except Exception as e:
                        logger.warning(f"Notification error for provider {provider.id}: {e}")
            
            # Update lead status
            if distributions:
                lead.is_distributed = True
                lead.distribution_date = timezone.now()
                lead.save(update_fields=['is_distributed', 'distribution_date', 'updated_at'])
            
            return {
                'lead': lead,
                'distributions': distributions,
                'message': f'Lead successfully distributed to {len(distributions)} provider(s)'
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
