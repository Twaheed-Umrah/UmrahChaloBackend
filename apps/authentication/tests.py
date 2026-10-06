from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase
from unittest.mock import patch

from .models import LoginAttempt
from .serializers import ServiceProviderRegistrationSerializer, UserRegistrationSerializer

User = get_user_model()


class OptionalEmailRegistrationTests(TestCase):
    def test_registration_allows_phone_without_email_and_preserves_existing_email(self):
        existing_user = User.objects.create_user(
            username='existing-email-user',
            email='existing@example.com',
            password='Safe-password-123',
            phone='+919876543210',
        )

        serializer = UserRegistrationSerializer(data={
            'full_name': 'Phone Only User',
            'phone': '+919876543211',
            'password': 'Safe-password-123',
            'confirm_password': 'Safe-password-123',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        new_user = serializer.save()

        existing_user.refresh_from_db()
        self.assertEqual(existing_user.email, 'existing@example.com')
        self.assertIsNone(new_user.email)
        self.assertEqual(new_user.phone, '+919876543211')

    @patch('apps.authentication.serializers.secrets.token_urlsafe', side_effect=['random-secret-one', 'random-secret-two'])
    def test_registration_generates_a_unique_password_when_omitted(self, generate_password):
        users = []
        for phone in ('+919876543214', '+919876543215'):
            serializer = UserRegistrationSerializer(data={
                'full_name': 'OTP Registered User',
                'phone': phone,
            })
            self.assertTrue(serializer.is_valid(), serializer.errors)
            users.append(serializer.save())

        self.assertTrue(users[0].check_password('random-secret-one'))
        self.assertTrue(users[1].check_password('random-secret-two'))
        self.assertFalse(users[0].check_password('random-secret-two'))
        self.assertFalse(users[1].check_password('random-secret-one'))
        self.assertNotIn('password', serializer.data)
        self.assertEqual(generate_password.call_count, 2)

    def test_registration_still_rejects_duplicate_phone(self):
        User.objects.create_user(
            username='existing-phone-user',
            email='existing-phone@example.com',
            password='Safe-password-123',
            phone='+919876543210',
        )

        serializer = UserRegistrationSerializer(data={
            'full_name': 'Duplicate Phone User',
            'phone': '+919876543210',
            'password': 'Safe-password-123',
            'confirm_password': 'Safe-password-123',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('phone', serializer.errors)

    def test_provider_registration_allows_email_to_be_omitted(self):
        serializer = ServiceProviderRegistrationSerializer(data={
            'full_name': 'Phone Only Provider',
            'phone': '+919876543212',
            'password': 'Safe-password-123',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        profile = serializer.save()
        self.assertIsNone(profile.user.email)
        self.assertEqual(profile.user.phone, '+919876543212')


class PhoneOnlyLoginTests(APITestCase):
    def test_phone_password_login_succeeds_and_tracks_phone(self):
        user = User(
            username='phone-only-user',
            email=None,
            phone='+919876543213',
            full_name='Phone Only User',
        )
        user.set_password('Safe-password-123')
        user.save()

        response = self.client.post('/api/v1/authenticate/auth/login/', {
            'phone': user.phone,
            'password': 'Safe-password-123',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        attempt = LoginAttempt.objects.get(phone=user.phone)
        self.assertIsNone(attempt.email)
        self.assertTrue(attempt.success)

# Create your tests here.
