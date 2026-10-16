# apps/telephony/models.py

from django.db import models
from apps.core.models import BaseModel


class CallLog(BaseModel):
    """
    Log of all incoming/outgoing Exotel calls, routing decisions,
    call durations, and recording URLs.
    """
    DIRECTION_CHOICES = [
        ('incoming', 'Incoming'),
        ('outbound-dial', 'Outbound Dial'),
        ('outbound-api', 'Outbound API'),
    ]

    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('ringing', 'Ringing'),
        ('in-progress', 'In Progress'),
        ('completed', 'Completed'),
        ('busy', 'Busy'),
        ('no-answer', 'No Answer'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
        ('client-hangup', 'Client Hangup'),
        ('incomplete', 'Incomplete'),
    ]

    call_sid = models.CharField(max_length=120, unique=True, db_index=True, help_text="Unique Exotel CallSid")
    call_from = models.CharField(max_length=50, blank=True, help_text="Caller's number")
    call_to = models.CharField(max_length=50, blank=True, help_text="ExoPhone dialed")
    direction = models.CharField(max_length=30, choices=DIRECTION_CHOICES, default='incoming', blank=True)

    # Routing Details
    destination_numbers = models.JSONField(default=list, blank=True, help_text="Array of numbers returned to Exotel")
    dialed_number = models.CharField(max_length=50, blank=True, help_text="Number of agent who was dialed or answered")
    digits_pressed = models.CharField(max_length=20, blank=True, help_text="IVR input digits entered by caller")
    custom_field = models.TextField(blank=True, help_text="Custom field passed by API/Exotel")
    flow_id = models.CharField(max_length=100, blank=True, help_text="Exotel Flow ID")

    # Linked Entities
    provider = models.ForeignKey(
        'authentication.ServiceProviderProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='call_logs',
        help_text="Service Provider connected to this call, if identified"
    )
    lead = models.ForeignKey(
        'leads.Lead',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='call_logs',
        help_text="Associated Lead, if identified"
    )
    package = models.ForeignKey(
        'packages.Package',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='call_logs',
        help_text="Associated Package, if identified"
    )

    # Caller details & Agent notes
    caller_name = models.CharField(max_length=150, blank=True, help_text="Name of caller/pilgrim if known")
    notes = models.TextField(blank=True, help_text="Call notes or remarks added by provider/admin")
    call_outcome = models.CharField(max_length=50, blank=True, default='', help_text="Outcome: interested, booked, not_interested, etc.")

    # Call Outcome & Metadata
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='initiated', db_index=True)
    call_type = models.CharField(max_length=50, blank=True, help_text="completed, client-hangup, incomplete, etc.")
    duration = models.PositiveIntegerField(default=0, help_text="Total call duration in seconds")
    conversation_duration = models.PositiveIntegerField(default=0, help_text="Actual conversation time in seconds")
    recording_url = models.URLField(max_length=500, blank=True, null=True, help_text="Call recording audio URL")

    # Raw Payloads
    raw_connect_payload = models.JSONField(default=dict, blank=True)
    raw_event_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'telephony_call_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['call_sid']),
            models.Index(fields=['call_from']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    @property
    def pilgrim_phone(self):
        """
        Guarantees returning the real phone number of the pilgrim/customer.
        - For incoming calls: pilgrim is call_from
        - For outbound bridge calls: pilgrim is call_to
        """
        if self.direction == 'outbound-api':
            return self.call_to or ""
        return self.call_from or ""

    @property
    def agent_phone(self):
        """
        Guarantees returning the real phone number of the provider/agent.
        - For incoming calls: agent is dialed_number or provider business phone
        - For outbound bridge calls: agent is call_from
        """
        if self.direction == 'outbound-api':
            return self.call_from or (self.provider.business_phone if self.provider else "")
        if self.provider and (self.provider.business_phone or (self.provider.user and self.provider.user.phone)):
            return self.provider.business_phone or self.provider.user.phone
        if self.dialed_number and '8047289252' not in self.dialed_number:
            return self.dialed_number
        if self.destination_numbers and len(self.destination_numbers) > 0:
            dest = self.destination_numbers[0]
            if dest and '8047289252' not in dest:
                return dest
        from django.conf import settings
        return getattr(settings, 'EXOTEL_DEFAULT_SUPPORT_NUMBER', '+919760316409')

    @property
    def mask_phone(self):
        """The virtual ExoPhone number (e.g. 080-472-89252) used for privacy masking"""
        from django.conf import settings
        default_outgoing = getattr(settings, 'EXOTEL_OUTGOING_PHONE_NUMBER', '080-472-89252')
        if self.direction == 'incoming' and self.call_to:
            return self.call_to
        return default_outgoing

    @property
    def status_category(self):
        """Categorize into received, missed, cut, ringing, failed"""
        s = (self.status or '').lower()
        if s == 'completed':
            return 'received'
        elif s in ['no-answer', 'busy', 'canceled', 'failed', 'incomplete', 'free', 'timeout']:
            return 'missed'
        elif s == 'client-hangup':
            return 'cut'
        elif s in ['initiated', 'ringing', 'in-progress']:
            return 'ringing'
        return 'other'

    @property
    def status_label(self):
        """Human readable status label for provider panel"""
        cat = self.status_category
        if cat == 'received':
            return 'Call Received'
        elif cat == 'missed':
            return 'Missed Call'
        elif cat == 'cut':
            return 'Call Cut / Disconnected'
        elif cat == 'ringing':
            return 'Ringing'
        return self.status.replace('-', ' ').title()

    def __str__(self):
        target = self.dialed_number or (self.destination_numbers[0] if self.destination_numbers else self.call_to)
        return f"Exotel Call {self.call_sid} ({self.call_from} -> {target}) [{self.status_label}]"


class CallSession(BaseModel):
    """
    Temporary session created when a pilgrim clicks 'Call Partner' on website/app.
    Maps pilgrim's phone or session code to the provider for 15 minutes.
    Enables zero-touch automatic routing without manual keypad entry.
    """
    pilgrim_phone = models.CharField(max_length=50, blank=True, db_index=True)
    provider = models.ForeignKey(
        'authentication.ServiceProviderProfile',
        on_delete=models.CASCADE,
        related_name='call_sessions'
    )
    package = models.ForeignKey(
        'packages.Package',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='call_sessions'
    )
    lead = models.ForeignKey(
        'leads.Lead',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='call_sessions'
    )
    session_code = models.CharField(max_length=20, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = 'telephony_call_sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['pilgrim_phone', 'is_active', 'expires_at']),
            models.Index(fields=['session_code', 'is_active']),
        ]

    def __str__(self):
        return f"Session: {self.pilgrim_phone} -> Provider #{self.provider_id} (Code {self.session_code})"
