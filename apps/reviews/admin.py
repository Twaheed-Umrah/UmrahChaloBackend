from django.contrib import admin
from .models import Review, ReviewHelpful, ReviewReport, ReviewResponse


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'get_item', 'rating', 'status', 
        'is_verified_purchase', 'helpful_count', 'reported_count', 'reviewed_at'
    )
    list_filter = ('status', 'rating', 'is_verified_purchase')
    search_fields = ('user__username', 'title', 'comment', 'service__name', 'package__name')
    ordering = ('-reviewed_at',)
    readonly_fields = ('created_at', 'updated_at')

    def get_item(self, obj):
        return obj.service.name if obj.service else obj.package.name if obj.package else "-"
    get_item.short_description = 'Service/Package'


@admin.register(ReviewHelpful)
class ReviewHelpfulAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'review', 'is_helpful')
    list_filter = ('is_helpful',)
    search_fields = ('user__username', 'review__title')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'reporter', 'review', 'reason', 'status', 
        'resolved_by', 'resolved_at'
    )
    list_filter = ('reason', 'status')
    search_fields = ('reporter__username', 'review__title', 'description', 'admin_notes')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ReviewResponse)
class ReviewResponseAdmin(admin.ModelAdmin):
    list_display = ('id', 'review', 'responder', 'is_official')
    list_filter = ('is_official',)
    search_fields = ('review__title', 'responder__username', 'response_text')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
