from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'services'

# ------------------- Router -------------------
router = DefaultRouter()
router.register(r'categories', views.ServiceCategoryViewSet, basename='servicecategory')
router.register(r'images', views.ServiceImageViewSet, basename='serviceimage')
router.register(r'services', views.ServiceViewSet, basename='service')
router.register(r'availability', views.ServiceAvailabilityViewSet, basename='serviceavailability')
router.register(r'faqs', views.ServiceFAQViewSet, basename='servicefaq')
router.register(r'views', views.ServiceViewViewSet, basename='serviceview')

# ------------------- Custom URLs -------------------
urlpatterns = [
    path('', include(router.urls)),

    # ================ UTILITY ENDPOINTS ================
    
    # Service type and status choices
    path('service-types/', views.service_type_choices, name='service-type-choices'),
    path('service-status/', views.service_status_choices, name='service-status-choices'),
    path("public/service/", views.PublicServiceDetailView.as_view(), name="public-service-detail"),

    # Public statistics
    path('public-stats/', views.service_stats_public, name='public-stats'),
    
    # Bulk operations (Admin only)
    path('bulk-action/', views.bulk_service_action, name='bulk-service-action'),

    # ================ CATEGORY ENDPOINTS ================
    
    # Category-specific services
    path(
        'categories/<int:pk>/services/',
        views.ServiceCategoryViewSet.as_view({'get': 'services'}),
        name='category-services'
    ),
    
    # Popular categories
    path(
        'categories/popular/',
        views.ServiceCategoryViewSet.as_view({'get': 'popular'}),
        name='popular-categories'
    ),

    # ================ IMAGE ENDPOINTS ================
    
    # Images grouped by category
    path(
        'images/by-category/',
        views.ServiceImageViewSet.as_view({'get': 'by_category'}),
        name='images-by-category'
    ),

    # ================ SERVICE ENDPOINTS ================
    
    # Service management endpoints
    path(
        'services/my-services/',
        views.ServiceViewSet.as_view({'get': 'my_services'}),
        name='my-services'
    ),
    path(
        'services/admin-services/',
        views.ServiceViewSet.as_view({'get': 'admin_services'}),
        name='admin-services'
    ),
    path(
        'services/get-service-by-id/',
        views.ServiceViewSet.as_view({'get': 'get_by_id'}),
        name='get-service-by-id'
    ),
    
    # Service discovery endpoints
    path(
        'services/featured/',
        views.ServiceViewSet.as_view({'get': 'featured'}),
        name='featured-services'
    ),
    path(
        'services/popular/',
        views.ServiceViewSet.as_view({'get': 'popular'}),
        name='popular-services'
    ),
    path(
        'services/search/',
        views.ServiceViewSet.as_view({'get': 'search'}),
        name='search-services'
    ),
    path(
        'services/by-service-type/',
        views.ServiceViewSet.as_view({'get': 'by_service_type'}),
        name='services-by-type'
    ),
    
    # Service statistics (Admin only)
    path(
        'services/stats/',
        views.ServiceViewSet.as_view({'get': 'stats'}),
        name='service-stats'
    ),
    
    # Service status management (Admin only)
    path(
        'services/<int:pk>/update-status/',
        views.ServiceViewSet.as_view({'post': 'update_status'}),
        name='service-update-status'
    ),
    
    # Service favorites management (Pilgrim)
    path(
        'services/<int:pk>/add-to-favorites/',
        views.ServiceViewSet.as_view({'post': 'add_to_favorites'}),
        name='service-add-to-favorites'
    ),
    path(
        'services/<int:pk>/remove-from-favorites/',
        views.ServiceViewSet.as_view({'post': 'remove_from_favorites'}),
        name='service-remove-from-favorites'
    ),
    
    # Service lead tracking
    path(
        'services/<int:pk>/increment-lead/',
        views.ServiceViewSet.as_view({'post': 'increment_lead'}),
        name='service-increment-lead'
    ),

    # ================ AVAILABILITY ENDPOINTS ================
    
    # Availability by service
    path(
        'availability/by-service/',
        views.ServiceAvailabilityViewSet.as_view({'get': 'by_service'}),
        name='availability-by-service'
    ),
    
    # Bulk availability creation
    path(
        'availability/bulk-create/',
        views.ServiceAvailabilityViewSet.as_view({'post': 'bulk_create'}),
        name='availability-bulk-create'
    ),

    # ================ FAQ ENDPOINTS ================
    
    # FAQs by service
    path(
        'faqs/by-service/',
        views.ServiceFAQViewSet.as_view({'get': 'by_service'}),
        name='faqs-by-service'
    ),
    
    # Bulk FAQ creation
    path(
        'faqs/bulk-create/',
        views.ServiceFAQViewSet.as_view({'post': 'bulk_create'}),
        name='faqs-bulk-create'
    ),

    # ================ ANALYTICS ENDPOINTS ================
    
    # Service view analytics
    path(
        'views/analytics/',
        views.ServiceViewViewSet.as_view({'get': 'analytics'}),
        name='service-view-analytics'
    ),
    
    # Export analytics data
    path(
        'views/export-csv/',
        views.ServiceViewViewSet.as_view({'get': 'export_csv'}),
        name='service-view-export-csv'
    ),
]

