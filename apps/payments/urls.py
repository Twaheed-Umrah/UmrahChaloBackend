from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PaymentMethodListView,
    PaymentCreateView,
    PaymentListView,
    PaymentDetailView,
    PaymentUpdateView,
    PaymentRefundCreateView,
    PaymentRefundListView,
    PaymentRefundDetailView,
    PaymentTransactionListView,
    PaymentWebhookCreateView,
    AdminPaymentListView,
    AdminPaymentRefundListView,
    AdminPaymentRefundUpdateView,
    verify_payment,
    payment_analytics,
    admin_payment_analytics,
    admin_dashboard,
    webhook_handler,
    cancel_payment,
    payment_receipt
)

app_name = 'payments'

urlpatterns = [
    # Payment Methods
    path('methods/', PaymentMethodListView.as_view(), name='payment-methods'),
    
    # Payments
    path('create/', PaymentCreateView.as_view(), name='payment-create'),
    path('list/', PaymentListView.as_view(), name='payment-list'),
    path('<int:pk>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('<int:pk>/update/', PaymentUpdateView.as_view(), name='payment-update'),
    path('<int:payment_id>/verify/', verify_payment, name='payment-verify'),
    path('<int:payment_id>/cancel/', cancel_payment, name='payment-cancel'),
    path('<int:payment_id>/receipt/', payment_receipt, name='payment-receipt'),
    
    # Refunds
    path('refunds/create/', PaymentRefundCreateView.as_view(), name='refund-create'),
    path('refunds/', PaymentRefundListView.as_view(), name='refund-list'),
    path('refunds/<int:pk>/', PaymentRefundDetailView.as_view(), name='refund-detail'),
    
    # Transactions
    path('transactions/', PaymentTransactionListView.as_view(), name='transaction-list'),
    
    # Webhooks
    path('webhooks/', PaymentWebhookCreateView.as_view(), name='webhook-create'),
    path('webhooks/<str:gateway_type>/', webhook_handler, name='webhook-handler'),
    
    # Analytics
    path('analytics/', payment_analytics, name='payment-analytics'),
    
    # Admin URLs
    path('admin/payments/', AdminPaymentListView.as_view(), name='admin-payment-list'),
    path('admin/refunds/', AdminPaymentRefundListView.as_view(), name='admin-refund-list'),
    path('admin/refunds/<int:pk>/update/', AdminPaymentRefundUpdateView.as_view(), name='admin-refund-update'),
    path('admin/analytics/', admin_payment_analytics, name='admin-payment-analytics'),
    path('admin/dashboard/', admin_dashboard, name='admin-dashboard'),
]