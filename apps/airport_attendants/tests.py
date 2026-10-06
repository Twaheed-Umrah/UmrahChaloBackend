from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.payments.models import Payment, PaymentMethod
from .models import Airport, AirportAttendant, AirportAttendantBooking

User = get_user_model()


class AirportAttendantBookingTests(APITestCase):
    def setUp(self):
        self.provider = User.objects.create_user(
            username='airport-provider',
            email='provider@example.com',
            password='safe-test-password',
            user_type='provider',
            phone='+919876543210',
        )
        self.airport = Airport.objects.create(
            name='Test International Airport',
            code='TST',
            price='2500.00',
        )
        self.attendant = AirportAttendant.objects.create(
            airport=self.airport,
            name='Airport Attendant',
            phone='+919999999999',
            alternate_phone='+918888888888',
        )
        self.client.force_authenticate(user=self.provider)

    def booking_payload(self, service_time='11:00:00'):
        return {
            'airport': self.airport.id,
            'service_date': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'service_time': service_time,
            'flight_name': 'Test Airways',
            'flight_number': 'TA 100',
            'pilgrim_count': 4,
        }

    def test_provider_airport_list_includes_coming_soon_airports(self):
        coming_soon_airport = Airport.objects.create(
            name='Coming Soon Airport',
            code='CSN',
            price='500.00',
            is_active=False,
        )

        response = self.client.get('/api/v1/airport-attendants/airports/')

        self.assertEqual(response.status_code, 200)
        airports = response.data.get('results', response.data)
        returned_airport = next(
            airport for airport in airports if airport['id'] == coming_soon_airport.id
        )
        self.assertFalse(returned_airport['is_active'])

    def test_pilgrim_cannot_access_airport_attendant_airport_list(self):
        pilgrim = User.objects.create_user(
            username='airport-pilgrim',
            email='pilgrim@example.com',
            password='safe-test-password',
            user_type='pilgrim',
            phone='+919876543211',
        )
        self.client.force_authenticate(user=pilgrim)

        response = self.client.get('/api/v1/airport-attendants/airports/')

        self.assertEqual(response.status_code, 403)

    def test_provider_booking_uses_airport_price_and_hides_attendant_until_paid(self):
        response = self.client.post(
            '/api/v1/airport-attendants/bookings/',
            self.booking_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['amount'], '2500.00')
        self.assertEqual(response.data['attendant_name'], None)
        self.assertEqual(response.data['attendant_phone'], None)

        booking = AirportAttendantBooking.objects.get(pk=response.data['id'])
        payment_method, _ = PaymentMethod.objects.get_or_create(
            type='razorpay',
            defaults={'name': 'Razorpay', 'is_active': True},
        )
        payment = Payment.objects.create(
            user=self.provider,
            payment_method=payment_method,
            amount='2500.00',
            total_amount='2500.00',
            purpose='airport_attendant',
            status='completed',
        )
        booking.payment = payment
        booking.status = AirportAttendantBooking.Status.CONFIRMED
        booking.save(update_fields=['payment', 'status', 'updated_at'])

        response = self.client.get('/api/v1/airport-attendants/bookings/')
        booking_data = response.data['results'][0] if 'results' in response.data else response.data[0]
        self.assertEqual(booking_data['attendant_name'], self.attendant.name)
        self.assertEqual(booking_data['attendant_phone'], self.attendant.phone)
        self.assertEqual(booking_data['attendant_alternate_phone'], self.attendant.alternate_phone)

    def test_same_attendant_cannot_be_booked_twice_for_exact_date_and_time(self):
        first_response = self.client.post(
            '/api/v1/airport-attendants/bookings/',
            self.booking_payload(),
            format='json',
        )
        second_response = self.client.post(
            '/api/v1/airport-attendants/bookings/',
            self.booking_payload(),
            format='json',
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertIn('availability', second_response.data.get('details', {}))

    def test_same_attendant_can_be_booked_at_a_different_time(self):
        first_response = self.client.post(
            '/api/v1/airport-attendants/bookings/',
            self.booking_payload('11:00:00'),
            format='json',
        )
        second_response = self.client.post(
            '/api/v1/airport-attendants/bookings/',
            self.booking_payload('12:00:00'),
            format='json',
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)

    def test_admin_booking_detail_includes_provider_and_payment_details(self):
        booking_response = self.client.post(
            '/api/v1/airport-attendants/bookings/',
            self.booking_payload(),
            format='json',
        )
        booking = AirportAttendantBooking.objects.get(pk=booking_response.data['id'])
        payment_method, _ = PaymentMethod.objects.get_or_create(
            type='razorpay',
            defaults={'name': 'Razorpay', 'is_active': True},
        )
        payment = Payment.objects.create(
            user=self.provider,
            payment_method=payment_method,
            amount='2500.00',
            total_amount='2500.00',
            purpose='airport_attendant',
            status='completed',
            gateway_payment_id='gateway-test-123',
        )
        booking.payment = payment
        booking.status = AirportAttendantBooking.Status.CONFIRMED
        booking.save(update_fields=['payment', 'status', 'updated_at'])

        admin_user = User.objects.create_user(
            username='airport-admin',
            email='admin@example.com',
            password='safe-test-password',
            user_type='super_admin',
        )
        self.client.force_authenticate(user=admin_user)
        response = self.client.get(f'/api/v1/airport-attendants/admin/bookings/{booking.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['provider_details']['email'], self.provider.email)
        self.assertEqual(response.data['attendant_details']['phone'], self.attendant.phone)
        self.assertEqual(response.data['payment_details']['gateway_payment_id'], 'gateway-test-123')

        self.client.force_authenticate(user=self.provider)
        denied_response = self.client.get(f'/api/v1/airport-attendants/admin/bookings/{booking.id}/')
        self.assertEqual(denied_response.status_code, 403)

    def test_attendant_requires_exactly_one_kyc_document(self):
        admin_user = User.objects.create_user(
            username='kyc-admin',
            email='kyc-admin@example.com',
            password='safe-test-password',
            user_type='super_admin',
        )
        self.client.force_authenticate(user=admin_user)
        endpoint = '/api/v1/airport-attendants/admin/attendants/'
        attendant_data = {
            'airport': self.airport.id,
            'name': 'KYC Test Attendant',
            'phone': '+917777777777',
        }

        missing_document = self.client.post(endpoint, attendant_data, format='multipart')
        self.assertEqual(missing_document.status_code, 400)

        both_documents = self.client.post(
            endpoint,
            {
                **attendant_data,
                'pan_document': SimpleUploadedFile('pan.pdf', b'pan', content_type='application/pdf'),
                'aadhaar_document': SimpleUploadedFile('aadhaar.pdf', b'aadhaar', content_type='application/pdf'),
            },
            format='multipart',
        )
        self.assertEqual(both_documents.status_code, 400)

        one_document = self.client.post(
            endpoint,
            {
                **attendant_data,
                'pan_document': SimpleUploadedFile('pan.pdf', b'pan', content_type='application/pdf'),
            },
            format='multipart',
        )
        self.assertEqual(one_document.status_code, 201)
