from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
from django.shortcuts import get_object_or_404

from .models import (
    SubscriptionPlan, 
    Subscription, 
    SubscriptionHistory, 
    SubscriptionFeature, 
    SubscriptionAlert
)
from .serializers import (
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
    SubscriptionCreateSerializer,
    SubscriptionHistorySerializer,
    SubscriptionFeatureSerializer,
    SubscriptionAlertSerializer,
    SubscriptionRenewalSerializer,
    SubscriptionUpgradeSerializer,
    SubscriptionStatusSerializer,
    UserSubscriptionSummarySerializer
)
from apps.core.permissions import IsServiceProvider, IsAdmin
from apps.core.pagination import LargeResultsSetPagination


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """ViewSet for subscription plans"""
    
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    pagination_class = LargeResultsSetPagination
    
    def get_permissions(self):
        """Get permissions based on action"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [IsAdmin]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter plans based on user type"""
        queryset = self.queryset
        
        # Only show active plans to regular users
        if self.action in ['list', 'retrieve'] and not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        # Filter by plan type
        plan_type = self.request.query_params.get('plan_type')
        if plan_type:
            queryset = queryset.filter(plan_type=plan_type)
        
        # Filter by duration
        duration = self.request.query_params.get('duration')
        if duration:
            queryset = queryset.filter(duration_months=duration)
        
        return queryset.order_by('price')
    
    @action(detail=False, methods=['get'])
    def compare(self, request):
        """Compare different subscription plans"""
        plan_ids = request.query_params.get('plans', '').split(',')
        if not plan_ids:
            return Response(
                {'error': 'Please provide plan IDs to compare'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            plans = SubscriptionPlan.objects.filter(
                id__in=plan_ids,
                is_active=True
            )
            serializer = SubscriptionPlanSerializer(plans, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for subscriptions"""
    
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        """Filter subscriptions based on user role"""
        queryset = self.queryset
        
        if self.request.user.is_staff:
            # Admin can see all subscriptions
            pass
        else:
            # Users can only see their own subscriptions
            queryset = queryset.filter(user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by plan type
        plan_type = self.request.query_params.get('plan_type')
        if plan_type:
            queryset = queryset.filter(plan__plan_type=plan_type)
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        """Get serializer based on action"""
        if self.action == 'create':
            return SubscriptionCreateSerializer
        elif self.action == 'update_status':
            return SubscriptionStatusSerializer
        return SubscriptionSerializer
    
    def perform_create(self, serializer):
        """Create subscription with user context"""
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current active subscription"""
        subscription = Subscription.objects.filter(
            user=request.user,
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        if subscription:
            serializer = SubscriptionSerializer(subscription)
            return Response(serializer.data)
        else:
            return Response(
                {'message': 'No active subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get user subscription summary"""
        serializer = UserSubscriptionSummarySerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        """Renew subscription"""
        subscription = self.get_object()
        
        # Check if user can renew this subscription
        if subscription.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SubscriptionRenewalSerializer(data=request.data)
        if serializer.is_valid():
            plan_id = serializer.validated_data['plan_id']
            auto_renew = serializer.validated_data['auto_renew']
            
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
                
                # Extend subscription
                subscription.extend_subscription(plan.duration_months)
                subscription.auto_renew = auto_renew
                subscription.status = 'active'
                subscription.save()
                
                # Create history record
                SubscriptionHistory.objects.create(
                    subscription=subscription,
                    action='renewed',
                    previous_plan=subscription.plan,
                    new_plan=plan,
                    amount=plan.price,
                    created_by=request.user
                )
                
                return Response(
                    SubscriptionSerializer(subscription).data,
                    status=status.HTTP_200_OK
                )
            except SubscriptionPlan.DoesNotExist:
                return Response(
                    {'error': 'Invalid plan'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def upgrade(self, request, pk=None):
        """Upgrade/downgrade subscription"""
        subscription = self.get_object()
        
        # Check permissions
        if subscription.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SubscriptionUpgradeSerializer(
            data=request.data,
            context={'subscription': subscription}
        )
        
        if serializer.is_valid():
            new_plan_id = serializer.validated_data['new_plan_id']
            
            try:
                new_plan = SubscriptionPlan.objects.get(id=new_plan_id, is_active=True)
                old_plan = subscription.plan
                
                # Update subscription
                subscription.plan = new_plan
                subscription.save()
                
                # Determine action type
                action = 'upgraded' if new_plan.price > old_plan.price else 'downgraded'
                
                # Create history record
                SubscriptionHistory.objects.create(
                    subscription=subscription,
                    action=action,
                    previous_plan=old_plan,
                    new_plan=new_plan,
                    amount=new_plan.price,
                    created_by=request.user
                )
                
                return Response(
                    SubscriptionSerializer(subscription).data,
                    status=status.HTTP_200_OK
                )
            except SubscriptionPlan.DoesNotExist:
                return Response(
                    {'error': 'Invalid plan'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel subscription"""
        subscription = self.get_object()
        
        # Check permissions
        if subscription.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        subscription.cancel_subscription()
        
        # Create history record
        SubscriptionHistory.objects.create(
            subscription=subscription,
            action='cancelled',
            previous_plan=subscription.plan,
            notes=request.data.get('reason', ''),
            created_by=request.user
        )
        
        return Response(
            {'message': 'Subscription cancelled successfully'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['patch'], permission_classes=[IsAdmin])
    def update_status(self, request, pk=None):
        """Update subscription status (admin only)"""
        subscription = self.get_object()
        serializer = SubscriptionStatusSerializer(subscription, data=request.data, partial=True)
        
        if serializer.is_valid():
            old_status = subscription.status
            serializer.save()
            
            # Create history record
            SubscriptionHistory.objects.create(
                subscription=subscription,
                action=f'status_changed_to_{subscription.status}',
                notes=f'Status changed from {old_status} to {subscription.status}',
                created_by=request.user
            )
            
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for subscription history"""
    
    queryset = SubscriptionHistory.objects.all()
    serializer_class = SubscriptionHistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        """Filter history based on user role"""
        queryset = self.queryset
        
        if self.request.user.is_staff:
            # Admin can see all history
            pass
        else:
            # Users can only see their own subscription history
            queryset = queryset.filter(subscription__user=self.request.user)
        
        # Filter by subscription
        subscription_id = self.request.query_params.get('subscription')
        if subscription_id:
            queryset = queryset.filter(subscription_id=subscription_id)
        
        # Filter by action
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        return queryset.order_by('-created_at')


class SubscriptionFeatureViewSet(viewsets.ModelViewSet):
    """ViewSet for subscription features"""
    
    queryset = SubscriptionFeature.objects.all()
    serializer_class = SubscriptionFeatureSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        """Filter features based on user role"""
        queryset = self.queryset
        
        if self.request.user.is_staff:
            # Admin can see all features
            pass
        else:
            # Users can only see their own subscription features
            queryset = queryset.filter(subscription__user=self.request.user)
        
        # Filter by subscription
        subscription_id = self.request.query_params.get('subscription')
        if subscription_id:
            queryset = queryset.filter(subscription_id=subscription_id)
        
        # Filter by feature name
        feature_name = self.request.query_params.get('feature')
        if feature_name:
            queryset = queryset.filter(feature_name=feature_name)
        
        return queryset.order_by('feature_name')
    
    @action(detail=True, methods=['post'])
    def increment(self, request, pk=None):
        """Increment feature usage"""
        feature = self.get_object()
        
        # Check permissions
        if feature.subscription.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if limit is reached
        if feature.is_limit_reached:
            return Response(
                {'error': 'Feature limit reached'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        feature.increment_usage()
        
        # Create alert if approaching limit
        if feature.limit and feature.usage_count >= feature.limit * 0.9:
            SubscriptionAlert.objects.get_or_create(
                subscription=feature.subscription,
                alert_type='feature_limit',
                defaults={
                    'message': f'You are approaching the limit for {feature.feature_name}. '
                              f'Usage: {feature.usage_count}/{feature.limit}'
                }
            )
        
        return Response(
            SubscriptionFeatureSerializer(feature).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get feature usage summary for current subscription"""
        current_subscription = Subscription.objects.filter(
            user=request.user,
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        if not current_subscription:
            return Response(
                {'message': 'No active subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        features = SubscriptionFeature.objects.filter(
            subscription=current_subscription
        )
        
        serializer = SubscriptionFeatureSerializer(features, many=True)
        return Response(serializer.data)


class SubscriptionAlertViewSet(viewsets.ModelViewSet):
    """ViewSet for subscription alerts"""
    
    queryset = SubscriptionAlert.objects.all()
    serializer_class = SubscriptionAlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    
    def get_queryset(self):
        """Filter alerts based on user role"""
        queryset = self.queryset
        
        if self.request.user.is_staff:
            # Admin can see all alerts
            pass
        else:
            # Users can only see their own alerts
            queryset = queryset.filter(subscription__user=self.request.user)
        
        # Filter by alert type
        alert_type = self.request.query_params.get('type')
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)
        
        # Filter by sent status
        is_sent = self.request.query_params.get('sent')
        if is_sent is not None:
            queryset = queryset.filter(is_sent=is_sent.lower() == 'true')
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_sent(self, request, pk=None):
        """Mark alert as sent"""
        alert = self.get_object()
        
        # Check permissions
        if alert.subscription.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        alert.mark_as_sent()
        
        return Response(
            SubscriptionAlertSerializer(alert).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Get unread alerts for user"""
        alerts = SubscriptionAlert.objects.filter(
            subscription__user=request.user,
            is_sent=False
        ).order_by('-created_at')
        
        serializer = SubscriptionAlertSerializer(alerts, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def mark_all_sent(self, request):
        """Mark all user alerts as sent"""
        alerts = SubscriptionAlert.objects.filter(
            subscription__user=request.user,
            is_sent=False
        )
        
        for alert in alerts:
            alert.mark_as_sent()
        
        return Response(
            {'message': f'Marked {alerts.count()} alerts as sent'},
            status=status.HTTP_200_OK
        )