# ================ COMPREHENSIVE API DOCUMENTATION ================
"""
SERVICE MANAGEMENT API ENDPOINTS

🏷️  CATEGORIES:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /categories/                    - List all categories      │
│ GET    /categories/{id}/               - Get category details     │
│ GET    /categories/{id}/services/      - Services in category     │
│ GET    /categories/popular/            - Popular categories       │
└──────────────────────────────────────────────────────────────────┘

🖼️  IMAGES:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /images/                        - List all images         │
│ POST   /images/                        - Upload image (Admin)    │
│ GET    /images/{id}/                   - Get image details       │
│ PUT    /images/{id}/                   - Update image (Admin)    │
│ DELETE /images/{id}/                   - Delete image (Admin)    │
│ GET    /images/by-category/            - Images grouped by cat   │
└──────────────────────────────────────────────────────────────────┘

🎯  SERVICES - CRUD Operations:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /services/                      - List services (filtered)│
│ POST   /services/                      - Create service (Provider)│
│ GET    /services/{id}/                 - Get service details     │
│ PUT    /services/{id}/                 - Update service (Owner)  │
│ PATCH  /services/{id}/                 - Partial update (Owner)  │
│ DELETE /services/{id}/                 - Delete service (Owner)  │
│ GET    /services/get-service-by-id/    - Get by ID param        │
└──────────────────────────────────────────────────────────────────┘

🔍  SERVICES - Discovery & Search:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /services/featured/             - Featured services       │
│ GET    /services/popular/              - Popular services        │
│ GET    /services/search/               - Advanced search         │
│ GET    /services/by-service-type/      - Filter by service type  │
└──────────────────────────────────────────────────────────────────┘

👥  SERVICES - User Management:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /services/my-services/          - Provider's services     │
│ GET    /services/admin-services/       - Admin service mgmt      │
│ POST   /services/{id}/update-status/   - Update status (Admin)   │
│ POST   /services/{id}/add-to-favorites/    - Add to favorites    │
│ POST   /services/{id}/remove-from-favorites/ - Remove favorites  │
│ POST   /services/{id}/increment-lead/  - Track lead             │
└──────────────────────────────────────────────────────────────────┘

📅  AVAILABILITY:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /availability/                  - List availability       │
│ POST   /availability/                  - Create availability     │
│ GET    /availability/{id}/             - Get availability        │
│ PUT    /availability/{id}/             - Update availability     │
│ DELETE /availability/{id}/             - Delete availability     │
│ GET    /availability/by-service/       - Get by service ID       │
│ POST   /availability/bulk-create/      - Bulk create slots      │
└──────────────────────────────────────────────────────────────────┘

❓  FAQs:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /faqs/                          - List FAQs              │
│ POST   /faqs/                          - Create FAQ             │
│ GET    /faqs/{id}/                     - Get FAQ details        │
│ PUT    /faqs/{id}/                     - Update FAQ             │
│ DELETE /faqs/{id}/                     - Delete FAQ             │
│ GET    /faqs/by-service/               - FAQs for service       │
│ POST   /faqs/bulk-create/              - Bulk create FAQs      │
└──────────────────────────────────────────────────────────────────┘

📊  ANALYTICS & TRACKING:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /services/stats/                - Service statistics     │
│ GET    /views/                         - List service views     │
│ GET    /views/{id}/                    - Get view details       │
│ GET    /views/analytics/               - View analytics         │
│ GET    /views/export-csv/              - Export analytics CSV   │
│ GET    /public-stats/                  - Public statistics      │
└──────────────────────────────────────────────────────────────────┘

🛠️  UTILITY & ADMIN:
┌──────────────────────────────────────────────────────────────────┐
│ GET    /service-types/                 - Service type choices    │
│ GET    /service-status/                - Service status choices  │
│ POST   /bulk-action/                   - Bulk admin actions     │
└──────────────────────────────────────────────────────────────────┘

🔐  PERMISSION LEVELS:
┌──────────────────────────────────────────────────────────────────┐
│ 🌍 AllowAny          - Categories, Public stats, Service listing │
│ 🔑 IsAuthenticated   - Basic authenticated access                │
│ 👤 IsProvider        - Provider-specific operations              │
│ 🛡️ IsAdmin           - Admin management operations               │
│ 🔒 IsOwner           - Owner-specific operations                  │
└──────────────────────────────────────────────────────────────────┘

📋  FILTERING & SEARCH PARAMETERS:

General Filters:
  ?q=search_term              - Text search
  ?service_type=visa          - Filter by service type  
  ?category=1                 - Filter by category ID
  ?city=Delhi                 - Filter by city
  ?min_price=100              - Minimum price filter
  ?max_price=5000             - Maximum price filter
  ?is_featured=true           - Featured services only
  ?is_popular=true            - Popular services only
  ?ordering=-created_at       - Sort results

Air Ticket Specific:
  ?flight_from=Delhi          - Origin city/airport
  ?flight_to=Mecca           - Destination city/airport
  ?departure_date=2024-01-15  - Departure date
  ?return_date=2024-01-25     - Return date
  ?flight_class=economy       - Flight class
  ?airline=Emirates           - Airline name

Zamzam Water Specific:
  ?min_water_capacity=0.5     - Min capacity in liters
  ?max_water_capacity=5.0     - Max capacity in liters
  ?packaging_type=bottle      - Packaging type

Hotel Specific:
  ?min_star_rating=3          - Minimum star rating
  ?max_star_rating=5          - Maximum star rating
  ?hotel_room_type=double     - Room type

Transport Specific:
  ?transport_type=bus         - Transport type
  ?min_vehicle_capacity=10    - Min passenger capacity
  ?max_vehicle_capacity=50    - Max passenger capacity
  ?pickup_location=Delhi      - Pickup location
  ?drop_location=Mecca        - Drop location

Date & Availability:
  ?date_from=2024-01-01       - Available from date
  ?date_to=2024-12-31         - Available to date  
  ?has_availability=true      - Has available slots

Analytics Filters:
  ?days=30                    - Analytics time range
  ?date_from=2024-01-01       - Start date for export
  ?date_to=2024-12-31         - End date for export
"""