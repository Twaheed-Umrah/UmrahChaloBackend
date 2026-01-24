from django.contrib import admin
from .models import Banner, PopularDestination, DestinationImage, VisitorTip

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'banner_type', 'get_provider', 
        'display_priority', 'priority_weight', 
        'target_city', 'target_state', 'is_active','display_order',
    ]
    list_filter = [
        'banner_type', 'display_priority', 'is_active',
        'target_city', 'target_state', 'target_country'
    ]
    search_fields = ['title', 'description', 'provider__email']
    list_editable = ['priority_weight', 'display_order', 'is_active']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'image', 'banner_type')
        }),
        ('Provider Information', {
            'fields': ('provider', 'provider_business_type')
        }),
        ('Location Targeting', {
            'fields': ('target_city', 'target_state', 'target_country')
        }),
        ('Priority & Scheduling', {
            'fields': ('display_priority', 'priority_weight', 'display_order',
                      'start_date', 'end_date', 'is_active')
        }),
        ('Targeting Filters', {
            'fields': ('target_user_types',)
        }),
        ('Link', {
            'fields': ('external_url',)
        }),
    )
    
    def get_provider(self, obj):
        if obj.provider:
            try:
                return obj.provider.service_provider_profile.business_name
            except:
                return obj.provider.email
        return "My Company"
    get_provider.short_description = 'Provider'

class DestinationImageInline(admin.TabularInline):
    model = DestinationImage
    extra = 1

class VisitorTipInline(admin.TabularInline):
    model = VisitorTip
    extra = 1

@admin.register(PopularDestination)
class PopularDestinationAdmin(admin.ModelAdmin):
    list_display = ['name', 'destination_type', 'ziyarat_type', 'city', 'view_count', 'is_featured']
    list_filter = ['destination_type', 'ziyarat_type', 'is_featured', 'is_active']
    search_fields = ['name', 'short_description', 'location']
    inlines = [DestinationImageInline, VisitorTipInline]
    list_editable = ['is_featured']
    readonly_fields = ['view_count', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'destination_type', 'ziyarat_type',
                      'short_description', 'detailed_description', 'image')
        }),
        ('Location Information', {
            'fields': ('location', 'city', 'country')
        }),
        ('Religious Information', {
            'fields': ('historical_significance', 'prayers_recommended', 
                      'rituals_associated', 'best_time_to_visit')
        }),
        ('Practical Information', {
            'fields': ('visiting_hours', 'dress_code', 'accessibility_info')
        }),
        ('Media', {
            'fields': ('video_url', 'gallery_images')
        }),
        ('Display Settings', {
            'fields': ('view_count', 'is_featured', 'display_order', 'is_active')
        }),
    )