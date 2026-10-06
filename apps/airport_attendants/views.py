import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrSuperAdmin, IsServiceProvider
from apps.payments.models import Payment, PaymentTransaction
from .models import Airport, AirportAttendant, AirportAttendantBooking
from .serializers import (
    AirportAttendantBookingCreateSerializer,
    AirportAttendantBookingSerializer,
    AdminAirportAttendantBookingSerializer,
    AirportAttendantSerializer,
    AirportSerializer,
)

logger = logging.getLogger(__name__)
RESERVATION_WINDOW = timedelta(minutes=15)


class AirportListView(generics.ListAPIView):
    serializer_class = AirportSerializer
    permission_classes = [IsServiceProvider]

    def get_queryset(self):
        queryset = Airport.objects.annotate(
            attendant_count=Count('attendants', filter=Q(attendants__is_active=True))
        ).order_by('name')
        return queryset


class AdminAirportListCreateView(generics.ListCreateAPIView):
    serializer_class = AirportSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    queryset = Airport.objects.annotate(
        attendant_count=Count('attendants', filter=Q(attendants__is_active=True))
    )


class AdminAirportDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AirportSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    queryset = Airport.objects.all()


class AdminAttendantListCreateView(generics.ListCreateAPIView):
    serializer_class = AirportAttendantSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = AirportAttendant.objects.select_related('airport')


class AdminAttendantDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AirportAttendantSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = AirportAttendant.objects.select_related('airport')


class AdminAttendantKYCView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, attendant_id, document_type):
        field_names = {'pan': 'pan_document', 'aadhaar': 'aadhaar_document'}
        field_name = field_names.get(document_type)
        if not field_name:
            return Response({'detail': 'Unknown KYC document type.'}, status=status.HTTP_404_NOT_FOUND)
        attendant = get_object_or_404(AirportAttendant, pk=attendant_id)
        document = getattr(attendant, field_name)
        if not document:
            return Response({'detail': 'KYC document has not been uploaded.'}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(document.open('rb'), as_attachment=True, filename=document.name.rsplit('/', 1)[-1])
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class ProviderBookingListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsServiceProvider]
    serializer_class = AirportAttendantBookingSerializer

    def get_queryset(self):
        return AirportAttendantBooking.objects.filter(
            provider=self.request.user
        ).select_related('airport', 'attendant', 'payment').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = AirportAttendantBookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        with transaction.atomic():
            attendants = AirportAttendant.objects.select_for_update().filter(
                airport=validated['airport'],
                is_active=True,
            ).order_by('id')
            selected_attendant = None
            now = timezone.now()
            for attendant in attendants:
                already_assigned = AirportAttendantBooking.objects.filter(
                    attendant=attendant,
                    service_date=validated['service_date'],
                    service_time=validated['service_time'],
                ).filter(
                    Q(status=AirportAttendantBooking.Status.CONFIRMED)
                    | Q(
                        status=AirportAttendantBooking.Status.AWAITING_PAYMENT,
                        created_at__gte=now - RESERVATION_WINDOW,
                    )
                ).exists()
                if not already_assigned:
                    selected_attendant = attendant
                    break

            if not selected_attendant:
                raise ValidationError({
                    'availability': 'No attendant is available at this airport for the selected date and time.'
                })

            booking = AirportAttendantBooking.objects.create(
                provider=request.user,
                attendant=selected_attendant,
                amount=validated['airport'].price,
                **validated,
            )

        return Response(
            AirportAttendantBookingSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


class ProviderBookingCancelView(APIView):
    permission_classes = [IsServiceProvider]

    def post(self, request, booking_id):
        with transaction.atomic():
            booking = get_object_or_404(
                AirportAttendantBooking.objects.select_for_update().select_related('airport'),
                pk=booking_id,
                provider=request.user,
            )
            if booking.status not in (
                AirportAttendantBooking.Status.AWAITING_PAYMENT,
                AirportAttendantBooking.Status.CONFIRMED,
            ):
                raise ValidationError({'status': 'This booking cannot be cancelled.'})

            if booking.payment_id:
                payment = Payment.objects.select_for_update().get(pk=booking.payment_id)
                if payment.status in ('pending', 'processing'):
                    payment.status = 'failed'
                    payment.failed_at = timezone.now()
                    payment.save(update_fields=['status', 'failed_at', 'updated_at'])
                    PaymentTransaction.objects.create(
                        payment=payment,
                        transaction_type='payment',
                        amount=payment.total_amount,
                        currency=payment.currency,
                        status='failed',
                        description='Airport attendant booking cancelled by provider before payment completed.',
                    )

            booking.status = AirportAttendantBooking.Status.CANCELLED
            booking.save(update_fields=['status', 'updated_at'])

        return Response(
            AirportAttendantBookingSerializer(booking).data,
            status=status.HTTP_200_OK,
        )


class AdminBookingListView(generics.ListAPIView):
    permission_classes = [IsAdminOrSuperAdmin]
    serializer_class = AirportAttendantBookingSerializer
    queryset = AirportAttendantBooking.objects.select_related(
        'airport', 'attendant', 'provider', 'payment',
    ).order_by('-created_at')


class AdminBookingDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminOrSuperAdmin]
    serializer_class = AdminAirportAttendantBookingSerializer
    queryset = AirportAttendantBooking.objects.select_related(
        'airport', 'attendant', 'provider', 'provider__service_provider_profile',
        'payment', 'payment__payment_method',
    )
