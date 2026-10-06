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

    class Meta:
        model = AirportAttendant
        fields = [
            'id', 'airport', 'airport_name', 'name', 'phone', 'alternate_phone', 'email',
            'pan_document', 'aadhaar_document', 'pan_document_exists',
            'aadhaar_document_exists', 'is_active',
        ]
        extra_kwargs = {
            'pan_document': {'write_only': True, 'required': False},
            'aadhaar_document': {'write_only': True, 'required': False},
        }

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
            'flight_number', 'pilgrim_count',
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
    payment_status = serializers.CharField(source='payment.status', read_only=True, default=None)
    provider_name = serializers.CharField(source='provider.full_name', read_only=True)
    provider_phone = serializers.CharField(source='provider.phone', read_only=True)
    provider_email = serializers.EmailField(source='provider.email', read_only=True)

    class Meta:
        model = AirportAttendantBooking
        fields = [
            'id', 'provider_name', 'provider_phone', 'provider_email', 'airport',
            'airport_name', 'service_date', 'service_time', 'flight_name',
            'flight_number', 'pilgrim_count', 'amount', 'status', 'payment_status',
            'attendant_name', 'attendant_phone', 'attendant_alternate_phone', 'created_at',
        ]

    def _attendant_after_payment(self, obj):
        return obj.attendant if obj.payment_id and obj.payment.status == 'completed' else None

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
        return {
            'id': attendant.id,
            'name': attendant.name,
            'phone': attendant.phone,
            'alternate_phone': attendant.alternate_phone,
            'email': attendant.email,
            'is_active': attendant.is_active,
            'pan_document_exists': bool(attendant.pan_document),
            'aadhaar_document_exists': bool(attendant.aadhaar_document),
        }
