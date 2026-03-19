from rest_framework import serializers
from .models import ContactInquiry, ChatSession


class ContactInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactInquiry
        fields = ['id', 'name', 'email', 'phone', 'service_interest', 'message', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be blank.")
        return value.strip()

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be blank.")
        return value.strip()


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = [
            'id', 'session_id', 'visitor_name', 'visitor_email',
            'visitor_phone', 'messages', 'topics_discussed',
            'total_messages', 'started_at', 'ended_at', 'created_at'
        ]
        read_only_fields = ['id', 'session_id', 'total_messages', 'ended_at', 'created_at']

    def validate_messages(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Messages must be a list.")
        return value
