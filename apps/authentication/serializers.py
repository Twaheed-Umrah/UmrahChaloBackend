from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import uuid

from django.utils import timezone
from .models import (
    User, OTPVerification, LoginAttempt, UserSession, 
    ServiceProviderProfile, SavedPackage, UserActivity
)
from apps.core.utils import generate_otp, send_otp
import re


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    user_type_display = serializers.CharField(source='get_user_type_display', read_only=True)
    location_info = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'phone', 'user_type', 'user_type_display',
            'full_name', 'is_verified', 'is_active', 'latitude', 'longitude',
            'location_address', 'location_updated_at', 'location_info',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_type', 'is_verified', 'location_updated_at', 'created_at', 'updated_at']

    def get_full_name(self, obj):
        return obj.full_name or f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_location_info(self, obj):
        return obj.get_location_info()

    def validate_email(self, value):
        user = self.context.get('request').user if self.context.get('request') else None
        if user and User.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        elif not user and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        if value:
            phone_regex = re.compile(r'^\+?1?\d{9,15}$')
            if not phone_regex.match(value):
                raise serializers.ValidationError("Invalid phone number format.")
        return value

    def validate_latitude(self, value):
        if value is not None:
            if not (-90 <= float(value) <= 90):
                raise serializers.ValidationError("Latitude must be between -90 and 90 degrees.")
        return value

    def validate_longitude(self, value):
        if value is not None:
            if not (-180 <= float(value) <= 180):
                raise serializers.ValidationError("Longitude must be between -180 and 180 degrees.")
        return value


