from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import Airport, AirportAttendant, AirportAttendantBooking


class AirportAttendantAdminForm(forms.ModelForm):
    class Meta:
        model = AirportAttendant
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ('profile_image', 'pan_document', 'aadhaar_document'):
            uploaded_file = self.files.get(field_name)
            if uploaded_file and uploaded_file.size > 5 * 1024 * 1024:
                label = 'Profile images' if field_name == 'profile_image' else 'KYC documents'
                self.add_error(field_name, ValidationError(f'{label} must be 5 MB or smaller.'))
        return cleaned_data


@admin.register(Airport)
class AirportAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price', 'attendant_count', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Active attendants')
    def attendant_count(self, airport):
        return airport.attendants.filter(is_active=True).count()


@admin.register(AirportAttendant)
class AirportAttendantAdmin(admin.ModelAdmin):
    form = AirportAttendantAdminForm
    list_display = (
        'profile_image_preview',
        'name',
        'airport',
        'phone',
        'alternate_phone',
        'is_active',
        'created_at',
    )
    list_display_links = ('name',)
    list_filter = ('airport', 'is_active')
    search_fields = ('name', 'phone', 'alternate_phone', 'email', 'airport__name')
    ordering = ('airport__name', 'name')
    readonly_fields = (
        'profile_image_preview',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        ('Attendant profile', {
            'fields': (
                'airport',
                'name',
                'phone',
                'alternate_phone',
                'email',
                'profile_image',
                'profile_image_preview',
                'is_active',
            ),
        }),
        ('Private KYC documents', {
            'description': 'Upload exactly one document: PAN or Aadhaar. Keep these identity documents private.',
            'fields': ('pan_document', 'aadhaar_document'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Profile image')
    def profile_image_preview(self, attendant):
        if not attendant.profile_image:
            return 'No image'
        return format_html(
            '<img src="{}" alt="{} profile" style="height:48px;width:48px;object-fit:cover;border-radius:50%;" />',
            attendant.profile_image.url,
            attendant.name,
        )


@admin.register(AirportAttendantBooking)
class AirportAttendantBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'provider',
        'airport',
        'service_date',
        'service_time',
        'flight_number',
        'pilgrim_count',
        'amount',
        'status',
        'payment_status',
    )
    list_filter = ('status', 'airport', 'service_date')
    search_fields = (
        'provider__full_name',
        'provider__phone',
        'airport__name',
        'flight_name',
        'flight_number',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'service_date'
    readonly_fields = tuple(field.name for field in AirportAttendantBooking._meta.fields)

    @admin.display(description='Payment status')
    def payment_status(self, booking):
        return booking.payment.status if booking.payment_id else 'Not started'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
