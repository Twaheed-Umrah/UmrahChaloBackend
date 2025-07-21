from django.contrib import admin
from .models import Lead, LeadDistribution, LeadInteraction, LeadNote

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'full_name', 'email', 'phone', 'lead_type', 'status',
        'preferred_date', 'number_of_people', 'is_distributed', 'source', 'created_at'
    )
    list_filter = ('status', 'lead_type', 'is_distributed', 'source', 'preferred_date')
    search_fields = ('full_name', 'email', 'phone', 'custom_message', 'special_requirements')
    readonly_fields = ('expires_at', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ("User Info", {
            'fields': ('user', 'full_name', 'email', 'phone')
        }),
        ("Lead Source & Type", {
            'fields': ('lead_type', 'status', 'source', 'priority')
        }),
        ("Linked Package/Service", {
            'fields': ('package', 'service')
        }),
        ("Travel & Preferences", {
            'fields': ('preferred_date', 'number_of_people', 'budget_range', 'departure_city', 'preferred_hotel_category')
        }),
        ("Messages & Services", {
            'fields': ('special_requirements', 'custom_message', 'selected_services')
        }),
        ("Tracking", {
            'fields': ('is_distributed', 'distribution_date', 'expires_at')
        }),
        ("Timestamps", {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(LeadDistribution)
class LeadDistributionAdmin(admin.ModelAdmin):
    list_display = (
        'lead', 'provider', 'status', 'sent_at', 'viewed_at', 'responded_at',
        'email_sent', 'sms_sent', 'app_notification_sent'
    )
    list_filter = ('status', 'email_sent', 'sms_sent', 'app_notification_sent')
    search_fields = ('lead__full_name', 'provider__business_name', 'response_message')
    readonly_fields = ('sent_at', 'viewed_at', 'responded_at')
    ordering = ('-sent_at',)


@admin.register(LeadInteraction)
class LeadInteractionAdmin(admin.ModelAdmin):
    list_display = (
        'lead', 'provider', 'interaction_type', 'interaction_date', 'is_successful'
    )
    list_filter = ('interaction_type', 'is_successful')
    search_fields = ('lead__full_name', 'provider__business_name', 'notes', 'outcome_notes')
    date_hierarchy = 'interaction_date'
    ordering = ('-interaction_date',)


@admin.register(LeadNote)
class LeadNoteAdmin(admin.ModelAdmin):
    list_display = ('lead', 'provider', 'is_private', 'created_at')
    list_filter = ('is_private',)
    search_fields = ('lead__full_name', 'provider__business_name', 'note')
    ordering = ('-created_at',)
