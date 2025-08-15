from django.contrib import admin
from .models import Lead, LeadDistribution, LeadInteraction, LeadNote

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone', 'lead_type', 'status', 'created_at', 'service_provider')
    list_filter = ('status', 'lead_type', 'created_at', 'service_provider')
    search_fields = ('full_name', 'email', 'phone', 'departure_city')
    autocomplete_fields = ('user', 'package', 'service', 'service_provider')

@admin.register(LeadDistribution)
class LeadDistributionAdmin(admin.ModelAdmin):
    list_display = ('lead', 'provider', 'status', 'sent_at', 'viewed_at', 'responded_at')
    list_filter = ('status',)
    search_fields = ('lead__full_name', 'provider__business_name')

@admin.register(LeadInteraction)
class LeadInteractionAdmin(admin.ModelAdmin):
    list_display = ('lead', 'provider', 'interaction_type', 'interaction_date', 'is_successful')
    list_filter = ('interaction_type', 'is_successful')
    search_fields = ('notes', 'outcome_notes')

@admin.register(LeadNote)
class LeadNoteAdmin(admin.ModelAdmin):
    list_display = ('lead', 'provider', 'is_private', 'created_at')
    list_filter = ('is_private',)
    search_fields = ('note',)
