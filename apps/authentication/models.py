from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.conf import settings
from apps.core.models import BaseModel, UserRole
class User(AbstractUser):
    """
    Custom User model extending AbstractUser
    """
    USER_TYPES = [
        (UserRole.PILGRIM, UserRole.PILGRIM.label),
        (UserRole.PROVIDER, UserRole.PROVIDER.label),
        (UserRole.SUPER_ADMIN, UserRole.SUPER_ADMIN.label),
    ]
    
    full_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(unique=True,max_length=15, blank=True, null=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='pilgrim')
    is_verified = models.BooleanField(default=False)
    
    # Location fields
    latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=8, 
        null=True, 
        blank=True,
        help_text="Latitude coordinate"
    )
    longitude = models.DecimalField(
        max_digits=11, 
        decimal_places=8, 
        null=True, 
        blank=True,
        help_text="Longitude coordinate"
    )
    location_updated_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Last time location was updated"
    )
    location_address = models.TextField(
        blank=True, 
        null=True,
        help_text="Human readable address from coordinates"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Needed for createsuperuser

    class Meta:
        db_table = 'auth_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.email} - {self.user_type}"

    def save(self, *args, **kwargs):
        if not self.username and self.full_name:
            base_username = self.full_name.strip().lower().replace(" ", "_")
            username_candidate = base_username
            counter = 1
            while User.objects.filter(username=username_candidate).exists():
                username_candidate = f"{base_username}_{counter}"
                counter += 1
            self.username = username_candidate
        super().save(*args, **kwargs)
    
    def update_location(self, latitude, longitude, address=None):
        """
        Update user's location coordinates
        For pilgrims: can be called multiple times (when app opens)
        For providers: typically called once during profile creation
        """
        self.latitude = latitude
        self.longitude = longitude
        self.location_updated_at = timezone.now()
        if address:
            self.location_address = address
        self.save(update_fields=['latitude', 'longitude', 'location_updated_at', 'location_address'])
    
    @property
    def has_location(self):
        """Check if user has location data"""
        return self.latitude is not None and self.longitude is not None
    
    @property
    def location_coordinates(self):
        """Return coordinates as tuple (latitude, longitude)"""
        if self.has_location:
            return (float(self.latitude), float(self.longitude))
        return None
    
    def get_location_info(self):
        """Get complete location information"""
        if self.has_location:
            return {
                'latitude': float(self.latitude),
                'longitude': float(self.longitude),
                'address': self.location_address,
                'updated_at': self.location_updated_at
            }
        return None
        
class OTPVerification(models.Model):
    """
    Model to handle OTP verification for users
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='otp_verifications')
    otp = models.CharField(max_length=6)
    purpose = models.CharField(max_length=50, choices=[
        ('email_verification', 'Email Verification'),
        ('phone_verification', 'Phone Verification'),
        ('password_reset', 'Password Reset'),
        ('login', 'Login'),
    ])
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'otp_verifications'
        verbose_name = 'OTP Verification'
        verbose_name_plural = 'OTP Verifications'
    
    def __str__(self):
        return f"OTP for {self.user.email} - {self.purpose}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()


class LoginAttempt(models.Model):
    """
    Model to track login attempts for security
    """
    email = models.EmailField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'login_attempts'
        verbose_name = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'
    
    def __str__(self):
        return f"Login attempt for {self.email} - {'Success' if self.success else 'Failed'}"


class UserSession(models.Model):
    """
    Model to track user sessions
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40)
    device_info = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_sessions'
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'
    
    def __str__(self):
        return f"Session for {self.user.email}"


