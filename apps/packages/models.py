# apps/packages/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
import uuid

from apps.core.models import BaseModel
from apps.services.models import Service, ServiceImage
from apps.authentication.models import ServiceProviderProfile

User = get_user_model()


class Package(models.Model):
    PACKAGE_TYPES = [
        ('hajj', 'Hajj'),
        ('umrah', 'Umrah'),
        ('both', 'Hajj & Umrah'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField()
    package_type = models.CharField(max_length=10, choices=PACKAGE_TYPES)

    provider = models.ForeignKey(
        ServiceProviderProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='packages'
    )

    base_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    duration_days = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    booking_deadline = models.DateField()
    max_capacity = models.PositiveIntegerField(default=50)
    current_bookings = models.PositiveIntegerField(default=0)

    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='India')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_packages'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    slug = models.SlugField(unique=True, blank=True)
    featured_image = models.ForeignKey(ServiceImage, on_delete=models.SET_NULL, null=True, blank=True, related_name='featured_in_packages')

    views_count = models.PositiveIntegerField(default=0)
    leads_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, validators=[MinValueValidator(0), MaxValueValidator(5)])
    reviews_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['package_type', 'start_date']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['city', 'state', 'country']),
        ]

    def __str__(self):
        try:
            return f"{self.name} - ({self.provider.user.get_full_name()})"
        except Exception:
            return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"{slugify(self.name)}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    @property
    def is_available(self):
        now = timezone.now().date()
        return self.status == 'published' and self.is_active and self.booking_deadline >= now and self.current_bookings < self.max_capacity

    @property
    def availability_percentage(self):
        if self.max_capacity == 0:
            return 0
        return ((self.max_capacity - self.current_bookings) / self.max_capacity) * 100

    @property
    def final_price(self):
    # Assume self.discount_amount stores the discount value
        if self.discounted_price:
            return self.base_price - self.discounted_price
        return self.base_price



class PackageService(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='package_services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='package_services')
    is_included = models.BooleanField(default=True)
    is_optional = models.BooleanField(default=False)
    additional_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)]
    )
    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['package', 'service']

    def __str__(self):
        package_name = getattr(self.package, 'name', 'No Package')
        service_name = getattr(self.service, 'name', 'No Service')
        return f"{package_name} - {service_name}"


class PackageInclusion(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='inclusions')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_highlighted = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'title']

    def __str__(self):
        return f"{self.package.name} - {self.title}"


class PackageExclusion(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='exclusions')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'title']

    def __str__(self):
        return f"{self.package.name} - {self.title}"


class PackageItinerary(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='itineraries')
    day_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=200, blank=True)
    activities = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['day_number']
        unique_together = ['package', 'day_number']

    def __str__(self):
        return f"{self.package.name} - Day {self.day_number}"


class PackageImage(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='package_images/')
    caption = models.CharField(max_length=200, blank=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.package.name} - Image {self.id}"


class PackagePolicy(BaseModel):
    POLICY_TYPES = [
        ('cancellation', 'Cancellation Policy'),
        ('payment', 'Payment Policy'),
        ('refund', 'Refund Policy'),
        ('terms', 'Terms & Conditions'),
    ]

    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='policies')
    policy_type = models.CharField(max_length=20, choices=POLICY_TYPES)
    title = models.CharField(max_length=200)
    content = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'policy_type']
        unique_together = ['package', 'policy_type']

    def __str__(self):
        return f"{self.package.name} - {self.get_policy_type_display()}"


class PackageAvailability(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='availabilities')
    date = models.DateField()
    available_slots = models.PositiveIntegerField(default=0)
    price_adjustment = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_available = models.BooleanField(default=True)
    color_code = models.CharField(max_length=7, default='#28a745', help_text="Color code for calendar display")

    class Meta:
        unique_together = ['package', 'date']
        ordering = ['date']

    def __str__(self):
        return f"{self.package.name} - {self.date}"
