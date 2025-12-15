# leads/models.py

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.authentication.models import ServiceProviderProfile
from apps.services.models import Service
from apps.packages.models import Package
from apps.core.models import BaseModel

User = get_user_model()

class Lead(models.Model):
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

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leads')
    package = models.ForeignKey(Package, on_delete=models.CASCADE, null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, null=True, blank=True)
    lead_type = models.CharField(max_length=20, choices=LEAD_TYPE_CHOICES, default='package')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    preferred_date = models.DateField(null=True, blank=True)
    number_of_people = models.PositiveIntegerField(default=1)
    budget_range = models.CharField(max_length=50, null=True, blank=True)
    departure_city = models.CharField(max_length=100, null=True, blank=True)
    special_requirements = models.TextField(null=True, blank=True)
    selected_services = models.JSONField(default=dict, blank=True)  # <-- optional now
    is_distributed = models.BooleanField(default=False)
    distribution_date = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=50, default='web')
    priority = models.PositiveIntegerField(default=0)
    service_provider = models.ForeignKey(ServiceProviderProfile, null=True, blank=True, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'leads'
        ordering = ['-created_at']

    def __str__(self):
        return f"Lead by {self.full_name} - {self.lead_type}"

    def save(self, *args, **kwargs):
        # Default expiry
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=30)

        # Auto-detect lead_type
        if not self.lead_type:
            if self.package:
                self.lead_type = 'package'
            elif self.service:
                self.lead_type = 'service'
            else:
                self.lead_type = 'custom'

        # Auto-fill selected_services for package leads
        if self.lead_type == 'package' and not self.selected_services and self.package:
            self.selected_services = {"package_id": self.package.id, "package_name": self.package.name}

        # Auto-fill selected_services for service leads
        if self.lead_type == 'service' and not self.selected_services and self.service:
            self.selected_services = {"service_id": self.service.id, "service_name": self.service.title}

        # Auto-set service_provider if user has one
        if self.user_id and not self.service_provider:
            if hasattr(self.user, 'service_provider_profile'):
                self.service_provider = self.user.service_provider_profile

        # Validate and save
        self.full_clean()
        super().save(*args, **kwargs)


class LeadDistribution(BaseModel):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('responded', 'Responded'),
        ('ignored', 'Ignored'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='distributions')
    provider = models.ForeignKey(ServiceProviderProfile, on_delete=models.CASCADE, related_name='lead_distributions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    sent_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_message = models.TextField(null=True, blank=True)
    quoted_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'lead_distributions'
        unique_together = ['lead', 'provider']
        ordering = ['-sent_at']

    def __str__(self):
        return f"Distribution of Lead {self.lead.id} to {self.provider}"


class LeadInteraction(BaseModel):
    INTERACTION_TYPES = [
        ('call', 'Call'),
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('meeting', 'Meeting'),
        ('other', 'Other'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='interactions')
    provider = models.ForeignKey(ServiceProviderProfile, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    notes = models.TextField(blank=True)
    interaction_date = models.DateTimeField(default=timezone.now)
    follow_up_date = models.DateTimeField(null=True, blank=True)
    is_successful = models.BooleanField(default=False)
    outcome_notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'lead_interactions'
        ordering = ['-interaction_date']

    def __str__(self):
        return f"{self.get_interaction_type_display()} on {self.interaction_date}"


class LeadNote(BaseModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='notes')
    provider = models.ForeignKey(ServiceProviderProfile, on_delete=models.CASCADE, related_name='notes')
    note = models.TextField()
    is_private = models.BooleanField(default=True)

    class Meta:
        db_table = 'lead_notes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Note by {self.provider} on Lead {self.lead.id}"
