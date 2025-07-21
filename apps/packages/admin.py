from django.contrib import admin
from .models import (
    Package,
    PackageService,
    PackageInclusion,
    PackageExclusion,
    PackageItinerary,
    PackageImage,
    PackagePolicy,
    PackageAvailability
)

class PackageServiceInline(admin.TabularInline):
    model = PackageService
    extra = 1

class PackageInclusionInline(admin.TabularInline):
    model = PackageInclusion
    extra = 1

class PackageExclusionInline(admin.TabularInline):
    model = PackageExclusion
    extra = 1

class PackageItineraryInline(admin.TabularInline):
    model = PackageItinerary
    extra = 1

class PackageImageInline(admin.TabularInline):
    model = PackageImage
    extra = 1

class PackagePolicyInline(admin.TabularInline):
    model = PackagePolicy
    extra = 1

class PackageAvailabilityInline(admin.TabularInline):
    model = PackageAvailability
    extra = 1


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'provider', 'package_type', 'status', 'start_date',
        'booking_deadline', 'final_price', 'current_bookings', 'max_capacity',
        'is_featured', 'is_active', 'views_count'
    )
    list_filter = ('status', 'package_type', 'is_featured', 'is_active', 'start_date')
    search_fields = ('name', 'provider__business_name', 'slug', 'description')
    date_hierarchy = 'start_date'
    ordering = ('-is_featured', '-created_at')
    readonly_fields = ('slug', 'verified_at', 'views_count', 'leads_count', 'rating', 'reviews_count', 'created_at', 'updated_at')

    fieldsets = (
        ("Basic Info", {
            'fields': ('name', 'slug', 'description', 'package_type', 'provider', 'featured_image')
        }),
        ("Pricing & Duration", {
            'fields': ('base_price', 'discounted_price', 'duration_days')
        }),
        ("Dates & Capacity", {
            'fields': ('start_date', 'end_date', 'booking_deadline', 'max_capacity', 'current_bookings')
        }),
        ("Status & Verification", {
            'fields': ('status', 'verified_by', 'verified_at', 'rejection_reason')
        }),
        ("Metrics", {
            'fields': ('views_count', 'leads_count', 'rating', 'reviews_count')
        }),
        ("Visibility", {
            'fields': ('is_active', 'is_featured')
        }),
        ("Timestamps", {
            'fields': ('created_at', 'updated_at')
        }),
    )

    inlines = [
        PackageServiceInline,
        PackageInclusionInline,
        PackageExclusionInline,
        PackageItineraryInline,
        PackageImageInline,
        PackagePolicyInline,
        PackageAvailabilityInline
    ]


@admin.register(PackageService)
class PackageServiceAdmin(admin.ModelAdmin):
    list_display = ('package', 'service', 'is_included', 'is_optional', 'additional_price', 'quantity')
    list_filter = ('is_included', 'is_optional')
    search_fields = ('package__name', 'service__name')


@admin.register(PackageInclusion)
class PackageInclusionAdmin(admin.ModelAdmin):
    list_display = ('package', 'title', 'is_highlighted', 'order')
    list_filter = ('is_highlighted',)
    search_fields = ('package__name', 'title')


@admin.register(PackageExclusion)
class PackageExclusionAdmin(admin.ModelAdmin):
    list_display = ('package', 'title', 'order')
    search_fields = ('package__name', 'title')


@admin.register(PackageItinerary)
class PackageItineraryAdmin(admin.ModelAdmin):
    list_display = ('package', 'day_number', 'title', 'location')
    search_fields = ('package__name', 'title', 'location')
    ordering = ('package', 'day_number')


@admin.register(PackageImage)
class PackageImageAdmin(admin.ModelAdmin):
    list_display = ('package', 'image', 'caption', 'is_featured', 'order')
    list_filter = ('is_featured',)
    search_fields = ('package__name', 'caption')


@admin.register(PackagePolicy)
class PackagePolicyAdmin(admin.ModelAdmin):
    list_display = ('package', 'policy_type', 'title', 'order')
    list_filter = ('policy_type',)
    search_fields = ('package__name', 'title')
    ordering = ('package', 'order')


@admin.register(PackageAvailability)
class PackageAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('package', 'date', 'available_slots', 'price_adjustment', 'is_available', 'color_code')
    list_filter = ('is_available', 'date')
    search_fields = ('package__name',)
    ordering = ('package', 'date')
