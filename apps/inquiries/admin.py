from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import ContactInquiry, ChatSession


# ─── Contact Inquiry Admin ──────────────────────────────────────────────────

@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'colored_name', 'email', 'phone',
        'service_interest', 'status_badge', 'status', 'created_at'
    )

    list_filter = ('status', 'service_interest', 'created_at')
    search_fields = ('name', 'email', 'phone', 'message')
    list_editable = ('status',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    actions = ['mark_in_progress', 'mark_resolved', 'mark_closed', 'delete_selected']

    readonly_fields = ('ip_address', 'created_at', 'updated_at', 'message_display')

    fieldsets = (
        ('👤 Visitor Information', {
            'fields': ('name', 'email', 'phone', 'service_interest'),
        }),
        ('📝 Message', {
            'fields': ('message_display',),
        }),
        ('🔧 Admin Management', {
            'fields': ('status', 'admin_notes'),
        }),
        ('📋 Meta', {
            'fields': ('ip_address', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # ── Custom display columns ─────────────────────────────────────────────
    def colored_name(self, obj):
        return format_html('<strong style="color:#1a73e8">{}</strong>', obj.name)
    colored_name.short_description = 'Name'

    def status_badge(self, obj):
        colors = {
            'new':         ('#dc2626', '🆕 New'),
            'in_progress': ('#d97706', '🔄 In Progress'),
            'resolved':    ('#059669', '✅ Resolved'),
            'closed':      ('#6b7280', '🔒 Closed'),
        }
        color, label = colors.get(obj.status, ('#6b7280', obj.status))
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600">{}</span>',
            color, label
        )
    status_badge.short_description = 'Status'

    def message_display(self, obj):
        return format_html(
            '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;'
            'font-size:14px;line-height:1.7;color:#374151;white-space:pre-wrap">{}</div>',
            obj.message
        )
    message_display.short_description = 'Message'

    # ── Bulk actions ───────────────────────────────────────────────────────
    @admin.action(description='✅ Mark selected as In Progress')
    def mark_in_progress(self, request, queryset):
        updated = queryset.update(status='in_progress')
        self.message_user(request, f'{updated} inquiry/inquiries marked as In Progress.')

    @admin.action(description='✅ Mark selected as Resolved')
    def mark_resolved(self, request, queryset):
        updated = queryset.update(status='resolved')
        self.message_user(request, f'{updated} inquiry/inquiries marked as Resolved.')

    @admin.action(description='🔒 Mark selected as Closed')
    def mark_closed(self, request, queryset):
        updated = queryset.update(status='closed')
        self.message_user(request, f'{updated} inquiry/inquiries marked as Closed.')


# ─── Chat Session Admin ─────────────────────────────────────────────────────

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = (
        'short_session_id', 'visitor_name_display', 'visitor_email',
        'visitor_phone', 'total_messages', 'topics_badge',
        'created_at'
    )
    list_filter = ('created_at',)
    search_fields = ('visitor_name', 'visitor_email', 'visitor_phone', 'session_id')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    actions = ['delete_selected']

    readonly_fields = (
        'session_id', 'total_messages', 'created_at',
        'conversation_display', 'topics_display',
        'started_at', 'ended_at',
    )

    fieldsets = (
        ('👤 Visitor Details', {
            'fields': ('session_id', 'visitor_name', 'visitor_email', 'visitor_phone'),
            'description': 'These fields are collected during the chatbot conversation.',
        }),
        ('💬 Conversation', {
            'fields': ('conversation_display',),
        }),
        ('🏷️ Topics & Stats', {
            'fields': ('topics_display', 'total_messages', 'started_at', 'ended_at'),
        }),
        ('📋 Meta', {
            'fields': ('ip_address', 'created_at'),
            'classes': ('collapse',),
        }),
    )

    # ── Custom display columns ─────────────────────────────────────────────
    def short_session_id(self, obj):
        return format_html(
            '<code style="background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:12px">{}</code>',
            str(obj.session_id)[:12] + '…'
        )
    short_session_id.short_description = 'Session'

    def visitor_name_display(self, obj):
        if obj.visitor_name:
            return format_html('<strong>{}</strong>', obj.visitor_name)
        return format_html('<em style="color:#9ca3af">Anonymous</em>')
    visitor_name_display.short_description = 'Name'

    def topics_badge(self, obj):
        count = len(obj.topics_discussed)
        if count == 0:
            return format_html('<span style="color:#9ca3af">—</span>')
        return format_html(
            '<span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:10px;font-size:12px">{} topics</span>',
            count
        )
    topics_badge.short_description = 'Topics'

    # ── Detail view renderers ──────────────────────────────────────────────
    def conversation_display(self, obj):
        if not obj.messages:
            return format_html('<em style="color:#9ca3af">No messages recorded.</em>')

        rows = []
        for msg in obj.messages:
            sender = msg.get('sender', 'unknown')
            text = msg.get('text', '').replace('\n', '<br>')
            timestamp = msg.get('timestamp', '')
            is_user = sender == 'user'

            bg = '#eff6ff' if is_user else '#f0fdf4'
            border = '#bfdbfe' if is_user else '#bbf7d0'
            label_color = '#1d4ed8' if is_user else '#15803d'
            icon = '👤' if is_user else '🤖'
            label = 'User' if is_user else 'Bot'

            rows.append(
                f'<div style="margin:8px 0;padding:10px 14px;background:{bg};border-left:3px solid {border};'
                f'border-radius:6px">'
                f'<div style="font-size:11px;color:{label_color};font-weight:700;margin-bottom:4px">'
                f'{icon} {label} &nbsp;·&nbsp; <span style="color:#9ca3af;font-weight:400">{timestamp}</span></div>'
                f'<div style="font-size:13px;color:#374151;line-height:1.6">{text}</div>'
                f'</div>'
            )

        return format_html(
            '<div style="max-height:500px;overflow-y:auto;border:1px solid #e5e7eb;'
            'border-radius:8px;padding:12px;background:#fff">{}</div>',
            mark_safe(''.join(rows))
        )
    conversation_display.short_description = 'Full Conversation'

    def topics_display(self, obj):
        if not obj.topics_discussed:
            return format_html('<em style="color:#9ca3af">No topics recorded.</em>')
        badges = ''.join(
            f'<span style="display:inline-block;margin:3px;padding:4px 10px;background:#ede9fe;'
            f'color:#5b21b6;border-radius:12px;font-size:12px;font-weight:500">{t}</span>'
            for t in obj.topics_discussed
        )
        return format_html('<div style="line-height:2">{}</div>', mark_safe(badges))
    topics_display.short_description = 'Topics Discussed'
