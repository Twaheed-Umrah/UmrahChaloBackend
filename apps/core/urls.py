from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MasterPincodeViewSet

router = DefaultRouter()
router.register(r'pincodes', MasterPincodeViewSet, basename='masterpincode')

urlpatterns = [
    path('', include(router.urls)),
]
