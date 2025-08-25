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
    Lightweight serializer for service lists with conditional fields
    """
    provider = ServiceProviderProfileSerializer(read_only=True)
    provider_company = serializers.CharField(source='provider.company_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    featured_image_url = serializers.SerializerMethodField()
    average_rating = serializers.ReadOnlyField()
    total_reviews = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    is_available_today = serializers.SerializerMethodField()
    service_specific_fields = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            'id', 'title', 'short_description', 'service_type', 'category_name',
            'price', 'original_price', 'price_currency', 'price_per', 'discount_percentage',
            'duration', 'city', 'state', 'country', 'featured_image_url', 'provider', 
            'provider_company', 'average_rating', 'total_reviews', 'views_count',
            'is_featured', 'is_popular', 'is_premium', 'status', 'slug',
            'is_available_today', 'service_specific_fields', 'created_at', 'updated_at'
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
    
    def get_service_specific_fields(self, obj):
        """Return service-specific fields based on service type"""
        return obj.get_service_specific_fields()

class ServiceDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for single service view with all conditional fields
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
    service_specific_fields = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            # Basic fields
            'id', 'title', 'description', 'short_description', 'service_type',
            'category', 'price', 'original_price', 'price_currency', 'price_per',
            'discount_percentage', 'duration', 'duration_in_days', 'city', 'state', 
            'country', 'available_from', 'available_to', 'is_always_available',
            'images', 'featured_image', 'status', 'verified_at', 'features',
            'inclusions', 'exclusions', 'contact_phone', 'contact_email',
            'booking_requirements', 'views_count', 'leads_count', 'bookings_count',
            'slug', 'meta_title', 'meta_description', 'is_featured', 'is_popular', 
            'is_premium', 'provider', 'availabilities', 'faqs', 'average_rating', 
            'total_reviews', 'has_active_subscription', 'service_specific_fields',
            
            # Air Ticket specific fields
            'departure_date', 'return_date', 'departure_city', 'arrival_city',
            'airline', 'seat_availability', 'flight_from', 'flight_to', 'flight_class',
            
            # Zamzam Water specific fields
            'water_capacity', 'water_capacity_liters', 'water_source', 'packaging_type',
            
            # Hotel specific fields
            'hotel_star_rating', 'hotel_room_type', 
            
            # Transport specific fields
            'transport_type', 'vehicle_capacity', 'pickup_location', 'drop_location',
            
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'views_count', 'leads_count', 'bookings_count', 'average_rating',
            'total_reviews', 'discount_percentage', 'has_active_subscription',
            'service_specific_fields', 'created_at', 'updated_at'
        ]
    
    def get_has_active_subscription(self, obj):
        return obj.get_provider_subscription_status()
    
    def get_service_specific_fields(self, obj):
        """Return service-specific fields based on service type"""
        return obj.get_service_specific_fields()

class ServiceCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating services with conditional field validation
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
            # Basic fields
            'title', 'description', 'short_description', 'service_type',
            'category', 'price', 'original_price', 'price_currency', 'price_per',
            'duration', 'duration_in_days', 'city', 'state', 'country',
            'available_from', 'available_to', 'is_always_available',
            'images', 'featured_image', 'features', 'inclusions', 'exclusions',
            'contact_phone', 'contact_email', 'booking_requirements',
            'meta_title', 'meta_description',
            
            # Air Ticket specific fields
            'departure_date', 'return_date', 'departure_city', 'arrival_city',
            'airline', 'seat_availability', 'flight_from', 'flight_to', 'flight_class',
            
            # Zamzam Water specific fields
            'water_capacity', 'water_capacity_liters', 'water_source', 'packaging_type',
            
            # Hotel specific fields
            'hotel_star_rating', 'hotel_room_type', 
            
            # Transport specific fields
            'transport_type', 'vehicle_capacity', 'pickup_location', 'drop_location'
        ]
    
    def validate(self, data):
        """
        Validate service data with conditional field requirements
        """
        service_type = data.get('service_type')
        
        # Air Ticket validation
        if service_type == ServiceType.AIR_TICKET:
            required_fields = {
                'flight_from': 'Flight origin is required for Air Ticket services',
                'flight_to': 'Flight destination is required for Air Ticket services',
                'departure_date': 'Departure date is required for Air Ticket services'
            }
            
            for field, error_msg in required_fields.items():
                if not data.get(field):
                    raise serializers.ValidationError({field: error_msg})
            
            # Validate dates
            if data.get('departure_date') and data.get('return_date'):
                if data['departure_date'] >= data['return_date']:
                    raise serializers.ValidationError({
                        'return_date': "Return date must be after departure date"
                    })
        
        # Zamzam Water validation
        elif service_type == ServiceType.JAM_JAM_WATER:
            if not data.get('water_capacity'):
                raise serializers.ValidationError({
                    'water_capacity': 'Water capacity is required for Zamzam Water services'
                })
        
        # Hotel validation
        elif service_type == ServiceType.HOTEL:
            if not data.get('hotel_room_type'):
                raise serializers.ValidationError({
                    'hotel_room_type': 'Room type is required for Hotel services'
                })
            
            # Validate star rating
            if data.get('hotel_star_rating'):
                if not (1 <= data['hotel_star_rating'] <= 5):
                    raise serializers.ValidationError({
                        'hotel_star_rating': 'Star rating must be between 1 and 5'
                    })
        
        # Transport validation
        elif service_type == ServiceType.TRANSPORT:
            required_fields = {
                'transport_type': 'Transport type is required for Transport services',
                'pickup_location': 'Pickup location is required for Transport services'
            }
            
            for field, error_msg in required_fields.items():
                if not data.get(field):
                    raise serializers.ValidationError({field: error_msg})
            
            # Validate vehicle capacity
            if data.get('vehicle_capacity') and data['vehicle_capacity'] <= 0:
                raise serializers.ValidationError({
                    'vehicle_capacity': 'Vehicle capacity must be greater than 0'
                })
        
        # General price validation
        if data.get('original_price') and data.get('price'):
            if data['original_price'] < data['price']:
                raise serializers.ValidationError({
                    'original_price': "Original price cannot be less than current price"
                })
        
        # Validate water capacity liters
        if data.get('water_capacity_liters') and data['water_capacity_liters'] <= 0:
            raise serializers.ValidationError({
                'water_capacity_liters': 'Water capacity must be greater than 0'
            })
        
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
        # Require rejection_reason if status is rejected
        if data.get('status') == ServiceStatus.REJECTED and not data.get('rejection_reason'):
            raise serializers.ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting a service.'
            })
        return data

    def update(self, instance, validated_data):
        """
        Update service status and set verification details automatically
        """
        status = validated_data.get('status')

        if status == ServiceStatus.VERIFIED:
            instance.verified_by = self.context['request'].user
            instance.verified_at = timezone.now()
            instance.rejection_reason = ''  # Clear rejection reason if approved

        elif status == ServiceStatus.REJECTED:
            instance.rejection_reason = validated_data.get('rejection_reason', '')

        instance.status = status
        instance.save(update_fields=['status', 'verified_by', 'verified_at', 'rejection_reason'])
        return instance

class ServiceViewSerializer(serializers.ModelSerializer):
    """
    Serializer for service view tracking
    """
    service_title = serializers.CharField(source='service.title', read_only=True)
    provider_name = serializers.CharField(source='provider.get_full_name', read_only=True)
    
    class Meta:
        model = ServiceView
        fields = [
            'id', 'service', 'service_title', 'provider', 'provider_name',
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
    Enhanced serializer for service search parameters with conditional fields
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
    
    # Air Ticket specific search fields
    flight_from = serializers.CharField(
        required=False,
        help_text="Flight origin city/airport"
    )
    flight_to = serializers.CharField(
        required=False,
        help_text="Flight destination city/airport"
    )
    departure_city = serializers.CharField(
        required=False,
        help_text="Departure city (legacy field)"
    )
    arrival_city = serializers.CharField(
        required=False,
        help_text="Arrival city (legacy field)"
    )
    departure_date = serializers.DateField(
        required=False,
        help_text="Departure date"
    )
    return_date = serializers.DateField(
        required=False,
        help_text="Return date"
    )
    flight_class = serializers.ChoiceField(
        choices=[
            ('economy', 'Economy'),
            ('business', 'Business'),
            ('first', 'First Class'),
            ('premium_economy', 'Premium Economy'),
        ],
        required=False,
        help_text="Flight class"
    )
    airline = serializers.CharField(
        required=False,
        help_text="Airline name"
    )
    
    # Zamzam Water specific search fields
    min_water_capacity = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        help_text="Minimum water capacity in liters"
    )
    max_water_capacity = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        help_text="Maximum water capacity in liters"
    )
    packaging_type = serializers.ChoiceField(
        choices=[
            ('bottle', 'Bottle'),
            ('container', 'Container'),
            ('can', 'Can'),
            ('pouch', 'Pouch'),
        ],
        required=False,
        help_text="Packaging type for water"
    )
    
    # Hotel specific search fields
    min_star_rating = serializers.IntegerField(
        min_value=1,
        max_value=5,
        required=False,
        help_text="Minimum hotel star rating"
    )
    max_star_rating = serializers.IntegerField(
        min_value=1,
        max_value=5,
        required=False,
        help_text="Maximum hotel star rating"
    )
    hotel_room_type = serializers.CharField(
        required=False,
        help_text="Hotel room type"
    )
    
    # Transport specific search fields
    transport_type = serializers.ChoiceField(
        choices=[
            ('bus', 'Bus'),
            ('car', 'Car'),
            ('taxi', 'Taxi'),
            ('van', 'Van'),
            ('coach', 'Coach'),
        ],
        required=False,
        help_text="Type of transport"
    )
    min_vehicle_capacity = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text="Minimum vehicle capacity"
    )
    max_vehicle_capacity = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text="Maximum vehicle capacity"
    )
    pickup_location = serializers.CharField(
        required=False,
        help_text="Pickup location"
    )
    drop_location = serializers.CharField(
        required=False,
        help_text="Drop location"
    )
    
    # General filters
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
    has_availability = serializers.BooleanField(
        required=False,
        help_text="Filter services with availability"
    )
    ordering = serializers.ChoiceField(
        choices=[
            'price', '-price', 'created_at', '-created_at',
            'views_count', '-views_count', 'title', '-title',
            'departure_date', '-departure_date', 'hotel_star_rating', 
            '-hotel_star_rating', 'water_capacity_liters', '-water_capacity_liters'
        ],
        required=False,
        default='-created_at',
        help_text="Order results by"
    )

# Additional specialized serializers for specific service types

class AirTicketServiceSerializer(ServiceDetailSerializer):
    """
    Specialized serializer for Air Ticket services
    """
    class Meta(ServiceDetailSerializer.Meta):
        fields = [field for field in ServiceDetailSerializer.Meta.fields 
                 if not any(field.startswith(prefix) for prefix in 
                          ['water_', 'hotel_', 'transport_', 'vehicle_', 'pickup_', 'drop_', 'packaging_'])]

class ZamzamWaterServiceSerializer(ServiceDetailSerializer):
    """
    Specialized serializer for Zamzam Water services
    """
    class Meta(ServiceDetailSerializer.Meta):
        fields = [field for field in ServiceDetailSerializer.Meta.fields 
                 if not any(field.startswith(prefix) for prefix in 
                          ['flight_', 'departure_', 'return_', 'arrival_', 'airline', 'seat_', 
                           'hotel_', 'transport_', 'vehicle_', 'pickup_', 'drop_'])]

class HotelServiceSerializer(ServiceDetailSerializer):
    """
    Specialized serializer for Hotel services
    """
    class Meta(ServiceDetailSerializer.Meta):
        fields = [field for field in ServiceDetailSerializer.Meta.fields 
                 if not any(field.startswith(prefix) for prefix in 
                          ['flight_', 'departure_', 'return_', 'arrival_', 'airline', 'seat_',
                           'water_', 'transport_', 'vehicle_', 'pickup_', 'drop_', 'packaging_'])]

class TransportServiceSerializer(ServiceDetailSerializer):
    """
    Specialized serializer for Transport services
    """
    class Meta(ServiceDetailSerializer.Meta):
        fields = [field for field in ServiceDetailSerializer.Meta.fields 
                 if not any(field.startswith(prefix) for prefix in 
                          ['flight_', 'departure_', 'return_', 'arrival_', 'airline', 'seat_',
                           'water_', 'hotel_', 'packaging_'])]