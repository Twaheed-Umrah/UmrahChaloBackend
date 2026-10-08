from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase
from unittest.mock import patch

from .models import LoginAttempt
from .models import ServiceProviderProfile
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
            user_type='provider',
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

    def test_pilgrim_password_login_is_rejected(self):
        user = User.objects.create_user(
            username='pilgrim-no-password-login',
            email=None,
            password='Safe-password-123',
            phone='+919876543221',
            user_type='pilgrim',
        )

        response = self.client.post('/api/v1/authenticate/auth/login/', {
            'phone': user.phone,
            'password': 'Safe-password-123',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('mobile OTP', str(response.data))


class PilgrimMobileAuthTests(APITestCase):
    @patch('apps.authentication.views.cache')
    @patch('apps.authentication.views.SMSService.send_otp', return_value=True)
    @patch('apps.authentication.views.OTPService.store_otp')
    @patch('apps.authentication.views.OTPService.generate_otp', return_value='123456')
    @patch('apps.authentication.views.OTPService.check_rate_limit', return_value=(True, 0))
    def test_mobile_otp_can_be_requested_for_new_pilgrim(
        self, check_rate_limit, generate_otp, store_otp, send_otp, cache_mock
    ):
        response = self.client.post('/api/v1/authenticate/auth/otp/request/', {
            'phone': '+919876543216',
            'purpose': 'pilgrim_auth',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['otp_sent'])
        send_otp.assert_called_once()

    def test_pilgrim_mobile_flow_does_not_accept_agent_phone(self):
        User.objects.create_user(
            username='mobile-agent',
            email=None,
            password='Safe-password-123',
            phone='+919876543219',
            user_type='provider',
        )

        response = self.client.post('/api/v1/authenticate/auth/otp/request/', {
            'phone': '+919876543219',
            'purpose': 'pilgrim_auth',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('agent account', response.data['error'])

    @patch('apps.authentication.views.cache')
    @patch('apps.authentication.views.OTPService.verify_otp', return_value=(True, 'OTP verified'))
    def test_verified_existing_pilgrim_is_logged_in(self, verify_otp, cache_mock):
        user = User.objects.create_user(
            username='existing-pilgrim-mobile',
            email=None,
            password='Safe-password-123',
            phone='+919876543220',
            user_type='pilgrim',
        )
        cache_mock.get.return_value = {
            'identifier': user.phone,
            'purpose': 'pilgrim_auth',
        }

        response = self.client.post('/api/v1/authenticate/auth/otp/verify/', {
            'request_id': 'existing-pilgrim-request',
            'otp': '123456',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['id'], user.id)
        self.assertEqual(response.data['user']['user_type'], 'pilgrim')
        self.assertIn('access_token', response.data)
        self.assertNotIn('is_new_user', response.data)

    @patch('apps.authentication.views.cache')
    @patch('apps.authentication.views.OTPService.verify_otp', return_value=(True, 'OTP verified'))
    def test_verified_new_mobile_requests_pilgrim_profile(
        self, verify_otp, cache_mock
    ):
        cache_mock.get.return_value = {
            'identifier': '+919876543217',
            'purpose': 'pilgrim_auth',
        }
        response = self.client.post('/api/v1/authenticate/auth/otp/verify/', {
            'request_id': 'new-pilgrim-request',
            'otp': '123456',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['verified'])
        self.assertTrue(response.data['is_new_user'])
        self.assertEqual(response.data['request_id'], 'new-pilgrim-request')

    @patch('apps.authentication.views.cache')
    @patch('apps.authentication.views.NotificationService.send_welcome_notification')
    def test_new_pilgrim_profile_is_created_after_verified_otp(self, send_welcome, cache_mock):
        cache_mock.get.return_value = {
            'identifier': '+919876543218',
            'purpose': 'pilgrim_auth',
        }
        response = self.client.post('/api/v1/authenticate/auth/register/', {
            'phone': '+919876543218',
            'full_name': 'New Pilgrim',
            'request_id': 'verified-pilgrim-request',
            'user_type': 'pilgrim',
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['user']['user_type'], 'pilgrim')
        self.assertEqual(response.data['user']['phone'], '+919876543218')
        self.assertTrue(User.objects.filter(phone='+919876543218', user_type='pilgrim').exists())


class ProviderProfileEndpointTests(APITestCase):
    def test_pending_provider_can_retrieve_own_profile(self):
        user = User.objects.create_user(
            username='pending-provider-profile',
            email=None,
            password='Safe-password-123',
            phone='+919876543224',
            user_type='provider',
        )
        ServiceProviderProfile.objects.create(user=user, verification_status='pending')
        self.client.force_authenticate(user=user)

        response = self.client.get('/api/v1/authenticate/providers/service-provider/me/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['verification_status'], 'pending')

    def test_missing_provider_profile_returns_404_instead_of_server_error(self):
        user = User.objects.create_user(
            username='provider-without-profile',
            email=None,
            password='Safe-password-123',
            phone='+919876543222',
            user_type='provider',
        )
        self.client.force_authenticate(user=user)

        response = self.client.get('/api/v1/authenticate/providers/service-provider/me/')

        self.assertEqual(response.status_code, 404)
