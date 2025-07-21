from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Review, ReviewHelpful, ReviewReport, ReviewResponse

User = get_user_model()


class ReviewUserSerializer(serializers.ModelSerializer):
    """
    Serializer for user info in reviews
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'profile_image']


class ReviewResponseSerializer(serializers.ModelSerializer):
    """
    Serializer for review responses
    """
    responder = ReviewUserSerializer(read_only=True)
    
    class Meta:
        model = ReviewResponse
        fields = [
            'id', 'response_text', 'is_official', 'responder',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['responder', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        validated_data['responder'] = self.context['request'].user
        return super().create(validated_data)


class ReviewListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing reviews
    """
    user = ReviewUserSerializer(read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    response = ReviewResponseSerializer(read_only=True)
    user_has_voted = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = [
            'id', 'user', 'service', 'package', 'service_name', 'package_name',
            'rating', 'title', 'comment', 'status', 'is_verified_purchase',
            'helpful_count', 'reported_count', 'reviewed_at', 'response',
            'user_has_voted', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'user', 'helpful_count', 'reported_count', 'user_has_voted',
            'created_at', 'updated_at'
        ]
    
    def get_user_has_voted(self, obj):
        """Check if current user has voted on this review"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ReviewHelpful.objects.filter(
                review=obj, 
                user=request.user
            ).exists()
        return False


class ReviewDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed review view
    """
    user = ReviewUserSerializer(read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    response = ReviewResponseSerializer(read_only=True)
    helpful_votes = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = [
            'id', 'user', 'service', 'package', 'service_name', 'package_name',
            'rating', 'title', 'comment', 'status', 'is_verified_purchase',
            'helpful_count', 'reported_count', 'reviewed_at', 'response',
            'helpful_votes', 'user_vote', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'user', 'helpful_count', 'reported_count', 'helpful_votes',
            'user_vote', 'created_at', 'updated_at'
        ]
    
    def get_helpful_votes(self, obj):
        """Get helpful votes breakdown"""
        helpful_votes = ReviewHelpful.objects.filter(review=obj)
        return {
            'helpful': helpful_votes.filter(is_helpful=True).count(),
            'not_helpful': helpful_votes.filter(is_helpful=False).count(),
            'total': helpful_votes.count()
        }
    
    def get_user_vote(self, obj):
        """Get current user's vote on this review"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                vote = ReviewHelpful.objects.get(review=obj, user=request.user)
                return vote.is_helpful
            except ReviewHelpful.DoesNotExist:
                return None
        return None


class ReviewCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating reviews
    """
    class Meta:
        model = Review
        fields = [
            'service', 'package', 'rating', 'title', 'comment'
        ]
    
    def validate(self, data):
        """Validate that either service or package is provided, but not both"""
        service = data.get('service')
        package = data.get('package')
        
        if not service and not package:
            raise serializers.ValidationError(
                "Either service or package must be provided"
            )
        
        if service and package:
            raise serializers.ValidationError(
                "Cannot review both service and package simultaneously"
            )
        
        return data
    
    def validate_service(self, value):
        """Validate service exists and user hasn't already reviewed it"""
        if value:
            user = self.context['request'].user
            if Review.objects.filter(user=user, service=value).exists():
                raise serializers.ValidationError(
                    "You have already reviewed this service"
                )
        return value
    
    def validate_package(self, value):
        """Validate package exists and user hasn't already reviewed it"""
        if value:
            user = self.context['request'].user
            if Review.objects.filter(user=user, package=value).exists():
                raise serializers.ValidationError(
                    "You have already reviewed this package"
                )
        return value
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ReviewUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating reviews
    """
    class Meta:
        model = Review
        fields = ['rating', 'title', 'comment']
    
    def validate(self, data):
        """Only allow updates if review is pending or user is the owner"""
        review = self.instance
        user = self.context['request'].user
        
        if review.user != user:
            raise serializers.ValidationError(
                "You can only update your own reviews"
            )
        
        if review.status == 'approved':
            raise serializers.ValidationError(
                "Cannot update approved reviews"
            )
        
        return data


class ReviewHelpfulSerializer(serializers.ModelSerializer):
    """
    Serializer for marking reviews as helpful
    """
    class Meta:
        model = ReviewHelpful
        fields = ['review', 'is_helpful']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        
        # Use get_or_create to handle duplicate votes
        helpful, created = ReviewHelpful.objects.get_or_create(
            review=validated_data['review'],
            user=validated_data['user'],
            defaults={'is_helpful': validated_data['is_helpful']}
        )
        
        # If not created, update the vote
        if not created:
            helpful.is_helpful = validated_data['is_helpful']
            helpful.save()
        
        # Update helpful count on review
        review = validated_data['review']
        review.helpful_count = review.helpful_votes.filter(is_helpful=True).count()
        review.save()
        
        return helpful


class ReviewReportSerializer(serializers.ModelSerializer):
    """
    Serializer for reporting reviews
    """
    reporter = ReviewUserSerializer(read_only=True)
    
    class Meta:
        model = ReviewReport
        fields = [
            'id', 'review', 'reporter', 'reason', 'description',
            'status', 'admin_notes', 'resolved_by', 'resolved_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'reporter', 'status', 'admin_notes', 'resolved_by',
            'resolved_at', 'created_at', 'updated_at'
        ]
    
    def validate_review(self, value):
        """Validate user hasn't already reported this review"""
        user = self.context['request'].user
        if ReviewReport.objects.filter(review=value, reporter=user).exists():
            raise serializers.ValidationError(
                "You have already reported this review"
            )
        return value
    
    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        
        # Increment reported count on review
        review = validated_data['review']
        review.reported_count += 1
        review.save()
        
        return super().create(validated_data)


class ReviewStatsSerializer(serializers.Serializer):
    """
    Serializer for review statistics
    """
    total_reviews = serializers.IntegerField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    rating_distribution = serializers.DictField()
    recent_reviews = ReviewListSerializer(many=True)
    
    class Meta:
        fields = [
            'total_reviews', 'average_rating', 'rating_distribution',
            'recent_reviews'
        ]