from django.contrib import admin
from .models import Lead, LeadDistribution, LeadInteraction, LeadNote


class LeadDistributionInline(admin.TabularInline):
    model = LeadDistribution
    extra = 0
    readonly_fields = ('sent_at', 'viewed_at', 'responded_at')
    autocomplete_fields = ('provider',)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone', 'lead_type', 'status', 'is_distributed', 'distribution_date', 'created_at', 'service_provider')
    list_filter = ('is_distributed', 'status', 'lead_type', 'created_at', 'service_provider')
    search_fields = ('full_name', 'email', 'phone', 'departure_city')
    autocomplete_fields = ('user', 'package', 'service', 'service_provider')
    inlines = [LeadDistributionInline]
    actions = ['distribute_to_subscribed_providers']

    @admin.action(description="Distribute selected leads to Subscribed Providers")
    def distribute_to_subscribed_providers(self, request, queryset):
        from .serializers import LeadManualDistributionSerializer
        success_count = 0
        error_count = 0
        for lead in queryset:
            try:
                serializer = LeadManualDistributionSerializer(data={
                    'lead_id': lead.id,
                    'only_subscribed_providers': True,
                    'deduct_credits': True
                })
                if serializer.is_valid():
                    serializer.distribute_lead()
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
        
        if success_count:
            self.message_user(request, f"Successfully distributed {success_count} lead(s) to active subscribed providers.")
        if error_count:
            self.message_user(request, f"Failed to distribute {error_count} lead(s).", level='error')


@admin.register(LeadDistribution)
class LeadDistributionAdmin(admin.ModelAdmin):
    list_display = ('lead', 'provider', 'status', 'sent_at', 'viewed_at', 'responded_at')
    list_filter = ('status', 'sent_at')
    search_fields = ('lead__full_name', 'provider__business_name')
    autocomplete_fields = ('lead', 'provider')


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

