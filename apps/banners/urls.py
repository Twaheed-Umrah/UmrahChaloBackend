from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BannerViewSet, 
    PopularDestinationViewSet,
    HomeView
)

router = DefaultRouter()
router.register(r'banners', BannerViewSet, basename='banner')
router.register(r'destinations', PopularDestinationViewSet, basename='destination')

urlpatterns = [
    path('', include(router.urls)),
    path('home/', HomeView.as_view(), name='home'),
    
    # Banner endpoints
    path('main-screen/', BannerViewSet.as_view({'get': 'main_screen'}), name='main-screen-banners'),
    path('offers/', BannerViewSet.as_view({'get': 'offers'}), name='offer-banners'),
    path('for-provider/', BannerViewSet.as_view({'get': 'for_provider'}), name='provider-banners'),
    path('by-location/', BannerViewSet.as_view({'get': 'by_location'}), name='location-banners'),
    
    # Destination endpoints
    path('destinations/hajj/', PopularDestinationViewSet.as_view({'get': 'hajj_destinations'}), name='hajj-destinations'),
    path('destinations/umrah/', PopularDestinationViewSet.as_view({'get': 'umrah_destinations'}), name='umrah-destinations'),
    path('destinations/ziyarat/', PopularDestinationViewSet.as_view({'get': 'ziyarat_destinations'}), name='ziyarat-destinations'),
    path('destinations/featured/', PopularDestinationViewSet.as_view({'get': 'featured'}), name='featured-destinations'),
    path('destinations/search-by-type/', PopularDestinationViewSet.as_view({'get': 'search_by_type'}), name='search-destinations-by-type'),
]