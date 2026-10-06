from django.test import SimpleTestCase

from .serializers import LeadCreateSerializer


class LeadCreateSerializerTests(SimpleTestCase):
    def test_email_is_optional_and_may_be_blank(self):
        serializer = LeadCreateSerializer(data={
            'lead_type': 'custom',
            'full_name': 'Test Customer',
            'email': '',
            'phone': '+919876543210',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_email_may_be_omitted(self):
        serializer = LeadCreateSerializer(data={
            'lead_type': 'custom',
            'full_name': 'Test Customer',
            'phone': '+919876543210',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
