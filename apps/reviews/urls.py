from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    # Public review endpoints
    path('', views.ReviewListCreateView.as_view(), name='review-list-create'),
    path('<int:pk>/', views.ReviewDetailView.as_view(), name='review-detail'),
    
    # User-specific review endpoints
    path('my-reviews/', views.MyReviewsView.as_view(), name='my-reviews'),
    
    # Review interaction endpoints
    path('<int:review_id>/helpful/', views.ReviewHelpfulView.as_view(), name='review-helpful'),
    path('<int:review_id>/report/', views.ReviewReportView.as_view(), name='review-report'),
    path('<int:review_id>/response/', views.ReviewResponseView.as_view(), name='review-response'),
    
    # Statistics endpoints
    path('service/<int:service_id>/stats/', views.service_review_stats, name='service-review-stats'),
    path('package/<int:package_id>/stats/', views.package_review_stats, name='package-review-stats'),
    
    # Admin endpoints
    path('admin/reviews/', views.AdminReviewListView.as_view(), name='admin-review-list'),
    path('admin/reviews/<int:review_id>/status/', views.admin_review_status, name='admin-review-status'),
    path('admin/reports/', views.AdminReviewReportListView.as_view(), name='admin-review-report-list'),
    path('admin/reports/<int:report_id>/resolve/', views.admin_resolve_report, name='admin-resolve-report'),
]