class ServiceProviderProfile(models.Model):
    """Detailed Service Provider profile for verification and business operations"""
    
    BUSINESS_TYPES = (
        ('individual', 'Individual'),
        ('company', 'Company'),
        ('agency', 'Travel Agency'),
        ('visa', 'Visa'),
        ('hotels', 'Hotels'),
        ('transport', 'Transport'),
        ('food', 'Food'),
        ('laundry', 'Laundry'),
        ('air_ticket_group_fare_umrah', 'Air Ticket Group Fare Umrah'),
        ('umrah_guide', 'Umrah Guide'),
        ('umrah_kit', 'Umrah Kit'),
        ('jam_jam_water', 'Jam Jam Water'),
        ('full_package', 'Full Package'),
    )
    
    VERIFICATION_STATUS = (
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='service_provider_profile')
    
    # Business Information
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES)
    business_description = models.TextField(blank=True)
    business_logo = models.ImageField(upload_to='business_logos/', null=True, blank=True)
    
    # Contact Information
    business_email = models.EmailField()
    business_phone = models.CharField(max_length=17)
    business_address = models.TextField()
    business_city = models.CharField(max_length=100)
    business_state = models.CharField(max_length=100)
    business_country = models.CharField(max_length=100)
    business_pincode = models.CharField(max_length=10)
    
    # Legal Information
    government_id_type = models.CharField(max_length=50)
    government_id_number = models.CharField(max_length=50)
    government_id_document = models.FileField(upload_to='government_ids/')
    gst_number = models.CharField(max_length=15, blank=True)
    gst_certificate = models.FileField(upload_to='gst_certificates/', null=True, blank=True)
    
    # License Information
    trade_license_number = models.CharField(max_length=100, null=True, blank=True)
    trade_license_document = models.FileField(upload_to='trade_licenses/', null=True, blank=True)
    
    # Verification
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS, default='pending')
    verification_notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_providers')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Stats for lead generation
    total_packages = models.IntegerField(default=0)
    total_leads = models.IntegerField(default=0)
    total_bookings = models.IntegerField(default=0)
    average_rating = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'serviceproviderprofiles'
        verbose_name = 'serviceproviderprofiles'
        verbose_name_plural = 'serviceproviderprofiles'
    
    def __str__(self):
        return f"{self.business_name} - {self.user.email}"
    
    @property
    def is_verified(self):
        return self.verification_status == 'verified'
    
    def update_stats(self):
        """Update provider statistics for lead generation metrics"""
        from apps.packages.models import Package
        from apps.leads.models import Lead
        from apps.reviews.models import Review
        
        self.total_packages = Package.objects.filter(provider=self).count()
        self.total_leads = Lead.objects.filter(provider=self).count()
        
        reviews = Review.objects.filter(provider=self)
        if reviews.exists():
            self.average_rating = reviews.aggregate(
                avg_rating=models.Avg('rating')
            )['avg_rating'] or 0.00
            self.total_reviews = reviews.count()
        
        self.save()
    
    def has_active_subscription(self):
        """Check if this service provider's user has an active subscription."""
        return self.user.subscriptions.filter(
            status='active',
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).exists()
    
    def get_active_subscription(self):
        """Get the active subscription object"""
        return self.user.subscriptions.filter(
            status='active',
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).first()
    
    def can_upload_any_service_type(self):
        """Check if provider can upload any service type (Ultra Premium feature)"""
        subscription = self.get_active_subscription()
        if not subscription:
            return False
        return subscription.can_upload_any_service_type()
    
    def can_upload_any_package(self):
        """Check if provider can upload any package (Ultra Premium feature)"""
        subscription = self.get_active_subscription()
        if not subscription:
            return False
        return subscription.can_upload_any_package()
    
    def gets_cross_business_leads(self):
        """Check if provider gets leads from all business types (Ultra Premium feature)"""
        subscription = self.get_active_subscription()
        if not subscription:
            return False
        return subscription.gets_cross_business_leads()
    
    def check_service_upload_permission(self, service_type):
        """Check if provider can upload specific service type"""
        # Ultra Premium can upload anything
        if self.can_upload_any_service_type():
            return True, None
        
        # Map service types to business types
        service_type_to_business_type = {
            'visa': 'visa',
            'hotel': 'hotels',
            'transport': 'transport',
            'food': 'food',
            'laundry': 'laundry',
            'air_ticket': 'air_ticket_group_fare_umrah',
            'umrah_guide': 'umrah_guide',
            'umrah_kit': 'umrah_kit',
            'jam_jam_water': 'jam_jam_water',
            'full_package': 'full_package',
        }
        
        allowed_business_type = service_type_to_business_type.get(service_type)
        
        if allowed_business_type and allowed_business_type != self.business_type:
            error_message = f"Your business type ({self.business_type}) can only upload {self.business_type} services. "
            error_message += f"You are trying to upload {service_type} service. "
            error_message += "Upgrade to Ultra Premium to upload any type of service."
            return False, error_message
        
        return True, None
    
    def check_package_upload_permission(self):
        """Check if provider can upload packages"""
        # Ultra Premium can upload anything
        if self.can_upload_any_package():
            return True, None
        
        # Only specific business types can upload packages
        allowed_for_packages = ['agency', 'company', 'full_package']
        
        if self.business_type not in allowed_for_packages:
            error_message = f"Your business type ({self.business_type}) cannot upload packages. "
            error_message += "Only agencies, companies, and full package providers can upload packages. "
            error_message += "Upgrade to Ultra Premium to upload any type of package."
            return False, error_message
        
        return True, None
    
    def check_upload_limits(self, upload_type):
        """Check if provider has reached upload limits"""
        subscription = self.get_active_subscription()
        if not subscription:
            return False, "No active subscription found"
        
        plan = subscription.plan
        
        # Ultra Premium has no limits
        if plan.plan_type == 'ultra_premium':
            return True, None
        
        if upload_type == 'service':
            current_count = self.services.count()
            limit = plan.max_services
            if current_count >= limit:
                return False, f"You have reached your service limit ({limit}). Upgrade to Ultra Premium for unlimited services."
        
        elif upload_type == 'package':
            current_count = self.packages.count()
            limit = plan.max_packages
            if current_count >= limit:
                return False, f"You have reached your package limit ({limit}). Upgrade to Ultra Premium for unlimited packages."
        
        return True, None
# REMOVED: PilgrimProfile - Basic User model is sufficient for pilgrims
# Pilgrims only need: email, phone, user_type = 'pilgrim'
# No additional profile model needed


class SavedPackage(models.Model):
    """Users can save packages for later reference"""
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_packages')
    package = models.ForeignKey('packages.Package', on_delete=models.CASCADE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'saved_packages'
        verbose_name = 'Saved Package'
        verbose_name_plural = 'Saved Packages'
        unique_together = ['user', 'package']
    
    def __str__(self):
        return f"{self.user.email} - {self.package.title}"


class UserActivity(models.Model):
    """Track user activities for lead generation analytics"""
    
    ACTIVITY_TYPES = (
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('view_package', 'View Package'),
        ('inquiry_sent', 'Inquiry Sent'),
        ('package_saved', 'Package Saved'),
        ('search_performed', 'Search Performed'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_activities'
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.get_activity_type_display()}"