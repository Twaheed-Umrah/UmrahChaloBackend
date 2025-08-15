from django.contrib import admin
from .models import (
    Package, PackageService, PackageInclusion, PackageExclusion,
    PackageItinerary, PackageImage, PackagePolicy, PackageAvailability
)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'package_type', 'provider', 'status', 'start_date', 'end_date', 'is_active', 'is_featured')
    list_filter = ('status', 'package_type', 'is_active', 'is_featured')
    search_fields = ('name', 'provider__user__first_name', 'provider__user__email')
    readonly_fields = ('slug',)
    ordering = ('-created_at',)


@admin.register(PackageService)
class PackageServiceAdmin(admin.ModelAdmin):
    list_display = ('package', 'service', 'is_included', 'is_optional', 'additional_price', 'quantity')
    list_filter = ('is_included', 'is_optional')
    search_fields = ('package__name', 'service__name')
    autocomplete_fields = ('package', 'service')


admin.site.register(PackageInclusion)
admin.site.register(PackageExclusion)
admin.site.register(PackageItinerary)
admin.site.register(PackageImage)
admin.site.register(PackagePolicy)
admin.site.register(PackageAvailability)
