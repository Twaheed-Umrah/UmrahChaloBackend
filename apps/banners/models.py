from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

User = get_user_model()

class BannerType(models.TextChoices):
    MAIN_SCREEN = 'main_screen', 'Main Screen Banner'
    OFFER = 'offer', 'Offer Banner'

class DisplayPriority(models.TextChoices):
    HIGH = 'high', 'High Priority'
    MEDIUM = 'medium', 'Medium Priority'
    LOW = 'low', 'Low Priority'

class Banner(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='banners/')
    banner_type = models.CharField(
        max_length=50,
        choices=BannerType.choices,
        default=BannerType.MAIN_SCREEN
    )
    
    # Provider reference
    provider = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        limit_choices_to={'user_type': 'provider'},
        related_name='banners'
    )
    
    # Provider business type filter
    provider_business_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Show banner only to providers of specific business type"
    )
    
    # Location-based targeting (city/state/country)
    target_city = models.CharField(max_length=100, blank=True)
    target_state = models.CharField(max_length=100, blank=True)
    target_country = models.CharField(max_length=100, blank=True)
    
    # Priority system
    display_priority = models.CharField(
        max_length=20,
        choices=DisplayPriority.choices,
        default=DisplayPriority.MEDIUM
    )
    priority_weight = models.IntegerField(
        default=1,
        help_text="Higher weight = higher priority (1-10)"
    )
    
    external_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority_weight', 'display_order', '-created_at']
        indexes = [
            models.Index(fields=['banner_type', 'is_active', 'display_priority']),
            models.Index(fields=['provider', 'is_active']),
            models.Index(fields=['target_city', 'target_state', 'is_active']),
        ]

    def __str__(self):
        if self.provider:
            try:
                business_name = self.provider.service_provider_profile.business_name
                return f"{self.title} - {business_name}"
            except:
                return f"{self.title} - Provider #{self.provider.id}"
        return f"{self.title} - My Company"
    def is_currently_active(self):
        """Check if banner is currently active based on dates"""
        now = timezone.now()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return self.is_active
    def is_currently_active(self):
        """Check if banner is currently active based on dates"""
        now = timezone.now()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return self.is_active
    
    def matches_location(self, provider_profile):
        """Check if banner matches provider's location"""
        if not self.target_city and not self.target_state and not self.target_country:
            return True  # Show to all if no location targeting
        
        matches = True
        
        if self.target_city:
            matches = matches and (provider_profile.business_city.lower() == self.target_city.lower())
        
        if self.target_state:
            matches = matches and (provider_profile.business_state.lower() == self.target_state.lower())
        
        if self.target_country:
            matches = matches and (provider_profile.business_country.lower() == self.target_country.lower())
        
        return matches
    
    
    def matches_provider_business(self, business_type):
        """Check if banner matches provider business type"""
        if not self.provider_business_type:
            return True
        return business_type == self.provider_business_type

class DestinationType(models.TextChoices):
    HAJJ = 'hajj', 'Hajj'
    UMRAH = 'umrah', 'Umrah'
    ZIYARAT = 'ziyarat', 'Ziyarat'

class ZiyaratType(models.TextChoices):
    MASJID_AL_HARAM = 'masjid_al_haram', 'Masjid al-Haram'
    MASJID_AN_NABAWI = 'masjid_an_nabawi', 'Masjid an-Nabawi'
    JABAL_RAHMA = 'jabal_rahma', 'Jabal Rahma'
    JANNAH_AL_BAQI = 'jannah_al_baqi', 'Jannah al-Baqi'
    JABAL_THAW = 'jabal_thawr', 'Jabal Thawr'
    HUDAIBIYAH = 'hudaibiyah', 'Hudaibiyah'
    OTHER_SITES = 'other_sites', 'Other Islamic Sites'

class PopularDestination(models.Model):
    name = models.CharField(max_length=200)
    destination_type = models.CharField(
        max_length=50,
        choices=DestinationType.choices
    )
    ziyarat_type = models.CharField(
        max_length=50,
        choices=ZiyaratType.choices,
        blank=True
    )
    short_description = models.TextField(blank=True, null=True)
    detailed_description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='destinations/')
    location = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='Saudi Arabia')
    
    # Religious significance
    historical_significance = models.TextField(blank=True)
    prayers_recommended = models.TextField(blank=True)
    rituals_associated = models.TextField(blank=True)
    best_time_to_visit = models.CharField(max_length=200, blank=True)
    
    # Practical information
    visiting_hours = models.CharField(max_length=200, blank=True)
    dress_code = models.TextField(blank=True)
    accessibility_info = models.TextField(blank=True)
    
    # Additional media
    gallery_images = models.ManyToManyField('DestinationImage', blank=True)
    video_url = models.URLField(blank=True)
    
    # Display settings
    view_count = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', '-is_featured', '-view_count']
        indexes = [
            models.Index(fields=['destination_type', 'is_active']),
            models.Index(fields=['ziyarat_type', 'is_active']),
        ]

    def __str__(self):
        return self.name

class DestinationImage(models.Model):
    destination = models.ForeignKey(
        PopularDestination, 
        on_delete=models.CASCADE, 
        related_name='additional_images'
    )
    image = models.ImageField(upload_to='destination_gallery/')
    caption = models.CharField(max_length=200, blank=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order']

class VisitorTip(models.Model):
    destination = models.ForeignKey(
        PopularDestination, 
        on_delete=models.CASCADE,
        related_name='visitor_tips'
    )
    tip = models.TextField()
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order']