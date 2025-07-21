from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Review, ReviewHelpful, ReviewReport, ReviewResponse
from .serializers import (
    ReviewListSerializer, ReviewDetailSerializer, ReviewCreateSerializer,
    ReviewUpdateSerializer, ReviewHelpfulSerializer, ReviewReportSerializer,
    ReviewResponseSerializer, ReviewStatsSerializer
)
from apps.core.permissions import IsOwnerOrReadOnly
from apps.core.pagination import LargeResultsSetPagination


class ReviewListCreateView(generics.ListCreateAPIView):
    """
    List all reviews or create a new review
    """
    queryset = Review.objects.filter(status='approved')
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['service', 'package', 'rating', 'is_verified_purchase']
    search_fields = ['title', 'comment']
    ordering_fields = ['rating', 'reviewed_at', 'helpful_count']
    ordering = ['-reviewed_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewListSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by service or package if provided
        service_id = self.request.query_params.get('service')
        package_id = self.request.query_params.get('package')
        
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        elif package_id:
            queryset = queryset.filter(package_id=package_id)
        
        return queryset.select_related('user', 'service', 'package').prefetch_related('response')


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a review
    """
    queryset = Review.objects.all()
    permission_classes = [IsOwnerOrReadOnly]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ReviewUpdateSerializer
        return ReviewDetailSerializer
    
    def get_queryset(self):
        # Allow users to see their own reviews regardless of status
        if self.request.user.is_authenticated:
            return Review.objects.filter(
                Q(status='approved') | Q(user=self.request.user)
            ).select_related('user', 'service', 'package').prefetch_related('response')
        return Review.objects.filter(status='approved').select_related('user', 'service', 'package').prefetch_related('response')


class MyReviewsView(generics.ListAPIView):
    """
    List current user's reviews
    """
    serializer_class = ReviewListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'rating', 'is_verified_purchase']
    ordering_fields = ['rating', 'reviewed_at']
    ordering = ['-reviewed_at']
    
    def get_queryset(self):
        return Review.objects.filter(user=self.request.user).select_related('service', 'package').prefetch_related('response')


class ReviewHelpfulView(generics.CreateAPIView):
    """
    Mark a review as helpful or not helpful
    """
    serializer_class = ReviewHelpfulSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        # Get the review from URL parameter
        review_id = self.kwargs.get('review_id')
        review = get_object_or_404(Review, id=review_id)
        
        # Add review to the data
        request.data['review'] = review.id
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        helpful = serializer.save()
        
        return Response({
            'message': 'Vote recorded successfully',
            'is_helpful': helpful.is_helpful,
            'helpful_count': review.helpful_count
        }, status=status.HTTP_201_CREATED)


class ReviewReportView(generics.CreateAPIView):
    """
    Report a review
    """
    serializer_class = ReviewReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        # Get the review from URL parameter
        review_id = self.kwargs.get('review_id')
        review = get_object_or_404(Review, id=review_id)
        
        # Add review to the data
        request.data['review'] = review.id
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        
        return Response({
            'message': 'Review reported successfully',
            'report_id': report.id
        }, status=status.HTTP_201_CREATED)


class ReviewResponseView(generics.CreateAPIView):
    """
    Respond to a review (for service providers)
    """
    serializer_class = ReviewResponseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        # Get the review from URL parameter
        review_id = self.kwargs.get('review_id')
        review = get_object_or_404(Review, id=review_id)
        
        # Check if user has permission to respond
        # This should be based on your business logic
        # For now, allowing authenticated users to respond
        if hasattr(review, 'response'):
            return Response({
                'error': 'Review already has a response'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Add review to the data
        request.data['review'] = review.id
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = serializer.save()
        
        return Response({
            'message': 'Response added successfully',
            'response': ReviewResponseSerializer(response).data
        }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def service_review_stats(request, service_id):
    """
    Get review statistics for a service
    """
    from apps.services.models import Service
    
    service = get_object_or_404(Service, id=service_id)
    reviews = Review.objects.filter(service=service, status='approved')
    
    # Calculate statistics
    total_reviews = reviews.count()
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    
    # Rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        rating_distribution[str(i)] = reviews.filter(rating=i).count()
    
    # Recent reviews
    recent_reviews = reviews.order_by('-reviewed_at')[:5]
    
    stats_data = {
        'total_reviews': total_reviews,
        'average_rating': round(average_rating, 2),
        'rating_distribution': rating_distribution,
        'recent_reviews': recent_reviews
    }
    
    serializer = ReviewStatsSerializer(stats_data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def package_review_stats(request, package_id):
    """
    Get review statistics for a package
    """
    from apps.packages.models import Package
    
    package = get_object_or_404(Package, id=package_id)
    reviews = Review.objects.filter(package=package, status='approved')
    
    # Calculate statistics
    total_reviews = reviews.count()
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    
    # Rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        rating_distribution[str(i)] = reviews.filter(rating=i).count()
    
    # Recent reviews
    recent_reviews = reviews.order_by('-reviewed_at')[:5]
    
    stats_data = {
        'total_reviews': total_reviews,
        'average_rating': round(average_rating, 2),
        'rating_distribution': rating_distribution,
        'recent_reviews': recent_reviews
    }
    
    serializer = ReviewStatsSerializer(stats_data)
    return Response(serializer.data)


# Admin views for managing reviews
class AdminReviewListView(generics.ListAPIView):
    """
    Admin view to list all reviews with all statuses
    """
    queryset = Review.objects.all()
    serializer_class = ReviewListSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'rating', 'is_verified_purchase']
    search_fields = ['title', 'comment', 'user__username']
    ordering_fields = ['rating', 'reviewed_at', 'helpful_count', 'reported_count']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return Review.objects.all().select_related('user', 'service', 'package').prefetch_related('response')


@api_view(['PATCH'])
@permission_classes([permissions.IsAdminUser])
def admin_review_status(request, review_id):
    """
    Admin endpoint to update review status
    """
    review = get_object_or_404(Review, id=review_id)
    
    new_status = request.data.get('status')
    if new_status not in ['pending', 'approved', 'rejected']:
        return Response({
            'error': 'Invalid status. Must be pending, approved, or rejected'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    review.status = new_status
    review.save()
    
    return Response({
        'message': f'Review status updated to {new_status}',
        'review': ReviewDetailSerializer(review).data
    })


class AdminReviewReportListView(generics.ListAPIView):
    """
    Admin view to list all review reports
    """
    queryset = ReviewReport.objects.all()
    serializer_class = ReviewReportSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'reason']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return ReviewReport.objects.all().select_related('review', 'reporter', 'resolved_by')


@api_view(['PATCH'])
@permission_classes([permissions.IsAdminUser])
def admin_resolve_report(request, report_id):
    """
    Admin endpoint to resolve review reports
    """
    report = get_object_or_404(ReviewReport, id=report_id)
    
    new_status = request.data.get('status')
    admin_notes = request.data.get('admin_notes', '')
    
    if new_status not in ['reviewed', 'resolved', 'dismissed']:
        return Response({
            'error': 'Invalid status. Must be reviewed, resolved, or dismissed'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    report.status = new_status
    report.admin_notes = admin_notes
    report.resolved_by = request.user
    
    if new_status in ['resolved', 'dismissed']:
        from django.utils import timezone
        report.resolved_at = timezone.now()
    
    report.save()
    
    return Response({
        'message': f'Report {new_status} successfully',
        'report': ReviewReportSerializer(report).data
    })