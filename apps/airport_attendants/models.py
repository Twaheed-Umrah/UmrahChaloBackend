from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone

from .private_storage import private_kyc_storage


class Airport(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=10, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AirportAttendant(models.Model):
    airport = models.ForeignKey(Airport, on_delete=models.PROTECT, related_name='attendants')
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    profile_image = models.ImageField(
        upload_to='airport_attendants/profiles/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        blank=True,
    )
    pan_document = models.FileField(
        upload_to='airport_attendants/pan/',
        storage=private_kyc_storage,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        blank=True,
    )
    aadhaar_document = models.FileField(
        upload_to='airport_attendants/aadhaar/',
        storage=private_kyc_storage,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['airport__name', 'name']

    def clean(self):
        super().clean()
        has_pan = bool(self.pan_document)
        has_aadhaar = bool(self.aadhaar_document)
        if has_pan == has_aadhaar:
            raise ValidationError(
                'Upload exactly one KYC document: either PAN card or Aadhaar card, not both.'
            )

    def __str__(self):
        return f'{self.name} ({self.airport.name})'


class AirportAttendantBooking(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = 'awaiting_payment', 'Awaiting payment'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'

    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='airport_attendant_bookings',
    )
    airport = models.ForeignKey(Airport, on_delete=models.PROTECT, related_name='bookings')
    attendant = models.ForeignKey(
        AirportAttendant,
        on_delete=models.PROTECT,
        related_name='bookings',
        null=True,
        blank=True,
    )
    service_date = models.DateField()
    service_time = models.TimeField()
    flight_name = models.CharField(max_length=150)
    flight_number = models.CharField(max_length=30)
    pilgrim_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(999)]
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    payment = models.ForeignKey(
        'payments.Payment',
        on_delete=models.PROTECT,
        related_name='airport_attendant_bookings',
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['airport', 'service_date', 'service_time', 'status']),
            models.Index(fields=['attendant', 'service_date', 'service_time', 'status']),
        ]

    @property
    def reservation_is_active(self):
        return (
            self.status == self.Status.AWAITING_PAYMENT
            and self.created_at >= timezone.now() - timedelta(minutes=15)
        )

    def __str__(self):
        return f'{self.airport.name} booking {self.id} ({self.service_date} {self.service_time})'
