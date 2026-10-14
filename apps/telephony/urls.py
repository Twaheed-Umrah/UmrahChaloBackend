# apps/telephony/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExotelConnectWebhookView,
    ExotelEventWebhookView,
    CallLogViewSet,
    InitiateCallSessionView
)

router = DefaultRouter()
router.register('logs', CallLogViewSet, basename='telephony-call-log')

urlpatterns = [
    # Initiate Click-to-Call session (POST)
    path('call-session/', InitiateCallSessionView.as_view(), name='initiate-call-session'),

    # Exotel Connect Applet (Dynamic URL) webhook (GET)
    path('exotel/connect/', ExotelConnectWebhookView.as_view(), name='exotel-connect'),
    
    # Exotel Event/Passthrough callback webhook (GET/POST)
    path('exotel/event/', ExotelEventWebhookView.as_view(), name='exotel-event'),
    
    # API endpoints for Admin/Dashboard
    path('', include(router.urls)),
]
