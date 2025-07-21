from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeadViewSet, LeadDistributionViewSet, 
    LeadInteractionViewSet, LeadNoteViewSet
)

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'lead-distributions', LeadDistributionViewSet, basename='lead-distribution')
router.register(r'lead-interactions', LeadInteractionViewSet, basename='lead-interaction')
router.register(r'lead-notes', LeadNoteViewSet, basename='lead-note')

urlpatterns = [
    path('', include(router.urls)),
]