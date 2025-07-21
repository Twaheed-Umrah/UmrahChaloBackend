from django.contrib import admin
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
    list_display = ('name', 'category', 'is_active')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'alt_text')
    ordering = ('-created_at',)


class ServiceAvailabilityInline(admin.TabularInline):
    model = ServiceAvailability
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


class ServiceFAQInline(admin.TabularInline):
    model = ServiceFAQ
    extra = 0


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'provider', 'service_type', 'status', 'price', 'country',
        'city', 'views_count', 'leads_count', 'bookings_count', 'is_featured'
    )
    list_filter = ('status', 'service_type', 'country', 'is_featured', 'is_popular', 'is_premium')
    search_fields = ('title', 'provider__user__email', 'city', 'state', 'country')
    readonly_fields = ('slug', 'views_count', 'leads_count', 'bookings_count', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    inlines = [ServiceAvailabilityInline, ServiceFAQInline]
    filter_horizontal = ('images',)


@admin.register(ServiceAvailability)
class ServiceAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('service', 'date', 'available_slots', 'booked_slots', 'is_available', 'remaining_slots')
    list_filter = ('is_available', 'date')
    search_fields = ('service__title',)
    ordering = ('date',)

    def remaining_slots(self, obj):
        return obj.remaining_slots


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
