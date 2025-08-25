from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import BaseModel
from apps.authentication.models import ServiceProviderProfile
User = get_user_model()


class Review(BaseModel):
    """
    Model for storing reviews/ratings for services and packages
    """
    RATING_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='reviews'
    )
    service = models.ForeignKey(
        'services.Service', 
        on_delete=models.CASCADE, 
        related_name='reviews',
        null=True, 
        blank=True
    )
    provider = models.ForeignKey(
        ServiceProviderProfile,
        on_delete=models.CASCADE,
        related_name='reviews',
        null=True,
    blank=True
    )
    package = models.ForeignKey(
        'packages.Package', 
        on_delete=models.CASCADE, 
        related_name='reviews',
        null=True, 
        blank=True
    )
    rating = models.IntegerField(
        choices=RATING_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=200)
    comment = models.TextField()
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    is_verified_purchase = models.BooleanField(default=False)
    helpful_count = models.PositiveIntegerField(default=0)
    reported_count = models.PositiveIntegerField(default=0)
    reviewed_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'reviews'
        ordering = ['-reviewed_at']
        unique_together = [
            ['user', 'service'],
            ['user', 'package'],
        ]
        indexes = [
            models.Index(fields=['service', 'status']),
            models.Index(fields=['package', 'status']),
            models.Index(fields=['rating']),
            models.Index(fields=['reviewed_at']),
        ]
    
    def __str__(self):
        if self.service:
            return f"{self.user.username} - {self.service.name} - {self.rating}⭐"
        elif self.package:
            return f"{self.user.username} - {self.package.name} - {self.rating}⭐"
        return f"{self.user.username} - {self.rating}⭐"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.service and not self.package:
            raise ValidationError("Review must be associated with either a service or package")
        if self.service and self.package:
            raise ValidationError("Review cannot be associated with both service and package")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class ReviewHelpful(BaseModel):
    """
    Model for tracking helpful votes on reviews
    """
    review = models.ForeignKey(
        Review, 
        on_delete=models.CASCADE, 
        related_name='helpful_votes'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='helpful_votes'
    )
    is_helpful = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'review_helpful'
        unique_together = ['review', 'user']
        indexes = [
            models.Index(fields=['review', 'is_helpful']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.review.title} - {'Helpful' if self.is_helpful else 'Not Helpful'}"


class ReviewReport(BaseModel):
    """
    Model for reporting inappropriate reviews
    """
    REPORT_REASONS = [
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('fake', 'Fake Review'),
        ('offensive', 'Offensive Language'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    
    review = models.ForeignKey(
        Review, 
        on_delete=models.CASCADE, 
        related_name='reports'
    )
    reporter = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='review_reports'
    )
    reason = models.CharField(max_length=20, choices=REPORT_REASONS)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    admin_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='resolved_reports'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'review_reports'
        unique_together = ['review', 'reporter']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['reason']),
        ]
    
    def __str__(self):
        return f"{self.reporter.username} reported {self.review.title} for {self.reason}"


class ReviewResponse(BaseModel):
    """
    Model for service provider responses to reviews
    """
    review = models.OneToOneField(
        Review, 
        on_delete=models.CASCADE, 
        related_name='response'
    )
    responder = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='review_responses'
    )
    response_text = models.TextField()
    is_official = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'review_responses'
        indexes = [
            models.Index(fields=['review']),
        ]
    
    def __str__(self):
        return f"Response to {self.review.title} by {self.responder.username}"