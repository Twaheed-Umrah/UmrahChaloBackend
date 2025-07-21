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

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'phone', 'user_type', 'user_type_display',
            'full_name', 'is_verified', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_type', 'is_verified', 'created_at', 'updated_at']

    def get_full_name(self, obj):
        return obj.full_name or f"{obj.first_name} {obj.last_name}".strip() or obj.username

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

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'phone', 'password', 'confirm_password', 'user_type', 'full_name']
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

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')

        full_name = validated_data.get('full_name', '')
        if not validated_data.get('user_type'):
            validated_data['user_type'] = 'pilgrim'

        user = User(
            email=validated_data['email'],
            phone=validated_data.get('phone'),
            full_name=full_name,
            user_type=validated_data['user_type']
        )
        user.set_password(validated_data['password'])
        user.save()

        # Generate and send OTP
        from .models import OTPVerification  # Adjust path if needed
        from apps.core.utils import generate_otp, send_otp  # Ensure you have these utils

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
    """
    Serializer for user login - works for all user types
    """
    email = serializers.EmailField()
    password = serializers.CharField()
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError("Invalid credentials.")
            if not user.is_active:
                raise serializers.ValidationError("User account is disabled.")
            attrs['user'] = user
        else:
            raise serializers.ValidationError("Must include email and password.")
        
        return attrs


class OTPLoginSerializer(serializers.Serializer):
    """
    Serializer for OTP-based login
    """
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        return value


class OTPVerificationSerializer(serializers.Serializer):
    """
    Serializer for OTP verification
    """
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    purpose = serializers.CharField()
    
    def validate(self, attrs):
        email = attrs.get('email')
        otp = attrs.get('otp')
        purpose = attrs.get('purpose')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        
        try:
            otp_verification = OTPVerification.objects.get(
                user=user,
                otp=otp,
                purpose=purpose,
                is_used=False
            )
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid OTP.")
        
        if otp_verification.is_expired():
            raise serializers.ValidationError("OTP has expired.")
        
        attrs['user'] = user
        attrs['otp_verification'] = otp_verification
        return attrs


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


class ServiceProviderRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    phone = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = ServiceProviderProfile
        fields = [
            'email', 'phone', 'password', 'confirm_password',
            'business_name', 'business_type', 'business_description',
            'business_logo', 'business_email', 'business_phone', 'business_address',
            'business_city', 'business_state', 'business_country', 'business_pincode',
            'government_id_type', 'government_id_number', 'government_id_document',
            'gst_number', 'gst_certificate', 'trade_license_number',
            'trade_license_document'
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

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
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


class ServiceProviderListSerializer(serializers.ModelSerializer):
    """
    Simplified Service Provider serializer for listing
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = ServiceProviderProfile
        fields = [
            'id', 'user_email', 'user_username', 'business_name', 'business_type',
            'business_city', 'business_state', 'verification_status', 'average_rating',
            'total_packages', 'total_reviews', 'is_active', 'is_featured', 'created_at'
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
    """
    User Session serializer for session management
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = UserSession
        fields = [
            'id', 'user', 'user_email', 'session_key', 'device_info',
            'ip_address', 'is_active', 'created_at', 'last_activity'
        ]
        read_only_fields = ['id', 'created_at', 'last_activity']


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