class LocationUpdateSerializer(serializers.Serializer):
    """
    Serializer specifically for location updates
    """
    latitude = serializers.DecimalField(max_digits=10, decimal_places=8)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=8)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_latitude(self, value):
        if not (-90 <= float(value) <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90 degrees.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= float(value) <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180 degrees.")
        return value

    def update_user_location(self, user):
        """Update user location with validated data"""
        latitude = self.validated_data['latitude']
        longitude = self.validated_data['longitude']
        address = self.validated_data.get('address', '')
        
        user.update_location(latitude, longitude, address)
        return user
    
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=8, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=8, required=False, allow_null=True)
    location_address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'phone', 'password', 'confirm_password', 'user_type', 
            'full_name', 'latitude', 'longitude', 'location_address'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'user_type': {'required': False},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        if value:
            phone_regex = re.compile(r'^\+?1?\d{9,15}$')
            if not phone_regex.match(value):
                raise serializers.ValidationError("Invalid phone number format.")
        return value

    def validate_latitude(self, value):
        if value is not None:
            if not (-90 <= float(value) <= 90):
                raise serializers.ValidationError("Latitude must be between -90 and 90 degrees.")
        return value

    def validate_longitude(self, value):
        if value is not None:
            if not (-180 <= float(value) <= 180):
                raise serializers.ValidationError("Longitude must be between -180 and 180 degrees.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        
        # Validate latitude and longitude together
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        
        if (latitude is not None and longitude is None) or (latitude is None and longitude is not None):
            raise serializers.ValidationError("Both latitude and longitude must be provided together or not at all.")
        
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')

        full_name = validated_data.get('full_name', '')
        if not validated_data.get('user_type'):
            validated_data['user_type'] = 'pilgrim'

        # Extract location data
        latitude = validated_data.pop('latitude', None)
        longitude = validated_data.pop('longitude', None)
        location_address = validated_data.pop('location_address', None)

        user = User(
            email=validated_data['email'],
            phone=validated_data.get('phone'),
            full_name=full_name,
            user_type=validated_data['user_type']
        )
        user.set_password(validated_data['password'])
        
        # Set location if provided
        if latitude is not None and longitude is not None:
            user.latitude = latitude
            user.longitude = longitude
            user.location_address = location_address
            user.location_updated_at = timezone.now()
        
        user.save()

        # Generate and send OTP
        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            purpose='email_verification',
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        send_otp(user.email, otp, 'email_verification')

        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)
    user = serializers.HiddenField(default=None)
    login_method = serializers.CharField(read_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        phone = attrs.get('phone')
        password = attrs.get('password')

        if not password or (not email and not phone):
            raise serializers.ValidationError("Must include either email or phone number and password.")

        try:
            user = User.objects.get(email=email) if email else User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")

        if not user.check_password(password):
            raise serializers.ValidationError("Invalid credentials.")

        attrs['user'] = user
        attrs['login_method'] = 'email' if email else 'phone'
        return attrs


class OTPLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        email = data.get("email")
        phone = data.get("phone")

        if not email and not phone:
            raise serializers.ValidationError("Either email or phone must be provided.")
        if email and phone:
            raise serializers.ValidationError("Provide only one of email or phone, not both.")

        return data


class OTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    otp = serializers.CharField(max_length=6)
    purpose = serializers.CharField()

    def validate(self, data):
        if not data.get("email") and not data.get("phone"):
            raise serializers.ValidationError("Email or Phone is required.")
        return data

class PasswordResetSerializer(serializers.Serializer):
    """
    Serializer for password reset request
    """
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for password reset confirmation
    """
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        
        email = attrs.get('email')
        otp = attrs.get('otp')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        
        try:
            otp_verification = OTPVerification.objects.get(
                user=user,
                otp=otp,
                purpose='password_reset',
                is_used=False
            )
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid OTP.")
        
        if otp_verification.is_expired():
            raise serializers.ValidationError("OTP has expired.")
        
        attrs['user'] = user
        attrs['otp_verification'] = otp_verification
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change
    """
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class RefreshTokenSerializer(serializers.Serializer):
    """
    Serializer for token refresh
    """
    refresh = serializers.CharField()


# Service Provider Serializers
class ServiceProviderRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    phone = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=8, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=8, required=False, allow_null=True)
    location_address = serializers.CharField(max_length=500, required=False, allow_blank=True)

    class Meta:
        model = ServiceProviderProfile
        fields = [
            'email', 'phone', 'password', 'confirm_password',
            'business_name', 'business_type', 'business_description',
            'business_logo', 'business_email', 'business_phone', 'business_address',
            'business_city', 'business_state', 'business_country', 'business_pincode',
            'government_id_type', 'government_id_number', 'government_id_document',
            'gst_number', 'gst_certificate', 'trade_license_number',
            'trade_license_document', 'latitude', 'longitude', 'location_address'
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        if value:
            phone_regex = re.compile(r'^\+?1?\d{9,15}$')
            if not phone_regex.match(value):
                raise serializers.ValidationError("Invalid phone number format.")
        return value

    def validate_business_email(self, value):
        if ServiceProviderProfile.objects.filter(business_email=value).exists():
            raise serializers.ValidationError("A service provider with this business email already exists.")
        return value

    def validate_latitude(self, value):
        if value is not None:
            if not (-90 <= float(value) <= 90):
                raise serializers.ValidationError("Latitude must be between -90 and 90 degrees.")
        return value

    def validate_longitude(self, value):
        if value is not None:
            if not (-180 <= float(value) <= 180):
                raise serializers.ValidationError("Longitude must be between -180 and 180 degrees.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        
        # Validate latitude and longitude together
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        
        if (latitude is not None and longitude is None) or (latitude is None and longitude is not None):
            raise serializers.ValidationError("Both latitude and longitude must be provided together or not at all.")
        
        return attrs

    def validate_gst_number(self, value):
        if value and len(value) != 15:
            raise serializers.ValidationError("GST number must be 15 characters long")
        return value

    def create(self, validated_data):
        email = validated_data.pop('email')
        phone = validated_data.pop('phone', None)
        password = validated_data.pop('password')
        validated_data.pop('confirm_password', None)
        
        # Extract location data for user
        latitude = validated_data.pop('latitude', None)
        longitude = validated_data.pop('longitude', None)
        location_address = validated_data.pop('location_address', None)

        # Generate a unique username from email
        username = email.split('@')[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}_{uuid.uuid4().hex[:6]}"

        user = User.objects.create_user(
            username=username,
            email=email,
            phone=phone,
            password=password,
            user_type='provider'
        )
        
        # Set location for provider (typically set once during registration)
        if latitude is not None and longitude is not None:
            user.latitude = latitude
            user.longitude = longitude
            user.location_address = location_address
            user.location_updated_at = timezone.now()
            user.save()

        # Send OTP
        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            purpose='email_verification',
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        send_otp(user.email, otp, 'email_verification')

        # Create profile
        return ServiceProviderProfile.objects.create(user=user, **validated_data)

class ServiceProviderProfileSerializer(serializers.ModelSerializer):
    """
    Service Provider profile serializer
    """
    user = UserProfileSerializer(read_only=True)
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)
    business_type_display = serializers.CharField(source='get_business_type_display', read_only=True)
    
    class Meta:
        model = ServiceProviderProfile
        fields = [
            'id', 'user', 'business_name', 'business_type', 'business_type_display',
            'business_description', 'business_logo', 'business_email', 'business_phone',
            'business_address', 'business_city', 'business_state', 'business_country',
            'business_pincode', 'government_id_type', 'government_id_number',
            'government_id_document', 'gst_number', 'gst_certificate',
            'trade_license_number', 'trade_license_document', 'verification_status',
            'verification_status_display', 'verification_notes', 'verified_by',
            'verified_at', 'total_packages', 'total_leads', 'total_bookings',
            'average_rating', 'total_reviews', 'is_active', 'is_featured',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'verification_status', 'verification_notes', 'verified_by',
            'verified_at', 'total_packages', 'total_leads', 'total_bookings',
            'average_rating', 'total_reviews', 'is_featured', 'created_at', 'updated_at'
        ]
    
    def validate_gst_number(self, value):
        if value and len(value) != 15:
            raise serializers.ValidationError("GST number must be 15 characters long")
        return value
    
    def validate_business_email(self, value):
        if ServiceProviderProfile.objects.filter(business_email=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A service provider with this business email already exists.")
        return value

class ServiceProviderListSerializer(serializers.ModelSerializer):
    """
    Detailed Service Provider serializer for listing
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    user_type = serializers.CharField(source='user.user_type', read_only=True)
    is_user_verified = serializers.BooleanField(source='user.is_verified', read_only=True)

    government_id_document = serializers.FileField(read_only=True)
    gst_certificate = serializers.FileField(read_only=True)
    trade_license_document = serializers.FileField(read_only=True)

    class Meta:
        model = ServiceProviderProfile
        fields = [
            'id','user_email','user_full_name','user_username','user_phone','user_type','is_user_verified',
            'business_name',
            'business_type',
            'business_city',
            'business_state',
            'verification_status',
            'average_rating',
            'business_email',
            'business_phone',
            'total_packages',
            'total_reviews',
            'is_active',
            'is_featured',
            'created_at','government_id_type','government_id_number','government_id_document',
            'gst_number',
            'gst_certificate',
            'trade_license_number',
            'trade_license_document',
        ]

# Activity and Tracking Serializers
class UserActivitySerializer(serializers.ModelSerializer):
    """
    User Activity serializer
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user', 'user_email', 'activity_type', 'activity_type_display',
            'description', 'metadata', 'ip_address', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SavedPackageSerializer(serializers.ModelSerializer):
    """
    Saved Package serializer
    """
    package_title = serializers.CharField(source='package.title', read_only=True)
    package_price = serializers.DecimalField(source='package.price', max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = SavedPackage
        fields = [
            'id', 'user', 'package', 'package_title', 'package_price',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class LoginAttemptSerializer(serializers.ModelSerializer):
    """
    Login Attempt serializer for security tracking
    """
    class Meta:
        model = LoginAttempt
        fields = [
            'id', 'email', 'ip_address', 'user_agent', 'success', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class UserSessionSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    session_key = serializers.CharField(read_only=True)  # Could contain 'JWT', UUID, etc.

    class Meta:
        model = UserSession
        fields = [
            'id', 'user_email', 'session_key', 'device_info',
            'ip_address', 'is_active', 'created_at', 'last_activity'
        ]
        read_only_fields = fields  # Make everything read-only if it's only for viewing



class EmailVerificationSerializer(serializers.Serializer):
    """
    Email verification serializer using OTP
    """
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    
    def validate(self, attrs):
        return OTPVerificationSerializer().validate({
            'email': attrs['email'],
            'otp': attrs['otp'],
            'purpose': 'email_verification'
        })


class PhoneVerificationSerializer(serializers.Serializer):
    """
    Phone verification serializer using OTP
    """
    phone = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6)
    
    def validate_phone(self, value):
        if value:
            phone_regex = re.compile(r'^\+?1?\d{9,15}$')
            if not phone_regex.match(value):
                raise serializers.ValidationError("Invalid phone number format.")
        return value
    
    def validate(self, attrs):
        try:
            user = User.objects.get(phone=attrs['phone'])
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this phone number does not exist.")
        
        return OTPVerificationSerializer().validate({
            'email': user.email,
            'otp': attrs['otp'],
            'purpose': 'phone_verification'
        })


# Admin Serializers
class UserManagementSerializer(serializers.ModelSerializer):
    """
    User management serializer for admin operations
    """
    user_type_display = serializers.CharField(source='get_user_type_display', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'phone', 'user_type', 'user_type_display',
            'is_verified', 'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login', 'created_at', 'updated_at']


class BulkUserActionSerializer(serializers.Serializer):
    """
    Bulk user action serializer for admin operations
    """
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False
    )
    action = serializers.ChoiceField(choices=[
        ('activate', 'Activate'),
        ('deactivate', 'Deactivate'),
        ('verify', 'Verify'),
        ('unverify', 'Unverify'),
    ])
    
    def validate_user_ids(self, value):
        existing_users = User.objects.filter(id__in=value).count()
        if existing_users != len(value):
            raise serializers.ValidationError("Some user IDs are invalid.")
        return value