from rest_framework import serializers
from django.db import transaction
from apps.services.serializers import ServiceListSerializer
from apps.authentication.serializers import ServiceProviderProfileSerializer
from .models import (
    Package, PackageService, PackageInclusion, PackageExclusion,
    PackageItinerary, PackageImage, PackagePolicy, PackageAvailability
)
import base64
import uuid
from django.core.files.base import ContentFile
from apps.authentication.models import ServiceProviderProfile
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

class PackageImageSerializer(serializers.ModelSerializer):
    """Serializer for package images"""
    
    class Meta:
        model = PackageImage
        fields = ['id', 'image', 'caption', 'is_featured', 'order']
        read_only_fields = ['id']


class PackageInclusionSerializer(serializers.ModelSerializer):
    """Serializer for package inclusions"""
    
    class Meta:
        model = PackageInclusion
        fields = ['id', 'title', 'description', 'is_highlighted', 'order']
        read_only_fields = ['id']


class PackageExclusionSerializer(serializers.ModelSerializer):
    """Serializer for package exclusions"""
    
    class Meta:
        model = PackageExclusion
        fields = ['id', 'title', 'description', 'order']
        read_only_fields = ['id']


class PackageItinerarySerializer(serializers.ModelSerializer):
    """Serializer for package itinerary"""
    
    class Meta:
        model = PackageItinerary
        fields = [
            'id', 'day_number', 'title', 'description', 
            'location', 'activities'
        ]
        read_only_fields = ['id']


class PackagePolicySerializer(serializers.ModelSerializer):
    """Serializer for package policies"""
    
    class Meta:
        model = PackagePolicy
        fields = ['id', 'policy_type', 'title', 'content', 'order']
        read_only_fields = ['id']


class PackageAvailabilitySerializer(serializers.ModelSerializer):
    """Serializer for package availability"""
    
    class Meta:
        model = PackageAvailability
        fields = [
            'id', 'date', 'available_slots', 'price_adjustment',
            'is_available', 'color_code'
        ]
        read_only_fields = ['id']


class PackageServiceSerializer(serializers.ModelSerializer):
    """Serializer for package services relationship"""
    service = ServiceListSerializer(read_only=True)
    service_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = PackageService
        fields = [
            'id', 'service', 'service_id', 'is_included', 'is_optional',
            'additional_price', 'quantity', 'notes'
        ]
        read_only_fields = ['id']


class PackageListSerializer(serializers.ModelSerializer):
    """Serializer for listing packages (minimal data)"""
    provider = ServiceProviderProfileSerializer(read_only=True)
    final_price = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()
    availability_percentage = serializers.ReadOnlyField()
    featured_image = serializers.SerializerMethodField()

    def get_featured_image(self, obj):
        request = self.context.get('request')
        if obj.featured_image and obj.featured_image.image:
            return request.build_absolute_uri(obj.featured_image.image.url) if request else obj.featured_image.image.url
        return None
    class Meta:
        model = Package
        fields = [
            'id', 'name', 'slug', 'description', 'package_type',
            'provider', 'base_price', 'discounted_price', 'final_price',
            'duration_days', 'start_date', 'end_date', 'booking_deadline',
            'max_capacity', 'current_bookings', 'availability_percentage',
            'city', 'state', 'country',
            'is_available', 'status', 'featured_image', 'rating',
            'reviews_count', 'views_count', 'leads_count', 'is_featured',
            'is_active', 'package_services', 'inclusions', 'exclusions',
            'itineraries', 'images', 'policies', 'availabilities',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'slug', 'final_price', 'is_available',
            'availability_percentage', 'views_count', 'leads_count',
            'rating', 'reviews_count', 'created_at', 'updated_at'
        ]


class PackageDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed package view"""
    provider = ServiceProviderProfileSerializer(read_only=True)
    package_services = PackageServiceSerializer(many=True, read_only=True)
    inclusions = PackageInclusionSerializer(many=True, read_only=True)
    exclusions = PackageExclusionSerializer(many=True, read_only=True)
    itineraries = PackageItinerarySerializer(many=True, read_only=True)
    policies = PackagePolicySerializer(many=True, read_only=True)
    availabilities = PackageAvailabilitySerializer(many=True, read_only=True)
    final_price = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()
    availability_percentage = serializers.ReadOnlyField()
    featured_image = serializers.SerializerMethodField()

    def get_featured_image(self, obj):
        request = self.context.get('request')
        if obj.featured_image and obj.featured_image.image:
            return request.build_absolute_uri(obj.featured_image.image.url) if request else obj.featured_image.image.url
        return None
    
    class Meta:
        model = Package
        fields = [
            'id', 'name', 'slug', 'description', 'package_type',
            'provider', 'base_price', 'discounted_price', 'final_price',
            'duration_days', 'start_date', 'end_date', 'booking_deadline',
            'max_capacity', 'current_bookings', 'availability_percentage',
            'city', 'state', 'country',
            'is_available', 'status', 'featured_image', 'rating',
            'reviews_count', 'views_count', 'leads_count', 'is_featured',
            'is_active', 'package_services', 'inclusions', 'exclusions',
            'itineraries', 'images', 'policies', 'availabilities',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'slug', 'final_price', 'is_available',
            'availability_percentage', 'views_count', 'leads_count',
            'rating', 'reviews_count', 'created_at', 'updated_at'
        ]


class PackageCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating packages"""
    services = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    inclusions = PackageInclusionSerializer(many=True, required=False)
    exclusions = PackageExclusionSerializer(many=True, required=False)
    itineraries = PackageItinerarySerializer(many=True, required=False)
    policies = PackagePolicySerializer(many=True, required=False)
    availabilities = PackageAvailabilitySerializer(many=True, required=False)
    
    class Meta:
        model = Package
        fields = [
            'id', 'name', 'description', 'package_type', 'base_price',
            'discounted_price', 'duration_days', 'start_date', 'end_date',
            'city', 'state', 'country',
            'booking_deadline', 'max_capacity', 'featured_image',
            'is_active', 'services', 'inclusions', 'exclusions',
            'itineraries', 'policies', 'availabilities'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        """Validate package data"""
        # Validate dates
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        booking_deadline = data.get('booking_deadline')
        
        if start_date and end_date and start_date >= end_date:
            raise serializers.ValidationError(
                "End date must be after start date"
            )
        
        if booking_deadline and start_date and booking_deadline >= start_date:
            raise serializers.ValidationError(
                "Booking deadline must be before start date"
            )
        
        # Validate pricing
        base_price = data.get('base_price')
        discounted_price = data.get('discounted_price')
        
        if (discounted_price and base_price and 
            discounted_price >= base_price):
            raise serializers.ValidationError(
                "Discounted price must be less than base price"
            )
        
        return data
    
    def create(self, validated_data):
        """Create package with related objects"""
        services_data = validated_data.pop('services', [])
        inclusions_data = validated_data.pop('inclusions', [])
        exclusions_data = validated_data.pop('exclusions', [])
        itineraries_data = validated_data.pop('itineraries', [])
        policies_data = validated_data.pop('policies', [])
        availabilities_data = validated_data.pop('availabilities', [])
        
        # Set provider from request user
        user = self.context['request'].user
        provider_profile = ServiceProviderProfile.objects.get(user=user)
        validated_data['provider'] = provider_profile
        
        with transaction.atomic():
            # Create package
            package = Package.objects.create(**validated_data)
            
            # Create related objects
            self._create_services(package, services_data)
            self._create_inclusions(package, inclusions_data)
            self._create_exclusions(package, exclusions_data)
            self._create_itineraries(package, itineraries_data)
            self._create_policies(package, policies_data)
            self._create_availabilities(package, availabilities_data)
        
        return package
    
    def update(self, instance, validated_data):
        """Update package with related objects"""
        services_data = validated_data.pop('services', None)
        inclusions_data = validated_data.pop('inclusions', None)
        exclusions_data = validated_data.pop('exclusions', None)
        itineraries_data = validated_data.pop('itineraries', None)
        policies_data = validated_data.pop('policies', None)
        availabilities_data = validated_data.pop('availabilities', None)
        
        with transaction.atomic():
            # Update package
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            
            # Update related objects if provided
            if services_data is not None:
                instance.package_services.all().delete()
                self._create_services(instance, services_data)
            
            if inclusions_data is not None:
                instance.inclusions.all().delete()
                self._create_inclusions(instance, inclusions_data)
            
            if exclusions_data is not None:
                instance.exclusions.all().delete()
                self._create_exclusions(instance, exclusions_data)
            
            if itineraries_data is not None:
                instance.itineraries.all().delete()
                self._create_itineraries(instance, itineraries_data)
            
            if policies_data is not None:
                instance.policies.all().delete()
                self._create_policies(instance, policies_data)
            
            if availabilities_data is not None:
                instance.availabilities.all().delete()
                self._create_availabilities(instance, availabilities_data)
        
        return instance
    
    def _create_services(self, package, services_data):
        """Create package services"""
        for service_data in services_data:
            PackageService.objects.create(package=package, **service_data)
    
    def _create_inclusions(self, package, inclusions_data):
        """Create package inclusions"""
        for inclusion_data in inclusions_data:
            PackageInclusion.objects.create(package=package, **inclusion_data)
    
    def _create_exclusions(self, package, exclusions_data):
        """Create package exclusions"""
        for exclusion_data in exclusions_data:
            PackageExclusion.objects.create(package=package, **exclusion_data)
    
    def _create_itineraries(self, package, itineraries_data):
        """Create package itineraries"""
        for itinerary_data in itineraries_data:
            PackageItinerary.objects.create(package=package, **itinerary_data)
    
    def _create_policies(self, package, policies_data):
        """Create package policies"""
        for policy_data in policies_data:
            PackagePolicy.objects.create(package=package, **policy_data)
    
    def _create_availabilities(self, package, availabilities_data):
        """Create package availabilities"""
        for availability_data in availabilities_data:
            PackageAvailability.objects.create(package=package, **availability_data)


class PackageStatusUpdateSerializer(serializers.ModelSerializer):
    """Serializer for admin to update package status"""
    rejection_reason = serializers.CharField(
        required=False, 
        allow_blank=True,
        max_length=1000
    )
    
    class Meta:
        model = Package
        fields = ['status', 'rejection_reason']
    
    def validate(self, data):
        status = data.get('status')
        rejection_reason = data.get('rejection_reason')
        
        if status == 'rejected' and not rejection_reason:
            raise serializers.ValidationError(
                "Rejection reason is required when rejecting a package"
            )
        
        return data
    
    def update(self, instance, validated_data):
        """Update package status with verification details"""
        status = validated_data.get('status')
        
        if status in ['verified', 'published', 'rejected']:
            from django.utils import timezone
            instance.verified_by = self.context['request'].user
            instance.verified_at = timezone.now()
        
        return super().update(instance, validated_data)