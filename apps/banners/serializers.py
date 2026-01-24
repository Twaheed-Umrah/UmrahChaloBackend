from rest_framework import serializers
from .models import Banner, PopularDestination, DestinationImage, VisitorTip
from django.contrib.auth import get_user_model

User = get_user_model()

class BannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    provider_info = serializers.SerializerMethodField()
    relevance_score = serializers.SerializerMethodField()
    
    class Meta:
        model = Banner
        fields = [
            'id', 'title', 'description', 'image_url', 
            'banner_type', 'provider_info', 'provider_business_type',
            'target_city', 'target_state', 'target_country','image',
            'relevance_score', 'external_url', 'display_priority', 
            'priority_weight', 'display_order', 'start_date', 'end_date'
        ]
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None
    
    def get_provider_info(self, obj):
        if obj.provider and obj.provider.user_type == 'provider':
            try:
                profile = obj.provider.service_provider_profile
                return {
                    'id': obj.provider.id,
                    'business_name': profile.business_name,
                    'business_type': profile.business_type,
                    'city': profile.business_city,
                    'state': profile.business_state,
                    'country': profile.business_country,
                    'is_verified': profile.is_verified,
                }
            except:
                return None
        return None
    
    def get_relevance_score(self, obj):
        """Calculate relevance score based on user context"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return obj.priority_weight
        
        user = request.user
        score = obj.priority_weight
        
        # Provider business type match
        if user.user_type == 'provider':
            try:
                profile = user.service_provider_profile
                if obj.matches_provider_business(profile.business_type):
                    score += 2
                
                # Location match bonus
                if obj.matches_location(profile):
                    score += 3
            except:
                pass
        
        
        return round(score, 2)

class DestinationImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = DestinationImage
        fields = ['id', 'image_url', 'caption', 'display_order']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None

class VisitorTipSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitorTip
        fields = ['id', 'tip', 'display_order']

class PopularDestinationSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    gallery_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )
    # Image field should be in the serializer for updates, but we handle creation in view
    image = serializers.ImageField(required=False, write_only=True)
    
    class Meta:
        model = PopularDestination
        fields = [
            'id', 'name', 'destination_type', 'ziyarat_type',
            'short_description', 'detailed_description', 'image', 'image_url',
            'location', 'city', 'country', 'historical_significance',
            'prayers_recommended', 'rituals_associated', 'best_time_to_visit',
            'visiting_hours', 'dress_code', 'accessibility_info',
            'gallery_images', 'video_url', 'view_count', 'is_featured',
            'display_order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['view_count', 'image_url', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None
    
    def create(self, validated_data):
        """Handle creation with gallery images"""
        gallery_images = validated_data.pop('gallery_images', [])
        
        # Create the destination
        destination = PopularDestination.objects.create(**validated_data)
        
        # Create gallery images
        for image in gallery_images:
            DestinationImage.objects.create(
                destination=destination,
                image=image
            )
        
        return destination
    
    def update(self, instance, validated_data):
        """Handle update with gallery images"""
        gallery_images = validated_data.pop('gallery_images', None)
        
        # Update fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update gallery images if provided
        if gallery_images is not None:
            # Clear existing gallery images
            instance.additional_images.all().delete()
            
            # Add new gallery images
            for image in gallery_images:
                DestinationImage.objects.create(
                    destination=instance,
                    image=image
                )
        
        return instance
    
class PopularDestinationListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PopularDestination
        fields = [
            'id', 'name', 'destination_type', 'ziyarat_type',
            'short_description', 'image_url', 'location',
            'city', 'country', 'view_count', 'is_featured'
        ]
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None