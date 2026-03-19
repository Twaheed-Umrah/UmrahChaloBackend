from django.urls import path
from .views import (
    ContactInquiryView, ChatSessionView,
    ContactInquiryListView, ContactInquiryDeleteView,
    ChatSessionListView, ChatSessionDeleteView,
)

urlpatterns = [
    # Public (no auth)
    path('contact/', ContactInquiryView.as_view(), name='contact-inquiry'),
    path('chat-session/', ChatSessionView.as_view(), name='chat-session'),

    # Admin panel endpoints (IsAdminUser)
    path('admin/contacts/', ContactInquiryListView.as_view(), name='admin-contacts-list'),
    path('admin/contacts/<int:pk>/', ContactInquiryDeleteView.as_view(), name='admin-contacts-detail'),
    path('admin/chats/', ChatSessionListView.as_view(), name='admin-chats-list'),
    path('admin/chats/<int:pk>/', ChatSessionDeleteView.as_view(), name='admin-chats-detail'),
]
