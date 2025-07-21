from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel
from apps.services.models import Service
from apps.packages.models import Package
from django.conf import settings

User = get_user_model()


class Lead(BaseModel):
    """
    Model to store lead information when users show interest in packages/services
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('contacted', 'Contacted'),
        ('converted', 'Converted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    LEAD_TYPE_CHOICES = [
        ('package', 'Package'),
        ('service', 'Service'),
        ('custom', 'Custom'),
    ]
    
    # User who created the lead
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='leads'
    )
    
    # Lead can be for either package or service
    package = models.ForeignKey(
        Package, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='leads'
    )
    
    service = models.ForeignKey(
        Service, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='leads'
    )
    
    # Lead details
    lead_type = models.CharField(
        max_length=20, 
        choices=LEAD_TYPE_CHOICES,
        default='package'
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Contact information
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    
    # Travel details
    preferred_date = models.DateField(null=True, blank=True)
    number_of_people = models.PositiveIntegerField(default=1)
    budget_range = models.CharField(max_length=50, null=True, blank=True)
    
    # Location preferences
    departure_city = models.CharField(max_length=100, null=True, blank=True)
    preferred_hotel_category = models.CharField(max_length=50, null=True, blank=True)
    
    # Additional requirements
    special_requirements = models.TextField(null=True, blank=True)
    custom_message = models.TextField(null=True, blank=True)
    
    # Selected services (for custom packages)
    selected_services = models.JSONField(
        default=dict,
        help_text="JSON field to store selected services for custom packages"
    )
    
    # Tracking
    is_distributed = models.BooleanField(default=False)
    distribution_date = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Source tracking
    source = models.CharField(
        max_length=50, 
        default='web',
        help_text="Source of lead: web, app, etc."
    )
    
    # Priority (for premium providers)
    priority = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'leads'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['package', 'status']),
            models.Index(fields=['service', 'status']),
            models.Index(fields=['preferred_date']),
            models.Index(fields=['is_distributed']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Lead by {self.full_name} for {self.package or self.service}"
    
    def save(self, *args, **kwargs):
        # Set expiry date (30 days from creation)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=30)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        return timezone.now() > self.expires_at if self.expires_at else False
    
    @property
    def target_providers(self):
        """Get providers who should receive this lead"""
        if self.package:
            return [self.package.provider]
        elif self.service:
            return [self.service.provider]
        return []


class LeadDistribution(BaseModel):
    """
    Model to track lead distribution to service providers
    """
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('responded', 'Responded'),
        ('ignored', 'Ignored'),
    ]
    
    lead = models.ForeignKey(
        Lead, 
        on_delete=models.CASCADE, 
        related_name='distributions'
    )
    
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='received_leads'
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='sent'
    )
    
    sent_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    # Provider response
    response_message = models.TextField(null=True, blank=True)
    quoted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Tracking
    email_sent = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    app_notification_sent = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'lead_distributions'
        unique_together = ['lead', 'provider']
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['lead', 'provider']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['sent_at']),
        ]
    
    def __str__(self):
        return f"Lead {self.lead.id} distributed to {self.provider.business_name}"
    
    def mark_as_viewed(self):
        if self.status == 'sent':
            self.status = 'viewed'
            self.viewed_at = timezone.now()
            self.save()
    
    def mark_as_responded(self, message=None, quoted_price=None):
        self.status = 'responded'
        self.responded_at = timezone.now()
        if message:
            self.response_message = message
        if quoted_price:
            self.quoted_price = quoted_price
        self.save()


class LeadInteraction(BaseModel):
    """
    Model to track interactions between users and providers regarding leads
    """
    INTERACTION_TYPES = [
        ('call', 'Phone Call'),
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('meeting', 'Meeting'),
        ('other', 'Other'),
    ]
    
    lead = models.ForeignKey(
        Lead, 
        on_delete=models.CASCADE, 
        related_name='interactions'
    )
    
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='lead_interactions'
    )
    
    interaction_type = models.CharField(
        max_length=20, 
        choices=INTERACTION_TYPES
    )
    
    notes = models.TextField(null=True, blank=True)
    interaction_date = models.DateTimeField(default=timezone.now)
    
    # Follow-up
    follow_up_date = models.DateTimeField(null=True, blank=True)
    follow_up_notes = models.TextField(null=True, blank=True)
    
    # Outcome
    is_successful = models.BooleanField(default=False)
    outcome_notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'lead_interactions'
        ordering = ['-interaction_date']
        indexes = [
            models.Index(fields=['lead', 'provider']),
            models.Index(fields=['interaction_date']),
        ]
    
    def __str__(self):
        return f"{self.interaction_type} interaction for Lead {self.lead.id}"


class LeadNote(BaseModel):
    """
    Model for providers to add notes about leads
    """
    lead = models.ForeignKey(
        Lead, 
        on_delete=models.CASCADE, 
        related_name='notes'
    )
    
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='lead_notes'
    )
    
    note = models.TextField()
    is_private = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'lead_notes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lead', 'provider']),
        ]
    
    def __str__(self):
        return f"Note for Lead {self.lead.id} by {self.provider.business_name}"