from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Notification,
    NotificationPreference,
    NotificationLog,
    BulkNotification,
)

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    """Lightweight User serializer for notifications"""

    class Meta:
        model = User
        fields = ["id", "full_name", "email", "phone", "user_type", "is_verified"]


class NotificationSerializer(serializers.ModelSerializer):
    recipient = UserMiniSerializer(read_only=True)
    recipient_id = serializers.PrimaryKeyRelatedField(
        source="recipient", queryset=User.objects.all(), write_only=True
    )

    content_type = serializers.StringRelatedField(read_only=True)
    object_id = serializers.IntegerField(required=False, allow_null=True)
    content_object = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "recipient_id",
            "notification_type",
            "title",
            "message",
            "content_type",
            "object_id",
            "content_object",
            "data",
            "status",
            "priority",
            "send_email",
            "send_sms",
            "send_app",
            "created_at",
            "sent_at",
            "read_at",
            "email_sent",
            "sms_sent",
            "app_sent",
            "retry_count",
            "max_retries",
            "next_retry_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "sent_at",
            "read_at",
            "email_sent",
            "sms_sent",
            "app_sent",
            "retry_count",
            "next_retry_at",
        ]

    def get_content_object(self, obj):
        return str(obj.content_object) if obj.content_object else None


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=User.objects.all(), write_only=True
    )

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "user",
            "user_id",
            # Email preferences
            "email_lead_notifications",
            "email_subscription_notifications",
            "email_package_notifications",
            "email_review_notifications",
            "email_pay_notifications",
            "email_verification_notifications",
            "email_marketing",
            # SMS preferences
            "sms_lead_notifications",
            "sms_subscription_notifications",
            "sms_package_notifications",
            "sms_review_notifications",
            "sms_payment_notifications",
            "sms_verification_notifications",
            "sms_marketing",
            # App preferences
            "app_lead_notifications",
            "app_subscription_notifications",
            "app_package_notifications",
            "app_review_notifications",
            "app_payment_notifications",
            "app_verification_notifications",
            "app_marketing",
            # Frequency & quiet hours
            "digest_frequency",
            "quiet_hours_start",
            "quiet_hours_end",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationLogSerializer(serializers.ModelSerializer):
    notification = serializers.PrimaryKeyRelatedField(
        queryset=Notification.objects.all()
    )
    notification_title = serializers.CharField(
        source="notification.title", read_only=True
    )
    recipient = serializers.CharField(
        source="notification.recipient.email", read_only=True
    )

    class Meta:
        model = NotificationLog
        fields = [
            "id",
            "notification",
            "notification_title",
            "recipient",
            "channel",
            "sent_at",
            "delivered",
            "delivered_at",
            "provider",
            "provider_response",
            "error_message",
            "error_code",
        ]
        read_only_fields = ["id", "sent_at", "delivered_at"]


class BulkNotificationSerializer(serializers.ModelSerializer):
    created_by = UserMiniSerializer(read_only=True)
    created_by_id = serializers.PrimaryKeyRelatedField(
        source="created_by", queryset=User.objects.all(), write_only=True
    )

    class Meta:
        model = BulkNotification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "target_user_type",
            "target_filters",
            "send_email",
            "send_sms",
            "send_app",
            "scheduled_at",
            "status",
            "total_recipients",
            "sent_count",
            "failed_count",
            "created_by",
            "created_by_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "total_recipients",
            "sent_count",
            "failed_count",
        ]
