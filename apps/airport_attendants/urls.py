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
)

app_name = 'airport_attendants'

urlpatterns = [
    path('airports/', AirportListView.as_view(), name='airport-list'),
    path('bookings/', ProviderBookingListCreateView.as_view(), name='provider-bookings'),
    path('bookings/<int:booking_id>/cancel/', ProviderBookingCancelView.as_view(), name='provider-booking-cancel'),
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
