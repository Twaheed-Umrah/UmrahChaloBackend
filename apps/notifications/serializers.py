from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Notification, NotificationTemplate, NotificationPreference,
    NotificationLog, BulkNotification
)

User = get_user_model()


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Serializer for notification templates"""
    
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'notification_type', 'title', 'email_subject', 
            'email_body', 'sms_body', 'app_body', 'send_email', 
            'send_sms', 'send_app', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    
    template_type = serializers.CharField(source='template.notification_type', read_only=True)
    template_title = serializers.CharField(source='template.title', read_only=True)
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)
    recipient_email = serializers.EmailField(source='recipient.email', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'recipient_name', 'recipient_email',
            'template', 'template_type', 'template_title', 'title', 
            'message', 'data', 'status', 'priority', 'created_at', 
            'sent_at', 'read_at', 'email_sent', 'sms_sent', 'app_sent',
            'retry_count', 'max_retries'
        ]
        read_only_fields = [
            'id', 'created_at', 'sent_at', 'read_at', 'email_sent', 
            'sms_sent', 'app_sent', 'retry_count', 'recipient_name',
            'recipient_email', 'template_type', 'template_title'
        ]


class NotificationListSerializer(serializers.ModelSerializer):
    """Simplified serializer for notification lists"""
    
    template_type = serializers.CharField(source='template.notification_type', read_only=True)
    is_read = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'template_type', 'priority',
            'status', 'is_read', 'created_at', 'read_at'
        ]
        read_only_fields = fields
    
    def get_is_read(self, obj):
        return obj.status == 'read'


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences"""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'email_lead_notifications', 'email_subscription_notifications',
            'email_package_notifications', 'email_review_notifications', 'email_marketing',
            'sms_lead_notifications', 'sms_subscription_notifications', 
            'sms_package_notifications', 'sms_review_notifications', 'sms_marketing',
            'app_lead_notifications', 'app_subscription_notifications',
            'app_package_notifications', 'app_review_notifications', 'app_marketing',
            'digest_frequency', 'quiet_hours_start', 'quiet_hours_end',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validate quiet hours"""
        quiet_start = data.get('quiet_hours_start')
        quiet_end = data.get('quiet_hours_end')
        
        if quiet_start and quiet_end:
            if quiet_start >= quiet_end:
                raise serializers.ValidationError({
                    'quiet_hours_end': 'Quiet hours end time must be after start time'
                })
        
        return data


class NotificationLogSerializer(serializers.ModelSerializer):
    """Serializer for notification logs"""
    
    notification_title = serializers.CharField(source='notification.title', read_only=True)
    recipient_email = serializers.EmailField(source='notification.recipient.email', read_only=True)
    
    class Meta:
        model = NotificationLog
        fields = [
            'id', 'notification', 'notification_title', 'recipient_email',
            'channel', 'sent_at', 'delivered', 'delivered_at', 
            'provider', 'provider_response', 'error_message', 'error_code'
        ]
        read_only_fields = fields


class BulkNotificationSerializer(serializers.ModelSerializer):
    """Serializer for bulk notifications"""
    
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    success_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = BulkNotification
        fields = [
            'id', 'title', 'message', 'target_user_type', 'target_filters',
            'send_email', 'send_sms', 'send_app', 'scheduled_at', 'status',
            'total_recipients', 'sent_count', 'failed_count', 'success_rate',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
            'started_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'total_recipients', 'sent_count', 'failed_count',
            'success_rate', 'created_by_name', 'created_at', 'updated_at',
            'started_at', 'completed_at'
        ]
    
    def get_success_rate(self, obj):
        """Calculate success rate"""
        if obj.total_recipients > 0:
            return round((obj.sent_count / obj.total_recipients) * 100, 2)
        return 0.0
    
    def validate(self, data):
        """Validate bulk notification data"""
        if data.get('scheduled_at'):
            from django.utils import timezone
            if data['scheduled_at'] < timezone.now():
                raise serializers.ValidationError({
                    'scheduled_at': 'Scheduled time must be in the future'
                })
        
        # At least one channel must be selected
        if not any([data.get('send_email', False), data.get('send_sms', False), data.get('send_app', False)]):
            raise serializers.ValidationError(
                'At least one notification channel must be selected'
            )
        
        return data


class CreateNotificationSerializer(serializers.ModelSerializer):
    """Serializer for creating notifications"""
    
    recipient_email = serializers.EmailField(write_only=True, required=False)
    template_type = serializers.CharField(write_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'recipient', 'recipient_email', 'template_type', 'title', 
            'message', 'data', 'priority'
        ]
    
    def validate(self, data):
        """Validate notification creation data"""
        if not data.get('recipient') and not data.get('recipient_email'):
            raise serializers.ValidationError(
                'Either recipient or recipient_email must be provided'
            )
        
        return data
    
    def create(self, validated_data):
        """Create notification with proper template"""
        template_type = validated_data.pop('template_type')
        recipient_email = validated_data.pop('recipient_email', None)
        
        # Get or create recipient
        if recipient_email and not validated_data.get('recipient'):
            try:
                recipient = User.objects.get(email=recipient_email)
                validated_data['recipient'] = recipient
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'recipient_email': 'User with this email does not exist'
                })
        
        # Get template
        try:
            template = NotificationTemplate.objects.get(
                notification_type=template_type,
                is_active=True
            )
            validated_data['template'] = template
        except NotificationTemplate.DoesNotExist:
            raise serializers.ValidationError({
                'template_type': 'Invalid or inactive notification template'
            })
        
        return super().create(validated_data)


class NotificationStatsSerializer(serializers.Serializer):
    """Serializer for notification statistics"""
    
    total_notifications = serializers.IntegerField()
    unread_notifications = serializers.IntegerField()
    sent_notifications = serializers.IntegerField()
    failed_notifications = serializers.IntegerField()
    
    # Channel stats
    email_sent = serializers.IntegerField()
    sms_sent = serializers.IntegerField()
    app_sent = serializers.IntegerField()
    
    # Recent activity
    notifications_today = serializers.IntegerField()
    notifications_this_week = serializers.IntegerField()
    notifications_this_month = serializers.IntegerField()


class MarkNotificationReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read"""
    
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100
    )
    
    def validate_notification_ids(self, value):
        """Validate that all notification IDs exist and belong to the user"""
        user = self.context['request'].user
        
        notifications = Notification.objects.filter(
            id__in=value,
            recipient=user
        )
        
        if len(notifications) != len(value):
            raise serializers.ValidationError(
                'Some notification IDs are invalid or do not belong to you'
            )
        
        return value