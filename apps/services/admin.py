from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ServiceCategory,
    ServiceImage,
    Service,
    ServiceAvailability,
    ServiceFAQ,
    ServiceView
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('display_order', 'name')


@admin.register(ServiceImage)
class ServiceImageAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'thumbnail')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'alt_text')
    ordering = ('-created_at',)

    def thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;"/>', obj.image.url)
        return "-"
    thumbnail.short_description = "Preview"


class ServiceAvailabilityInline(admin.TabularInline):
    model = ServiceAvailability
    extra = 0
    readonly_fields = ('created_at', 'updated_at', 'remaining_slots', 'is_fully_booked')


class ServiceFAQInline(admin.TabularInline):
    model = ServiceFAQ
    extra = 0


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'provider_name', 'service_type', 'status',
        'price', 'original_price', 'discount_percentage',
        'country', 'city', 'views_count', 'bookings_count',
        'is_featured', 'is_popular', 'is_premium'
    )
    list_filter = (
        'status', 'service_type', 'country',
        'is_featured', 'is_popular', 'is_premium',
        'created_at'
    )
    search_fields = (
        'title', 'provider__user__email',
        'provider__user__username',
        'city', 'state', 'country'
    )
    readonly_fields = (
        'slug', 'views_count', 'leads_count', 'bookings_count',
        'created_at', 'updated_at', 'discount_percentage'
    )
    ordering = ('-created_at',)
    inlines = [ServiceAvailabilityInline, ServiceFAQInline]
    list_editable = ('status', 'is_featured', 'is_popular', 'is_premium')
    autocomplete_fields = ('provider', 'category', 'images', 'featured_image', 'verified_by')

    fieldsets = (
        ("Basic Info", {
            "fields": ("title", "slug", "provider", "service_type", "category", "status", "verified_by", "verified_at")
        }),
        ("Descriptions", {
            "fields": ("description", "short_description")
        }),
        ("Pricing", {
            "fields": ("price", "original_price", "price_currency", "price_per", "discount_percentage")
        }),
        ("Location", {
            "fields": ("city", "state", "country")
        }),
        ("Availability", {
            "fields": ("is_always_available", "available_from", "available_to")
        }),
        ("Images", {
            "fields": ("featured_image", "images")
        }),
        ("Flags", {
            "fields": ("is_featured", "is_popular", "is_premium")
        }),
        ("Analytics", {
            "fields": ("views_count", "leads_count", "bookings_count")
        }),
        ("SEO", {
            "fields": ("meta_title", "meta_description")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def provider_name(self, obj):
        return obj.provider.user.get_full_name() or obj.provider.user.username
    provider_name.short_description = "Provider"


@admin.register(ServiceAvailability)
class ServiceAvailabilityAdmin(admin.ModelAdmin):
    list_display = (
        'service', 'date', 'available_slots', 'booked_slots',
        'remaining_slots', 'is_available', 'is_fully_booked'
    )
    list_filter = ('is_available', 'date')
    search_fields = ('service__title',)
    ordering = ('date',)
    readonly_fields = ('remaining_slots', 'is_fully_booked')

    def remaining_slots(self, obj):
        return obj.remaining_slots

    def is_fully_booked(self, obj):
        return obj.is_fully_booked


@admin.register(ServiceFAQ)
class ServiceFAQAdmin(admin.ModelAdmin):
    list_display = ('service', 'question', 'display_order')
    search_fields = ('service__title', 'question')
    ordering = ('display_order',)


@admin.register(ServiceView)
class ServiceViewAdmin(admin.ModelAdmin):
    list_display = ('service', 'provider', 'ip_address', 'viewed_at')
    list_filter = ('viewed_at',)
    search_fields = ('service__title', 'provider__user__email', 'ip_address')
    ordering = ('-viewed_at',)
