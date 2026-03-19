from django.db import models
from django.utils import timezone
import uuid


class ContactInquiry(models.Model):
    """Stores Contact Us form submissions from visitors."""

    STATUS_CHOICES = [
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    SERVICE_CHOICES = [
        ('Hotels', 'Hotels'),
        ('Transport', 'Transport'),
        ('Food Services', 'Food Services'),
        ('Laundry', 'Laundry'),
        ('Air Tickets', 'Air Tickets'),
        ('Umrah Guide', 'Umrah Guide'),
        ('Umrah Kits', 'Umrah Kits'),
        ('Zamzam Water', 'Zamzam Water'),
        ('Visa Services', 'Visa Services'),
        ('Other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    service_interest = models.CharField(max_length=100, choices=SERVICE_CHOICES, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    admin_notes = models.TextField(blank=True, help_text='Internal notes for admin team')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contact_inquiries'
        ordering = ['-created_at']
        verbose_name = 'Contact Inquiry'
        verbose_name_plural = 'Contact Inquiries'

    def __str__(self):
        return f"{self.name} ({self.email}) - {self.get_status_display()}"


class ChatSession(models.Model):
    """Stores a chatbot conversation session."""

    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Optionally extracted from conversation
    visitor_name = models.CharField(max_length=200, blank=True)
    visitor_email = models.EmailField(blank=True)
    visitor_phone = models.CharField(max_length=20, blank=True)

    # Full message history stored as JSON list:
    # [{"sender": "bot"|"user", "text": "...", "timestamp": "..."}]
    messages = models.JSONField(default=list)

    # Metadata
    topics_discussed = models.JSONField(default=list, blank=True,
                                         help_text='List of topic keys from botResponses that were triggered')
    total_messages = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-created_at']
        verbose_name = 'Chat Session'
        verbose_name_plural = 'Chat Sessions'

    def __str__(self):
        identifier = self.visitor_name or self.visitor_email or str(self.session_id)[:8]
        return f"Chat Session — {identifier} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    def save(self, *args, **kwargs):
        self.total_messages = len(self.messages)
        super().save(*args, **kwargs)
