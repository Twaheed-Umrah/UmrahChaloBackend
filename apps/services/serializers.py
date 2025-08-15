from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    ServiceCategory, ServiceImage, Service, ServiceAvailability, 
    ServiceFAQ, ServiceView, ServiceType, ServiceStatus
)
from apps.authentication.serializers import UserProfileSerializer
import base64
import uuid
from django.core.files.base import ContentFile
from apps.authentication.models import ServiceProviderProfile
from apps.authentication.serializers import ServiceProviderProfileSerializer
User = get_user_model()
class Base64ImageField(serializers.ImageField):
    """
    A Django REST framework field for handling image-uploads through raw post data.
    It uses base64 for encoding and decoding the contents of the file.
    """
    
    def to_internal_value(self, data):
        # Check if this is a base64 string
        if isinstance(data, str) and data.startswith('data:image'):
            try:
                # Parse the base64 string
                header, imgstr = data.split(';base64,')
                ext = header.split('/')[1]  # Get extension from data:image/jpeg
                
                # Handle different image formats
                if ext == 'jpeg':
                    ext = 'jpg'
                
                # Generate a unique filename
                filename = f"{uuid.uuid4()}.{ext}"
                
                # Decode the base64 string
                decoded_data = base64.b64decode(imgstr)
                data = ContentFile(decoded_data, name=filename)
                
            except (ValueError, IndexError) as e:
                raise serializers.ValidationError(f"Invalid base64 image data: {str(e)}")
        
        return super().to_internal_value(data)
    
    def to_representation(self, value):
        """Return full URL for the image"""
        if not value:
            return None
        
        # Check if the file actually exists
        try:
            if not value.storage.exists(value.name):
                return None
        except Exception:
            return None
        
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(value.url)
        return value.url

