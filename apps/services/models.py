from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import BaseModel, UserRole
import uuid

User = get_user_model()

class ServiceCategory(BaseModel):
    """
    Categories for different types of services
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True)  # Icon class name
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        verbose_name_plural = "Service Categories"
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name

class ServiceType(models.TextChoices):
    VISA = 'visa', 'Visa'
    HOTEL = 'hotel', 'Hotels'
    TRANSPORT = 'transport', 'Transport'
    FOOD = 'food', 'Food'
    LAUNDRY = 'laundry', 'Laundry'
    AIR_TICKET = 'air_ticket', 'Air Ticket Group Fare Umrah'
    UMRAH_GUIDE = 'umrah_guide', 'Umrah Guide'
    UMRAH_KIT = 'umrah_kit', 'Umrah Kit'
    JAM_JAM_WATER = 'jam_jam_water', 'Jam Jam Water'
    HAJJ_PACKAGE = 'hajj_package', 'Hajj Package'
    UMRAH_PACKAGE = 'umrah_package', 'Umrah Package'

class ServiceStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    VERIFIED = 'verified', 'Verified'
    PUBLISHED = 'published', 'Published'
    REJECTED = 'rejected', 'Rejected'
    EXPIRED = 'expired', 'Expired'

class ServiceImage(BaseModel):
    """
    Image bank managed by Super Admin
    """
    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to='service_images/')
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='images')
    alt_text = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.category.name}"

class Service(BaseModel):
    """
    Individual services offered by providers
    """
    provider = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name='services'
)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    short_description = models.CharField(max_length=500, blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_currency = models.CharField(max_length=3, default='INR')
    price_per = models.CharField(max_length=50, default='person')  # person, group, day, etc.
    
    # Service details
    duration = models.CharField(max_length=100, blank=True)  # "5 days", "2 hours", etc.
    duration_in_days = models.IntegerField(null=True, blank=True)  # For filtering
    
    # Location
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='India')
    
    # Availability
    available_from = models.DateField(null=True, blank=True)
    available_to = models.DateField(null=True, blank=True)
    is_always_available = models.BooleanField(default=True)
    
    # Images (selected from image bank)
    images = models.ManyToManyField(ServiceImage, blank=True, related_name='services')
    featured_image = models.ForeignKey(
        ServiceImage, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='featured_services'
    )
    
    # Status and verification
    status = models.CharField(max_length=20, choices=ServiceStatus.choices, default=ServiceStatus.PENDING)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_services',
        limit_choices_to={'role__in': [UserRole.ADMIN, UserRole.SUPER_ADMIN]}
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Features and inclusions
    features = models.JSONField(default=list, blank=True)  # List of features
    inclusions = models.JSONField(default=list, blank=True)  # What's included
    exclusions = models.JSONField(default=list, blank=True)  # What's not included
    
    # Contact and booking
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    booking_requirements = models.TextField(blank=True)
    
    # Analytics
    views_count = models.IntegerField(default=0)
    leads_count = models.IntegerField(default=0)
    bookings_count = models.IntegerField(default=0)
    
    # SEO
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=300, blank=True)
    
    # Special fields for Air Ticket Group Fare
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    departure_city = models.CharField(max_length=100, blank=True)
    arrival_city = models.CharField(max_length=100, blank=True)
    airline = models.CharField(max_length=100, blank=True)
    seat_availability = models.IntegerField(null=True, blank=True)
    
    # Flags
    is_featured = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['service_type', 'status']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['city', 'service_type']),
            models.Index(fields=['departure_date']),
            models.Index(fields=['price']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.provider.user.get_full_name()}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Service.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if reviews:
            return reviews.aggregate(models.Avg('rating'))['rating__avg']
        return 0
    
    @property
    def total_reviews(self):
        return self.reviews.count()
    
    @property
    def discount_percentage(self):
        if self.original_price and self.original_price > self.price:
            return round(((self.original_price - self.price) / self.original_price) * 100)
        return 0
    
    def increment_views(self):
        """Increment view count"""
        self.views_count += 1
        self.save(update_fields=['views_count'])
    
    def increment_leads(self):
        """Increment lead count"""
        self.leads_count += 1
        self.save(update_fields=['leads_count'])
    
    def is_available_on_date(self, date):
        """Check if service is available on a specific date"""
        if self.is_always_available:
            return True
        
        if self.available_from and self.available_to:
            return self.available_from <= date <= self.available_to
        
        return False
    
    def get_provider_subscription_status(self):
        """Check if provider has active subscription"""
        from apps.subscriptions.models import Subscription
        return Subscription.objects.filter(
            provider=self.provider,
            is_active=True
        ).exists()

class ServiceAvailability(BaseModel):
    """
    Manage service availability for specific dates
    """
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='availabilities')
    date = models.DateField()
    available_slots = models.IntegerField(default=1)
    booked_slots = models.IntegerField(default=0)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['service', 'date']
        ordering = ['date']
    
    def __str__(self):
        return f"{self.service.title} - {self.date}"
    
    @property
    def remaining_slots(self):
        return self.available_slots - self.booked_slots
    
    @property
    def is_fully_booked(self):
        return self.booked_slots >= self.available_slots

class ServiceFAQ(BaseModel):
    """
    Frequently asked questions for services
    """
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='faqs')
    question = models.CharField(max_length=300)
    answer = models.TextField()
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'created_at']
    
    def __str__(self):
        return f"{self.service.title} - {self.question}"

class ServiceView(BaseModel):
    """
    Track service views for analytics
    """
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='view_logs')
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-viewed_at']
    
    def __str__(self):
        return f"{self.service.title} - {self.viewed_at}"