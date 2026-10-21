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

from apps.core.permissions import IsAdminOrSuperAdmin, IsServiceProvider, IsAirportAttendant
from apps.payments.models import Payment, PaymentTransaction
from rest_framework import permissions
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Airport, AirportAttendant, AirportAttendantBooking
from .serializers import (
    AirportAttendantBookingCreateSerializer,
    AirportAttendantBookingSerializer,
    AdminAirportAttendantBookingSerializer,
    AirportAttendantSerializer,
    AirportSerializer,
    AttendantPortalProfileSerializer,
    AttendantDutySerializer,
    AttendantDutyStatusUpdateSerializer,
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


# =========================================================================
# ATTENDANT ON-GROUND PORTAL VIEWS
# =========================================================================

def get_attendant_for_request(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None
    attendant = getattr(user, 'airport_attendant_profile', None)
    if not attendant and user.phone:
        attendant = AirportAttendant.objects.filter(phone=user.phone).first()
        if attendant and not attendant.user:
            attendant.user = user
            attendant.save(update_fields=['user'])
    if not attendant and user.email:
        attendant = AirportAttendant.objects.filter(email=user.email).first()
        if attendant and not attendant.user:
            attendant.user = user
            attendant.save(update_fields=['user'])
    return attendant


class AttendantPortalProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        attendant = get_attendant_for_request(request)
        if not attendant:
            return Response(
                {'detail': 'No airport attendant profile associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AttendantPortalProfileSerializer(attendant, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        attendant = get_attendant_for_request(request)
        if not attendant:
            return Response(
                {'detail': 'No airport attendant profile associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AttendantPortalProfileSerializer(
            attendant, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class AttendantDutyListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendantDutySerializer

    def get_queryset(self):
        attendant = get_attendant_for_request(self.request)
        if not attendant:
            return AirportAttendantBooking.objects.none()

        tab = self.request.query_params.get('tab', 'today')
        today = timezone.localdate()
        qs = AirportAttendantBooking.objects.filter(
            attendant=attendant,
            status=AirportAttendantBooking.Status.CONFIRMED,
        ).select_related(
            'airport', 'provider', 'provider__service_provider_profile'
        )

        if tab == 'today':
            qs = qs.filter(service_date=today).order_by('service_time')
        elif tab == 'upcoming':
            qs = qs.filter(service_date__gte=today).exclude(
                duty_status=AirportAttendantBooking.DutyStatus.COMPLETED
            ).order_by('service_date', 'service_time')
        elif tab == 'completed':
            qs = qs.filter(duty_status=AirportAttendantBooking.DutyStatus.COMPLETED).order_by('-service_date', '-service_time')
        elif tab == 'upload':
            qs = qs.filter(
                Q(completion_image__isnull=True) | Q(completion_image='')
            ).order_by('service_date', 'service_time')
        else:  # all
            qs = qs.order_by('-service_date', '-service_time')

        return qs


class AttendantDutyDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendantDutySerializer

    def get_object(self):
        attendant = get_attendant_for_request(self.request)
        if not attendant:
            raise ValidationError({'detail': 'No airport attendant profile found.'})
        return get_object_or_404(
            AirportAttendantBooking.objects.select_related(
                'airport', 'provider', 'provider__service_provider_profile'
            ),
            pk=self.kwargs['pk'],
            attendant=attendant,
        )


class AttendantDutyStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request, pk):
        attendant = get_attendant_for_request(request)
        if not attendant:
            return Response({'detail': 'No airport attendant profile found.'}, status=status.HTTP_404_NOT_FOUND)
        booking = get_object_or_404(AirportAttendantBooking, pk=pk, attendant=attendant)
        serializer = AttendantDutyStatusUpdateSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(
            AttendantDutySerializer(updated, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class AttendantLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        password = request.data.get('password', '').strip()

        if not phone:
            return Response({'error': 'Phone number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if attendant exists
        attendant = AirportAttendant.objects.filter(phone=phone).first()
        if not attendant:
            return Response(
                {'error': 'No airport attendant registered with this phone number.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not attendant.is_active:
            return Response(
                {'error': 'This attendant account is inactive. Please contact Administrator.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Find or create linked user
        user = attendant.user
        if not user:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.filter(phone=phone).first()
            if not user:
                username = f"attendant_{phone}_{attendant.id}"
                user = User.objects.create(
                    username=username,
                    phone=phone,
                    email=attendant.email or f"{username}@umrahchalo.internal",
                    full_name=attendant.name,
                    user_type='airport_attendant',
                    is_active=True,
                )
                if password:
                    user.set_password(password)
                else:
                    user.set_unusable_password()
                user.save()
            attendant.user = user
            attendant.save(update_fields=['user'])

        # Verify password if user has password and password was provided
        if user.has_usable_password() and password:
            if not user.check_password(password):
                return Response({'error': 'Invalid credentials.'}, status=status.HTTP_400_BAD_REQUEST)
        elif password and not user.has_usable_password():
            user.set_password(password)
            user.save(update_fields=['password'])

        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Login successful',
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'full_name': user.full_name or attendant.name,
                'phone': user.phone,
                'email': user.email,
                'user_type': 'airport_attendant',
            },
            'attendant_profile': AttendantPortalProfileSerializer(attendant, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