class ServiceCategorySerializer(serializers.ModelSerializer):
    services_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceCategory
        fields = [
            'id', 'name', 'description', 'icon', 'is_active', 
            'display_order', 'services_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_services_count(self, obj):
        return obj.services.filter(status=ServiceStatus.PUBLISHED).count()

class ServiceImageSerializer(serializers.ModelSerializer):
    image = Base64ImageField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = ServiceImage
        fields = [
            'id', 'name', 'image', 'category', 'category_name', 
            'alt_text', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
class ServiceAvailabilitySerializer(serializers.ModelSerializer):
    remaining_slots = serializers.ReadOnlyField()
    is_fully_booked = serializers.ReadOnlyField()
    effective_price = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceAvailability
        fields = [
            'id', 'date', 'available_slots', 'booked_slots', 'remaining_slots',
            'price_override', 'effective_price', 'is_available', 'is_fully_booked'
        ]
    
    def get_effective_price(self, obj):
        return obj.price_override if obj.price_override else obj.service.price

class ServiceFAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceFAQ
        fields = [
            'id', 'question', 'answer', 'display_order', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class ServiceListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for service lists
    """
    provider = ServiceProviderProfileSerializer(read_only=True)
    provider_company = serializers.CharField(source='provider.company_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    featured_image_url = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()
    total_reviews = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_available_today = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            'id', 'title', 'short_description', 'service_type', 'category_name',
            'price', 'original_price', 'price_currency', 'price_per', 'discount_percentage',
            'duration', 'city', 'state', 'country','featured_image_url', 'provider', 
            'provider_company', 'average_rating', 'total_reviews', 'views_count',
            'is_featured', 'is_popular', 'is_premium', 'status', 'slug',
            'departure_date', 'return_date', 'departure_city', 'arrival_city',
            'is_available_today', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_featured_image_url(self, obj):
        if obj.featured_image and obj.featured_image.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.featured_image.image.url)
            return obj.featured_image.image.url
        return None
    
    def get_is_available_today(self, obj):
        return obj.is_available_on_date(timezone.now().date())

class ServiceDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for single service view
    """
    provider = ServiceProviderProfileSerializer(read_only=True)
    category = ServiceCategorySerializer(read_only=True)
    images = ServiceImageSerializer(many=True, read_only=True)
    featured_image = ServiceImageSerializer(read_only=True)
    availabilities = ServiceAvailabilitySerializer(many=True, read_only=True)
    faqs = ServiceFAQSerializer(many=True, read_only=True)
    average_rating = serializers.ReadOnlyField()
    total_reviews = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    has_active_subscription = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            'id', 'title', 'description', 'short_description', 'service_type',
            'category', 'price', 'original_price', 'price_currency', 'price_per',
            'discount_percentage', 'duration', 'duration_in_days', 'city', 'state', 
            'country', 'available_from', 'available_to', 'is_always_available',
            'images', 'featured_image', 'status', 'verified_at', 'features',
            'inclusions', 'exclusions', 'contact_phone', 'contact_email',
            'booking_requirements', 'views_count', 'leads_count', 'bookings_count',
            'slug', 'meta_title', 'meta_description', 'departure_date', 'return_date',
            'departure_city', 'arrival_city', 'airline', 'seat_availability',
            'is_featured', 'is_popular', 'is_premium', 'provider', 'availabilities',
            'faqs', 'average_rating', 'total_reviews', 'has_active_subscription',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'views_count', 'leads_count', 'bookings_count', 'average_rating',
            'total_reviews', 'discount_percentage', 'has_active_subscription',
            'created_at', 'updated_at'
        ]
    
    def get_has_active_subscription(self, obj):
        return obj.get_provider_subscription_status()

class ServiceCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating services
    """
    images = serializers.PrimaryKeyRelatedField(
        queryset=ServiceImage.objects.filter(is_active=True),
        many=True,
        required=False
    )
    featured_image = serializers.PrimaryKeyRelatedField(
        queryset=ServiceImage.objects.filter(is_active=True),
        required=False
    )
    
    class Meta:
        model = Service
        fields = [
            'title', 'description', 'short_description', 'service_type',
            'category', 'price', 'original_price', 'price_currency', 'price_per',
            'duration', 'duration_in_days', 'city', 'state', 'country',
            'available_from', 'available_to', 'is_always_available',
            'images', 'featured_image', 'features', 'inclusions', 'exclusions',
            'contact_phone', 'contact_email', 'booking_requirements',
            'meta_title', 'meta_description', 'departure_date', 'return_date',
            'departure_city', 'arrival_city', 'airline', 'seat_availability'
        ]
    
    def validate(self, data):
        """
        Validate service data
        """
        service_type = data.get('service_type')
        
        # Validate air ticket specific fields
        if service_type == ServiceType.AIR_TICKET:
            required_fields = ['departure_date', 'departure_city', 'arrival_city']
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError(
                        f"{field} is required for Air Ticket services"
                    )
            
            # Validate dates
            if data.get('departure_date') and data.get('return_date'):
                if data['departure_date'] >= data['return_date']:
                    raise serializers.ValidationError(
                        "Return date must be after departure date"
                    )
        
        # Validate price
        if data.get('original_price') and data.get('price'):
            if data['original_price'] < data['price']:
                raise serializers.ValidationError(
                    "Original price cannot be less than current price"
                )
        
        return data
    
    def create(self, validated_data):
        """
        Create service with current user as provider
        """
        user = self.context['request'].user
        try:
           validated_data['provider'] = user.service_provider_profile
        except ServiceProviderProfile.DoesNotExist:
            raise serializers.ValidationError("Only providers can create services.")

        return super().create(validated_data)

class ServiceStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating service status (Admin only)
    """
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = Service
        fields = ['status', 'rejection_reason']
    
    def validate(self, data):
        if data.get('status') == ServiceStatus.REJECTED and not data.get('rejection_reason'):
            raise serializers.ValidationError(
                "Rejection reason is required when rejecting a service"
            )
        return data
    
    def update(self, instance, validated_data):
        """
        Update service status and set verification details
        """
        if validated_data.get('status') == ServiceStatus.VERIFIED:
            validated_data['verified_by'] = self.context['request'].user
            validated_data['verified_at'] = timezone.now()
        
        return super().update(instance, validated_data)

class ServiceViewSerializer(serializers.ModelSerializer):
    """
    Serializer for service view tracking
    """
    service_title = serializers.CharField(source='service.title', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = ServiceView
        fields = [
            'id', 'service', 'service_title', 'user', 'user_name',
            'ip_address', 'user_agent', 'viewed_at'
        ]
        read_only_fields = ['viewed_at']

class ServiceStatsSerializer(serializers.Serializer):
    """
    Serializer for service statistics
    """
    total_services = serializers.IntegerField()
    published_services = serializers.IntegerField()
    pending_services = serializers.IntegerField()
    total_views = serializers.IntegerField()
    total_leads = serializers.IntegerField()
    popular_categories = serializers.ListField()
    recent_services = ServiceListSerializer(many=True)

class ServiceSearchSerializer(serializers.Serializer):
    """
    Serializer for service search parameters
    """
    q = serializers.CharField(required=False, help_text="Search query")
    service_type = serializers.ChoiceField(
        choices=ServiceType.choices, 
        required=False,
        help_text="Filter by service type"
    )
    category = serializers.IntegerField(
        required=False,
        help_text="Filter by category ID"
    )
    city = serializers.CharField(
        required=False,
        help_text="Filter by city"
    )
    min_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        help_text="Minimum price"
    )
    max_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        help_text="Maximum price"
    )
    date_from = serializers.DateField(
        required=False,
        help_text="Available from date"
    )
    date_to = serializers.DateField(
        required=False,
        help_text="Available to date"
    )
    departure_city = serializers.CharField(
        required=False,
        help_text="Departure city (for air tickets)"
    )
    arrival_city = serializers.CharField(
        required=False,
        help_text="Arrival city (for air tickets)"
    )
    departure_date = serializers.DateField(
        required=False,
        help_text="Departure date (for air tickets)"
    )
    is_featured = serializers.BooleanField(
        required=False,
        help_text="Filter featured services"
    )
    is_popular = serializers.BooleanField(
        required=False,
        help_text="Filter popular services"
    )
    min_rating = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=5,
        help_text="Minimum rating"
    )
    ordering = serializers.ChoiceField(
        choices=[
            'price', '-price', 'created_at', '-created_at',
            'views_count', '-views_count', 'title', '-title'
        ],
        required=False,
        default='-created_at',
        help_text="Order results by"
    )