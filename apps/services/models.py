from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import BaseModel, UserRole
from apps.authentication.models import ServiceProviderProfile

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
        ServiceProviderProfile,
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
        limit_choices_to={'user_type__in': [UserRole.ADMIN, UserRole.SUPER_ADMIN]}
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
    
    # ============= CONDITIONAL FIELDS BASED ON SERVICE TYPE =============
    
    # Air Ticket specific fields
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    departure_city = models.CharField(max_length=100, blank=True)
    arrival_city = models.CharField(max_length=100, blank=True)
    airline = models.CharField(max_length=100, blank=True)
    seat_availability = models.IntegerField(null=True, blank=True)
    
    # Flight specific fields (for Air Ticket service type)
    flight_from = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name="Flight From",
        help_text="Origin airport/city for flight"
    )
    flight_to = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name="Flight To",
        help_text="Destination airport/city for flight"
    )
    flight_class = models.CharField(
        max_length=20,
        choices=[
            ('economy', 'Economy'),
            ('business', 'Business'),
            ('first', 'First Class'),
            ('premium_economy', 'Premium Economy'),
        ],
        blank=True,
        verbose_name="Flight Class"
    )
    
    # Zamzam Water specific fields
    water_capacity = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Water Capacity",
        help_text="Capacity of Zamzam water (e.g., 500ml, 1L, 5L)"
    )
    water_capacity_liters = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Capacity in Liters",
        help_text="Numerical capacity in liters for filtering"
    )
    water_source = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Water Source",
        help_text="Source/origin of Zamzam water"
    )
    packaging_type = models.CharField(
        max_length=50,
        choices=[
            ('bottle', 'Bottle'),
            ('container', 'Container'),
            ('can', 'Can'),
            ('pouch', 'Pouch'),
        ],
        blank=True,
        verbose_name="Packaging Type"
    )
    
    # Hotel specific fields
    hotel_star_rating = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Star Rating"
    )
    hotel_room_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Room Type",
        help_text="Type of room (Single, Double, Suite, etc.)"
    )
        
    # Transport specific fields
    transport_type = models.CharField(
        max_length=50,
        choices=[
            ('bus', 'Bus'),
            ('car', 'Car'),
            ('taxi', 'Taxi'),
            ('van', 'Van'),
            ('coach', 'Coach'),
        ],
        blank=True,
        verbose_name="Transport Type"
    )
    vehicle_capacity = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Vehicle Capacity",
        help_text="Number of passengers"
    )
    pickup_location = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Pickup Location"
    )
    drop_location = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Drop Location"
    )
    
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
            models.Index(fields=['flight_from', 'flight_to']),
            models.Index(fields=['water_capacity_liters']),
        ]
    
    def __str__(self):
        provider_name = None
        try:
            if self.provider and self.provider.user:
                provider_name = self.provider.user.get_full_name() or self.provider.user.username
        except Exception:
            provider_name = "Unknown Provider"
        return f"{self.title} - ({provider_name})"
    
    def clean(self):
        """
        Custom validation to ensure required fields are filled based on service type
        """
        from django.core.exceptions import ValidationError
        
        errors = {}
        
        # Air Ticket validation
        if self.service_type == ServiceType.AIR_TICKET:
            if not self.flight_from:
                errors['flight_from'] = 'Flight From is required for Air Ticket services'
            if not self.flight_to:
                errors['flight_to'] = 'Flight To is required for Air Ticket services'
            if not self.departure_date:
                errors['departure_date'] = 'Departure date is required for Air Ticket services'
        
        # Zamzam Water validation
        if self.service_type == ServiceType.JAM_JAM_WATER:
            if not self.water_capacity:
                errors['water_capacity'] = 'Water capacity is required for Zamzam Water services'
        
        # Hotel validation
        if self.service_type == ServiceType.HOTEL:
            if not self.hotel_room_type:
                errors['hotel_room_type'] = 'Room type is required for Hotel services'
        
        # Transport validation
        if self.service_type == ServiceType.TRANSPORT:
            if not self.transport_type:
                errors['transport_type'] = 'Transport type is required for Transport services'
            if not self.pickup_location:
                errors['pickup_location'] = 'Pickup location is required for Transport services'
        
        if errors:
            raise ValidationError(errors)
    
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
        
        # Auto-populate numerical capacity for water
        if self.service_type == ServiceType.JAM_JAM_WATER and self.water_capacity:
            try:
                import re
                # Extract number from capacity string (e.g., "500ml" -> 0.5, "1L" -> 1)
                capacity_match = re.search(r'(\d+(?:\.\d+)?)', self.water_capacity.lower())
                if capacity_match:
                    capacity_num = float(capacity_match.group(1))
                    if 'ml' in self.water_capacity.lower():
                        self.water_capacity_liters = capacity_num / 1000
                    elif 'l' in self.water_capacity.lower():
                        self.water_capacity_liters = capacity_num
            except:
                pass  # If parsing fails, leave water_capacity_liters as is
        
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
        """Check if provider has an active subscription"""
        from django.utils import timezone
        from apps.subscriptions.models import Subscription

        return Subscription.objects.filter(
            user=self.provider.user,
            status='active',
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).exists()
    
    def get_service_specific_fields(self):
        """
        Return a dictionary of service-specific fields based on service type
        """
        specific_fields = {}
        
        if self.service_type == ServiceType.AIR_TICKET:
            specific_fields.update({
                'flight_from': self.flight_from,
                'flight_to': self.flight_to,
                'flight_class': self.flight_class,
                'departure_date': self.departure_date,
                'return_date': self.return_date,
                'airline': self.airline,
                'seat_availability': self.seat_availability,
            })
        
        elif self.service_type == ServiceType.JAM_JAM_WATER:
            specific_fields.update({
                'water_capacity': self.water_capacity,
                'water_capacity_liters': self.water_capacity_liters,
                'water_source': self.water_source,
                'packaging_type': self.packaging_type,
            })
        
        elif self.service_type == ServiceType.HOTEL:
            specific_fields.update({
                'hotel_star_rating': self.hotel_star_rating,
                'hotel_room_type': self.hotel_room_type,
            })
        
        elif self.service_type == ServiceType.TRANSPORT:
            specific_fields.update({
                'transport_type': self.transport_type,
                'vehicle_capacity': self.vehicle_capacity,
                'pickup_location': self.pickup_location,
                'drop_location': self.drop_location,
            })
        
        return {k: v for k, v in specific_fields.items() if v is not None}

# Rest of the models remain the same
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