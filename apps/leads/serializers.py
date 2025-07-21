from rest_framework import serializers
from django.utils import timezone
from apps.authentication.serializers import UserProfileSerializer, ServiceProviderProfileSerializer
from apps.services.serializers import ServiceListSerializer
from apps.packages.serializers import PackageListSerializer
from .models import Lead, LeadDistribution, LeadInteraction, LeadNote


class LeadSerializer(serializers.ModelSerializer):
    """
    Serializer for Lead model
    """
    user_details = UserProfileSerializer(source='user', read_only=True)
    package_details = PackageListSerializer(source='package', read_only=True)
    service_details = ServiceListSerializer(source='service', read_only=True)
    is_expired = serializers.ReadOnlyField()
    target_providers = serializers.ReadOnlyField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'user', 'user_details', 'package', 'package_details', 
            'service', 'service_details', 'lead_type', 'status',
            'full_name', 'email', 'phone', 'preferred_date', 
            'number_of_people', 'budget_range', 'departure_city',
            'preferred_hotel_category', 'special_requirements', 
            'custom_message', 'selected_services', 'is_distributed',
            'distribution_date', 'expires_at', 'source', 'priority',
            'is_expired', 'target_providers', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'is_distributed', 'distribution_date', 'created_at', 'updated_at']
    
    def validate(self, data):
        """
        Custom validation for Lead
        """
        # Either package or service must be provided
        if not data.get('package') and not data.get('service'):
            raise serializers.ValidationError(
                "Either package or service must be provided"
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
    
    def create(self, validated_data):
        """
        Create a new lead and set the user
        """
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class LeadCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating leads (minimal fields)
    """
    class Meta:
        model = Lead
        fields = [
            'package', 'service', 'lead_type', 'full_name', 'email', 'phone',
            'preferred_date', 'number_of_people', 'budget_range', 'departure_city',
            'preferred_hotel_category', 'special_requirements', 'custom_message',
            'selected_services', 'source'
        ]
    
    def validate(self, data):
        """
        Custom validation for Lead creation
        """
        # Either package or service must be provided
        if not data.get('package') and not data.get('service'):
            raise serializers.ValidationError(
                "Either package or service must be provided"
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
        
        return data
    
    def create(self, validated_data):
        """
        Create a new lead and set the user
        """
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


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
            'response_message', 'quoted_price', 'email_sent', 'sms_sent',
            'app_notification_sent', 'created_at', 'updated_at'
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
        validated_data['provider'] = self.context['request'].user.service_provider
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
        validated_data['provider'] = self.context['request'].user.service_provider
        return super().create(validated_data)


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


class LeadSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for lead summary (minimal fields)
    """
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    
    class Meta:
        model = Lead
        fields = [
            'id', 'user_name', 'package_name', 'service_name', 'lead_type',
            'status', 'full_name', 'phone', 'preferred_date', 'number_of_people',
            'budget_range', 'created_at', 'is_expired'
        ]