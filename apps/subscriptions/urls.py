from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'plans', views.SubscriptionPlanViewSet, basename='subscription-plans')
router.register(r'subscriptions', views.SubscriptionViewSet, basename='subscriptions')
router.register(r'history', views.SubscriptionHistoryViewSet, basename='subscription-history')
router.register(r'features', views.SubscriptionFeatureViewSet, basename='subscription-features')
router.register(r'alerts', views.SubscriptionAlertViewSet, basename='subscription-alerts')
router.register(r'wallets', views.CreditWalletViewSet, basename='credit-wallets')
router.register(r'growth-areas', views.GrowthPlanAreaViewSet, basename='growth-areas')
router.register(r'credit-packs', views.CreditPackViewSet, basename='credit-packs')

app_name = 'subscriptions'

urlpatterns = [
    path('', include(router.urls)),
]