from rest_framework import serializers

from apps.payments.serializers import PaymentSerializer
from .models import Airport, AirportAttendant, AirportAttendantBooking


class AirportSerializer(serializers.ModelSerializer):
    attendant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Airport
        fields = ['id', 'name', 'code', 'price', 'is_active', 'attendant_count']
        read_only_fields = ['id', 'attendant_count']


class AirportAttendantSerializer(serializers.ModelSerializer):
    airport_name = serializers.CharField(source='airport.name', read_only=True)
    pan_document_exists = serializers.SerializerMethodField()
    aadhaar_document_exists = serializers.SerializerMethodField()
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = AirportAttendant
        fields = [
            'id', 'user', 'airport', 'airport_name', 'name', 'phone', 'alternate_phone', 'email',
            'profile_image', 'profile_image_url', 'pan_document', 'aadhaar_document', 'pan_document_exists',
            'aadhaar_document_exists', 'is_active', 'is_on_duty',
        ]
        extra_kwargs = {
            'profile_image': {'required': False},
            'pan_document': {'write_only': True, 'required': False},
            'aadhaar_document': {'write_only': True, 'required': False},
            'user': {'required': False, 'allow_null': True},
        }

    def get_profile_image_url(self, obj):
        if not obj.profile_image:
            return None
        request = self.context.get('request')
        image_url = obj.profile_image.url
        return request.build_absolute_uri(image_url) if request else image_url

    def get_pan_document_exists(self, obj):
        return bool(obj.pan_document)

    def get_aadhaar_document_exists(self, obj):
        return bool(obj.aadhaar_document)

    def validate(self, attrs):
        instance = self.instance
        has_pan = bool(attrs.get('pan_document', instance.pan_document if instance else None))
        has_aadhaar = bool(attrs.get('aadhaar_document', instance.aadhaar_document if instance else None))
        if has_pan == has_aadhaar:
            raise serializers.ValidationError(
                'Upload exactly one KYC document: either PAN card or Aadhaar card, not both.'
            )
        return attrs

    def validate_pan_document(self, document):
        return self._validate_kyc_document(document)

    def validate_aadhaar_document(self, document):
        return self._validate_kyc_document(document)

    def validate_profile_image(self, image):
        if image.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Profile images must be 5 MB or smaller.')
        return image

    @staticmethod
    def _validate_kyc_document(document):
        if document.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('KYC documents must be 5 MB or smaller.')
        return document


class AirportAttendantBookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirportAttendantBooking
        fields = [
            'airport', 'service_date', 'service_time', 'flight_name',
            'flight_number', 'pilgrim_count', 'lead_pilgrim_name',
            'lead_pilgrim_phone', 'special_notes',
        ]

    def validate_airport(self, airport):
        if not airport.is_active:
            raise serializers.ValidationError('This airport is not available for booking.')
        return airport

    def validate_service_date(self, service_date):
        from django.utils import timezone

        if service_date < timezone.localdate():
            raise serializers.ValidationError('Service date must be today or later.')
        return service_date

    def validate(self, attrs):
        from datetime import datetime
        from django.utils import timezone

        service_date = attrs['service_date']
        service_time = attrs['service_time']
        if service_date == timezone.localdate():
            requested_time = timezone.make_aware(datetime.combine(service_date, service_time))
            if requested_time < timezone.localtime():
                raise serializers.ValidationError({'service_time': 'Service time must be in the future.'})
        return attrs


class AirportAttendantBookingSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    airport_name = serializers.CharField(source='airport.name', read_only=True)
    attendant_name = serializers.SerializerMethodField()
    attendant_phone = serializers.SerializerMethodField()
    attendant_alternate_phone = serializers.SerializerMethodField()
    attendant_profile_image_url = serializers.SerializerMethodField()
    completion_image_url = serializers.SerializerMethodField()
    payment_status = serializers.CharField(source='payment.status', read_only=True, default=None)
    provider_name = serializers.CharField(source='provider.full_name', read_only=True)
    provider_phone = serializers.CharField(source='provider.phone', read_only=True)
    provider_email = serializers.EmailField(source='provider.email', read_only=True)

    class Meta:
        model = AirportAttendantBooking
        fields = [
            'id', 'provider_name', 'provider_phone', 'provider_email', 'airport',
            'airport_name', 'service_date', 'service_time', 'flight_name',
            'flight_number', 'pilgrim_count', 'amount', 'status', 'duty_status',
            'lead_pilgrim_name', 'lead_pilgrim_phone', 'terminal_gate',
            'special_notes', 'attendant_notes', 'completed_at',
            'completion_image', 'completion_image_url',
            'payment_status', 'attendant_name', 'attendant_phone',
            'attendant_alternate_phone', 'created_at', 'attendant_profile_image_url',
        ]
        extra_kwargs = {
            'completion_image': {'read_only': True},
        }

    def get_completion_image_url(self, obj):
        if not obj.completion_image:
            return None
        request = self.context.get('request')
        image_url = obj.completion_image.url
        return request.build_absolute_uri(image_url) if request else image_url


    def _attendant_after_payment(self, obj):
        return (
            obj.attendant
            if (
                obj.status == AirportAttendantBooking.Status.CONFIRMED
                and obj.payment_id
                and obj.payment.status == 'completed'
            )
            else None
        )

    def get_status(self, obj):
        from datetime import timedelta
        from django.utils import timezone

        if (
            obj.status == AirportAttendantBooking.Status.AWAITING_PAYMENT
            and obj.created_at < timezone.now() - timedelta(minutes=15)
        ):
            return 'expired'
        return obj.status

    def get_attendant_name(self, obj):
        attendant = self._attendant_after_payment(obj)
        return attendant.name if attendant else None

    def get_attendant_phone(self, obj):
        attendant = self._attendant_after_payment(obj)
        return attendant.phone if attendant else None

    def get_attendant_alternate_phone(self, obj):
        attendant = self._attendant_after_payment(obj)
        return attendant.alternate_phone if attendant else None

    def get_attendant_profile_image_url(self, obj):
        attendant = self._attendant_after_payment(obj)
        if not attendant or not attendant.profile_image:
            return None
        request = self.context.get('request')
        image_url = attendant.profile_image.url
        return request.build_absolute_uri(image_url) if request else image_url


class AdminAirportAttendantBookingSerializer(AirportAttendantBookingSerializer):
    provider_details = serializers.SerializerMethodField()
    airport_details = serializers.SerializerMethodField()
    attendant_details = serializers.SerializerMethodField()
    payment_details = PaymentSerializer(source='payment', read_only=True)

    class Meta(AirportAttendantBookingSerializer.Meta):
        fields = AirportAttendantBookingSerializer.Meta.fields + [
            'provider_details', 'airport_details', 'attendant_details', 'payment_details',
            'updated_at',
        ]

    def get_provider_details(self, obj):
        provider = obj.provider
        profile = getattr(provider, 'service_provider_profile', None)
        return {
            'id': provider.id,
            'full_name': provider.full_name,
            'email': provider.email,
            'phone': provider.phone,
            'user_type': provider.user_type,
            'business_name': profile.business_name if profile else None,
            'business_email': profile.business_email if profile else None,
            'business_phone': profile.business_phone if profile else None,
        }

    def get_airport_details(self, obj):
        return {
            'id': obj.airport_id,
            'name': obj.airport.name,
            'code': obj.airport.code,
            'current_price': obj.airport.price,
            'is_active': obj.airport.is_active,
        }

    def get_attendant_details(self, obj):
        attendant = obj.attendant
        if not attendant:
            return None
        image_url = attendant.profile_image.url if attendant.profile_image else None
        request = self.context.get('request')
        return {
            'id': attendant.id,
            'name': attendant.name,
            'phone': attendant.phone,
            'alternate_phone': attendant.alternate_phone,
            'email': attendant.email,
            'profile_image_url': request.build_absolute_uri(image_url) if request and image_url else image_url,
            'is_active': attendant.is_active,
            'is_on_duty': attendant.is_on_duty,
            'pan_document_exists': bool(attendant.pan_document),
            'aadhaar_document_exists': bool(attendant.aadhaar_document),
        }


# =========================================================================
# ATTENDANT PORTAL SERIALIZERS
# =========================================================================

