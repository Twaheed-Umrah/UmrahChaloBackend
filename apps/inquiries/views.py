from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from apps.core.permissions import IsAdminOrSuperAdmin


from .models import ContactInquiry, ChatSession
from .serializers import ContactInquirySerializer, ChatSessionSerializer


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# ─── Public endpoints (no auth) ─────────────────────────────────────────────

class ContactInquiryView(APIView):
    """
    POST /api/v1/inquiries/contact/
    Accepts contact form data from the frontend and saves it to the DB.
    No authentication required.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ContactInquirySerializer(data=request.data)
        if serializer.is_valid():
            inquiry = serializer.save(ip_address=get_client_ip(request))
            return Response(
                {
                    'success': True,
                    'message': "Thank you for contacting us! We'll get back to you within 24 hours.",
                    'id': inquiry.id
                },
                status=status.HTTP_201_CREATED
            )
        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class ChatSessionView(APIView):
    """
    POST /api/v1/inquiries/chat-session/
    Saves a chatbot conversation session on close.
    No authentication required.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ChatSessionSerializer(data=request.data)
        if serializer.is_valid():
            session = serializer.save(ip_address=get_client_ip(request))
            return Response(
                {'success': True, 'session_id': str(session.session_id)},
                status=status.HTTP_201_CREATED
            )
        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


# ─── Admin-only endpoints ────────────────────────────────────────────────────

class ContactInquiryListView(APIView):
    """GET /api/v1/inquiries/admin/contacts/  — paginated list for admin panel"""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        qs = ContactInquiry.objects.all().order_by('-created_at')
        search = request.query_params.get('search', '')
        status_filter = request.query_params.get('status', '')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        if status_filter:
            qs = qs.filter(status=status_filter)

        data = ContactInquirySerializer(qs, many=True).data
        return Response({'count': len(data), 'results': data})


class ContactInquiryDeleteView(APIView):
    """DELETE /api/v1/inquiries/admin/contacts/<pk>/"""
    permission_classes = [IsAdminOrSuperAdmin]

    def delete(self, request, pk):
        try:
            obj = ContactInquiry.objects.get(pk=pk)
            obj.delete()
            return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)
        except ContactInquiry.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        """Update status."""
        try:
            obj = ContactInquiry.objects.get(pk=pk)
            new_status = request.data.get('status')
            if new_status:
                obj.status = new_status
                obj.save(update_fields=['status', 'updated_at'])
            return Response(ContactInquirySerializer(obj).data)
        except ContactInquiry.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)


class ChatSessionListView(APIView):
    """GET /api/v1/inquiries/admin/chats/  — list for admin panel"""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        qs = ChatSession.objects.all().order_by('-created_at')
        search = request.query_params.get('search', '')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(visitor_name__icontains=search) |
                Q(visitor_email__icontains=search) |
                Q(visitor_phone__icontains=search)
            )
        data = ChatSessionSerializer(qs, many=True).data
        return Response({'count': len(data), 'results': data})


class ChatSessionDeleteView(APIView):
    """DELETE /api/v1/inquiries/admin/chats/<pk>/"""
    permission_classes = [IsAdminOrSuperAdmin]

    def delete(self, request, pk):
        try:
            obj = ChatSession.objects.get(pk=pk)
            obj.delete()
            return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)
        except ChatSession.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

