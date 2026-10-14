# apps/telephony/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import CallLog


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = [
        'call_sid',
        'call_from',
        'call_to',
        'display_destination',
        'direction',
        'status_badge',
        'duration_display',
        'recording_player',
        'created_at',
    ]
    list_filter = ['status', 'direction', 'call_type', 'created_at']
    search_fields = [
        'call_sid',
        'call_from',
        'call_to',
        'dialed_number',
        'custom_field',
        'provider__business_name',
        'lead__full_name',
    ]
    readonly_fields = [
        'call_sid',
        'call_from',
        'call_to',
        'direction',
        'destination_numbers',
        'dialed_number',
        'digits_pressed',
        'custom_field',
        'flow_id',
        'provider',
        'lead',
        'status',
        'call_type',
        'duration',
        'conversation_duration',
        'recording_url',
        'recording_player',
        'raw_connect_payload',
        'raw_event_payload',
        'created_at',
        'updated_at',
    ]

    def display_destination(self, obj):
        if obj.dialed_number:
            return obj.dialed_number
        if obj.destination_numbers:
            return ", ".join(obj.destination_numbers)
        return "-"
    display_destination.short_description = "Routed To"

    def duration_display(self, obj):
        mins, secs = divmod(obj.duration, 60)
        return f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
    duration_display.short_description = "Duration"

    def status_badge(self, obj):
        colors = {
            'completed': '#10B981',
            'in-progress': '#3B82F6',
            'ringing': '#F59E0B',
            'busy': '#EF4444',
            'no-answer': '#EF4444',
            'failed': '#DC2626',
            'canceled': '#6B7280',
            'client-hangup': '#F97316',
        }
        color = colors.get(obj.status.lower(), '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = "Status"

    def recording_player(self, obj):
        if obj.recording_url:
            return format_html(
                '<a href="{}" target="_blank" style="color: #2563EB; font-weight: 500;">▶ Listen Audio</a>',
                obj.recording_url
            )
        return "-"
    recording_player.short_description = "Recording"
