from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.authentication.models import ServiceProviderProfile

User = get_user_model()


class ProviderServicesEndpointTests(APITestCase):
    def test_provider_without_subscription_can_list_own_services(self):
        user = User.objects.create_user(
            username='provider-without-subscription',
            email=None,
            password='Safe-password-123',
            phone='+919876543223',
            user_type='provider',
        )
        ServiceProviderProfile.objects.create(user=user)
        self.client.force_authenticate(user=user)

        response = self.client.get('/api/v1/services-pack/services/my_services/?page=1')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'], [])
