# apps/telephony/serializers.py

from rest_framework import serializers
from .models import CallLog, CallSession
from apps.authentication.models import ServiceProviderProfile


class ProviderCallDetailsSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    owner_phone = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceProviderProfile
        fields = [
            'id',
            'business_name',
            'business_type',
            'business_description',
            'business_phone',
            'business_email',
            'business_address',
            'business_city',
            'business_state',
            'business_country',
            'business_pincode',
            'logo_url',
            'verification_status',
            'total_packages',
            'total_leads',
            'average_rating',
            'total_reviews',
            'experience_years',
            'owner_name',
            'owner_phone',
            'owner_email',
        ]

    def get_owner_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return ""

    def get_owner_phone(self, obj):
        return obj.user.phone if obj.user else ""

    def get_owner_email(self, obj):
        return obj.user.email if obj.user else ""

    def get_logo_url(self, obj):
        if obj.business_logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.business_logo.url)
            return obj.business_logo.url
        return None


class CallLogSerializer(serializers.ModelSerializer):
    provider_details = ProviderCallDetailsSerializer(source='provider', read_only=True)
    provider_name = serializers.CharField(source='provider.business_name', read_only=True)
    lead_name = serializers.CharField(source='lead.full_name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    pilgrim_phone = serializers.CharField(read_only=True)
    agent_phone = serializers.CharField(read_only=True)
    mask_phone = serializers.CharField(read_only=True)
    status_category = serializers.CharField(read_only=True)
    status_label = serializers.CharField(read_only=True)
    formatted_duration = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()

    def get_formatted_duration(self, obj):
        if not obj.duration:
            return "0s"
        mins, secs = divmod(obj.duration, 60)
        return f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

    def get_formatted_created_at(self, obj):
        if obj.created_at:
            return obj.created_at.strftime("%d %b %Y, %I:%M %p")
        return ""

    class Meta:
        model = CallLog
        fields = [
            'id',
            'call_sid',
            'call_from',
            'call_to',
            'pilgrim_phone',
            'agent_phone',
            'mask_phone',
            'caller_name',
            'direction',
            'destination_numbers',
            'dialed_number',
            'digits_pressed',
            'custom_field',
            'flow_id',
            'provider',
            'provider_name',
            'provider_details',
            'lead',
            'lead_name',
            'package',
            'package_name',
            'status',
            'status_category',
            'status_label',
            'call_type',
            'call_outcome',
            'notes',
            'duration',
            'formatted_duration',
            'conversation_duration',
            'recording_url',
            'created_at',
            'formatted_created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'call_sid',
            'call_from',
            'call_to',
            'pilgrim_phone',
            'agent_phone',
            'mask_phone',
            'direction',
            'destination_numbers',
            'dialed_number',
            'digits_pressed',
            'custom_field',
            'flow_id',
            'provider_details',
            'status_category',
            'status_label',
            'created_at',
            'formatted_created_at',
            'updated_at',
        ]

    def to_representation(self, instance):
        """
        Role-based privacy representation:
        - Service Providers: Show ONLY the pilgrim's real number (pilgrim_phone).
          Never show the platform virtual/mask number (080-472-89252).
        - Admin / Superadmin: Show BOTH agent and pilgrim numbers, plus virtual mask number and recordings.
        """
        data = super().to_representation(instance)
        request = self.context.get('request')

        is_provider = False
        if request and request.user and request.user.is_authenticated:
            is_admin = request.user.is_staff or getattr(request.user, 'user_type', None) in ['admin', 'super_admin']
            if not is_admin and hasattr(request.user, 'service_provider_profile'):
                is_provider = True

        if is_provider:
            # Hide virtual mask number & internal telephony routing from provider
            data.pop('call_to', None)
            data.pop('call_from', None)
            data.pop('mask_phone', None)
            data.pop('agent_phone', None)
            data.pop('destination_numbers', None)
            data.pop('dialed_number', None)
            data.pop('flow_id', None)
            data.pop('custom_field', None)
            data.pop('call_sid', None)

        return data


class ProviderCallDirectorySerializer(serializers.ModelSerializer):
    """
    Summary serializer for Provider Call Directory in Admin Panel.
    Shows provider information alongside their call metrics.
    """
    total_calls = serializers.IntegerField(read_only=True)
    received_calls = serializers.IntegerField(read_only=True)
    missed_calls = serializers.IntegerField(read_only=True)
    cut_calls = serializers.IntegerField(read_only=True)
    total_talk_time = serializers.IntegerField(read_only=True)
    formatted_talk_time = serializers.SerializerMethodField()
    answer_rate = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    owner_phone = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()

    class Meta:
        model = ServiceProviderProfile
        fields = [
            'id',
            'business_name',
            'business_type',
            'business_description',
            'business_phone',
            'business_email',
            'business_address',
            'business_city',
            'business_state',
            'business_country',
            'business_pincode',
            'verification_status',
            'total_packages',
            'average_rating',
            'total_reviews',
            'owner_name',
            'owner_phone',
            'owner_email',
            'logo_url',
            'total_calls',
            'received_calls',
            'missed_calls',
            'cut_calls',
            'total_talk_time',
            'formatted_talk_time',
            'answer_rate',
        ]

    def get_owner_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return ""

    def get_owner_phone(self, obj):
        return obj.user.phone if obj.user else ""

    def get_owner_email(self, obj):
        return obj.user.email if obj.user else ""

    def get_formatted_talk_time(self, obj):
        total_secs = getattr(obj, 'total_talk_time', 0) or 0
        mins, secs = divmod(total_secs, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m {secs}s" if mins > 0 else "0s"

    def get_answer_rate(self, obj):
        total = getattr(obj, 'total_calls', 0) or 0
        if total == 0:
            return 0
        received = getattr(obj, 'received_calls', 0) or 0
        return round((received / total) * 100, 1)

    def get_logo_url(self, obj):
        if obj.business_logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.business_logo.url)
            return obj.business_logo.url
        return None
