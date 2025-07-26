from django.db import models
from django.conf import settings
from django.utils import timezone

class TimeStampedModel(models.Model):
    """
    Abstract base class that provides created_at and updated_at fields
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

class BaseModel(TimeStampedModel, models.Model):
    """
    Abstract base class that provides created_at, updated_at, and primary key.
    """
    id = models.AutoField(primary_key=True)

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager):
    """
    Manager for soft delete functionality
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    
    def deleted(self):
        return super().get_queryset().filter(is_deleted=True)
    
    def all_with_deleted(self):
        return super().get_queryset()

class SoftDeleteModel(models.Model):
    """
    Abstract model that provides soft delete functionality
    """
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    objects = SoftDeleteManager()
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def delete(self, using=None, keep_parents=False):
        """
        Soft delete the object
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=['is_deleted', 'deleted_at'])
    
    def hard_delete(self, using=None, keep_parents=False):
        """
        Actually delete the object from database
        """
        super().delete(using=using, keep_parents=keep_parents)
    
    def restore(self):
        """
        Restore a soft deleted object
        """
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])

class Status(models.TextChoices):
    """
    Generic status choices for various models
    """
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    SUSPENDED = 'suspended', 'Suspended'
    EXPIRED = 'expired', 'Expired'

class Priority(models.TextChoices):
    """
    Priority levels for various models
    """
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    URGENT = 'urgent', 'Urgent'

class ServiceType(models.TextChoices):
    """
    Types of services available in the platform
    """
    VISA = 'visa', 'Visa'
    HOTEL = 'hotel', 'Hotel'
    TRANSPORT = 'transport', 'Transport'
    FOOD = 'food', 'Food'
    LAUNDRY = 'laundry', 'Laundry'
    AIR_TICKET = 'air_ticket', 'Air Ticket Group Fare'
    UMRAH_GUIDE = 'umrah_guide', 'Umrah Guide'
    UMRAH_KIT = 'umrah_kit', 'Umrah Kit'
    ZAMZAM_WATER = 'zamzam_water', 'Zamzam Water'
    HAJJ_PACKAGE = 'hajj_package', 'Hajj Package'
    UMRAH_PACKAGE = 'umrah_package', 'Umrah Package'

class UserRole(models.TextChoices):
    """
    User roles in the system
    """
    PILGRIM = 'pilgrim', 'Pilgrim'
    PROVIDER = 'provider', 'Service Provider'
    ADMIN = 'admin', 'Admin'
    SUPER_ADMIN = 'super_admin', 'Super Admin'

class Country(BaseModel):
    """
    Country model for location data
    """
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=3, unique=True)
    phone_code = models.CharField(max_length=5)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Countries'
        ordering = ['name']
    
    def __str__(self):
        return self.name

class State(BaseModel):
    """
    State model for location data
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['name', 'country']
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}, {self.country.name}"

class City(BaseModel):
    """
    City model for location data
    """
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='cities')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Cities'
        unique_together = ['name', 'state']
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}, {self.state.name}"

class ActivityLog(BaseModel):
    """
    Activity log model to track user actions
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  
        on_delete=models.CASCADE,
        related_name='activity_logs'
    )
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['model_name', 'action']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.model_name}"

class FAQ(BaseModel):
    """
    Frequently Asked Questions model
    """
    question = models.CharField(max_length=500)
    answer = models.TextField()
    category = models.CharField(max_length=100, default='general')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order', 'question']
    
    def __str__(self):
        return self.question

class ImageBank(BaseModel):
    """
    Image bank for service and package images uploaded by super admin
    """
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='image_bank/')
    alt_text = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=50, choices=ServiceType.choices)
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Changed from 'auth.User'
        on_delete=models.CASCADE,
        related_name='uploaded_images'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name

class SystemConfiguration(BaseModel):
    """
    System configuration model for global settings
    """
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['key']
    
    def __str__(self):
        return f"{self.key}: {self.value[:50]}..."