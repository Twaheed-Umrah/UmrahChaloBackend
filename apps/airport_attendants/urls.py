from django.urls import path

from .views import (
    AdminAirportDetailView,
    AdminAirportListCreateView,
    AdminAttendantKYCView,
    AdminAttendantDetailView,
    AdminAttendantListCreateView,
    AdminBookingListView,
    AdminBookingDetailView,
    AirportListView,
    ProviderBookingCancelView,
    ProviderBookingListCreateView,
    AttendantLoginView,
    AttendantPortalProfileView,
    AttendantDutyListView,
    AttendantDutyDetailView,
    AttendantDutyStatusUpdateView,
)

app_name = 'airport_attendants'

urlpatterns = [
    # Attendant Portal Endpoints
    path('auth/login/', AttendantLoginView.as_view(), name='attendant-login'),
    path('portal/profile/', AttendantPortalProfileView.as_view(), name='attendant-profile'),
    path('portal/duties/', AttendantDutyListView.as_view(), name='attendant-duties'),
    path('portal/duties/<int:pk>/', AttendantDutyDetailView.as_view(), name='attendant-duty-detail'),
    path('portal/duties/<int:pk>/status/', AttendantDutyStatusUpdateView.as_view(), name='attendant-duty-status-update'),

    # Provider / Public Endpoints
    path('airports/', AirportListView.as_view(), name='airport-list'),
    path('bookings/', ProviderBookingListCreateView.as_view(), name='provider-bookings'),
    path('bookings/<int:booking_id>/cancel/', ProviderBookingCancelView.as_view(), name='provider-booking-cancel'),

    # Admin Endpoints
    path('admin/airports/', AdminAirportListCreateView.as_view(), name='admin-airports'),
    path('admin/airports/<int:pk>/', AdminAirportDetailView.as_view(), name='admin-airport-detail'),
    path('admin/attendants/', AdminAttendantListCreateView.as_view(), name='admin-attendants'),
    path('admin/attendants/<int:pk>/', AdminAttendantDetailView.as_view(), name='admin-attendant-detail'),
    path(
        'admin/attendants/<int:attendant_id>/kyc/<str:document_type>/',
        AdminAttendantKYCView.as_view(),
        name='admin-attendant-kyc',
    ),
    path('admin/bookings/', AdminBookingListView.as_view(), name='admin-bookings'),
    path('admin/bookings/<int:pk>/', AdminBookingDetailView.as_view(), name='admin-booking-detail'),
]