class AttendantPortalProfileSerializer(serializers.ModelSerializer):
    airport_name = serializers.CharField(source='airport.name', read_only=True)
    airport_code = serializers.CharField(source='airport.code', read_only=True)
    profile_image_url = serializers.SerializerMethodField()
    pan_document_exists = serializers.SerializerMethodField()
    aadhaar_document_exists = serializers.SerializerMethodField()
    duty_stats = serializers.SerializerMethodField()

    class Meta:
        model = AirportAttendant
        fields = [
            'id', 'name', 'phone', 'alternate_phone', 'email',
            'airport', 'airport_name', 'airport_code',
            'profile_image_url', 'is_active', 'is_on_duty',
            'pan_document_exists', 'aadhaar_document_exists', 'duty_stats',
        ]
        read_only_fields = ['id', 'name', 'email', 'airport', 'airport_name', 'airport_code']

    def get_profile_image_url(self, obj):
        if not obj.profile_image:
            return None
        request = self.context.get('request')
        image_url = obj.profile_image.url
        return request.build_absolute_uri(image_url) if request else image_url

    def get_pan_document_exists(self, obj):
        return bool(obj.pan_document)

    def get_aadhaar_document_exists(self, obj):
        return bool(obj.aadhaar_document)

    def get_duty_stats(self, obj):
        from django.utils import timezone
        today = timezone.localdate()
        bookings = obj.bookings.all()
        return {
            'completed_duties': bookings.filter(duty_status=AirportAttendantBooking.DutyStatus.COMPLETED).count(),
            'today_duties': bookings.filter(service_date=today, status=AirportAttendantBooking.Status.CONFIRMED).count(),
            'upcoming_duties': bookings.filter(service_date__gte=today, status=AirportAttendantBooking.Status.CONFIRMED).count(),
            'total_assigned': bookings.count(),
        }


class AttendantDutySerializer(serializers.ModelSerializer):
    """
    Detailed duty serializer for the airport assistant, exposing rich Agent information.
    """
    airport_name = serializers.CharField(source='airport.name', read_only=True)
    airport_code = serializers.CharField(source='airport.code', read_only=True)
    agent_details = serializers.SerializerMethodField()
    completion_image_url = serializers.SerializerMethodField()

    class Meta:
        model = AirportAttendantBooking
        fields = [
            'id', 'service_date', 'service_time', 'flight_name', 'flight_number',
            'pilgrim_count', 'status', 'duty_status', 'lead_pilgrim_name',
            'lead_pilgrim_phone', 'terminal_gate', 'special_notes',
            'attendant_notes', 'completion_image_url', 'completed_at', 'created_at',
            'airport', 'airport_name', 'airport_code', 'agent_details',
        ]

    def get_completion_image_url(self, obj):
        if not obj.completion_image:
            return None
        request = self.context.get('request')
        image_url = obj.completion_image.url
        return request.build_absolute_uri(image_url) if request else image_url

    def get_agent_details(self, obj):
        provider = obj.provider
        profile = getattr(provider, 'service_provider_profile', None)
        request = self.context.get('request')
        logo_url = None
        if profile and profile.business_logo:
            logo_url = request.build_absolute_uri(profile.business_logo.url) if request else profile.business_logo.url

        return {
            'id': provider.id,
            'agency_name': profile.business_name if (profile and profile.business_name) else provider.full_name or 'Travel Agency',
            'business_type': profile.business_type if profile else None,
            'business_logo': logo_url,
            'agent_name': provider.full_name or 'Agent',
            'agent_phone': (profile.business_phone if profile and profile.business_phone else provider.phone) or '',
            'agent_whatsapp': (profile.business_phone if profile and profile.business_phone else provider.phone) or '',
            'agent_email': (profile.business_email if profile and profile.business_email else provider.email) or '',
            'business_city': profile.business_city if profile else '',
            'business_state': profile.business_state if profile else '',
            'business_address': profile.business_address if profile else '',
            'is_verified': profile.is_verified if profile else provider.is_verified,
        }


class AttendantDutyStatusUpdateSerializer(serializers.ModelSerializer):
    completion_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = AirportAttendantBooking
        fields = ['duty_status', 'terminal_gate', 'attendant_notes', 'completion_image']

    def update(self, instance, validated_data):
        from django.utils import timezone
        new_status = validated_data.get('duty_status', instance.duty_status)
        instance.duty_status = new_status
        if 'terminal_gate' in validated_data:
            instance.terminal_gate = validated_data['terminal_gate']
        if 'attendant_notes' in validated_data:
            instance.attendant_notes = validated_data['attendant_notes']
        if 'completion_image' in validated_data:
            instance.completion_image = validated_data['completion_image']

        if new_status == AirportAttendantBooking.DutyStatus.COMPLETED and not instance.completed_at:
            instance.completed_at = timezone.now()
        instance.save()
        return instance


