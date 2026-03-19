from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import (
    SubscriptionPlan, 
    Subscription, 
    SubscriptionHistory, 
    SubscriptionFeature, 
    SubscriptionAlert,
    CreditWallet,
    CreditTransaction,
    GrowthPlanArea,
    ImpressionLog,
    CreditPack
)
from apps.authentication.serializers import UserProfileSerializer;

class CreditPackSerializer(serializers.ModelSerializer):
    """Serializer for credit top-up packages"""
    class Meta:
        model = CreditPack
        fields = ['id', 'name', 'credits', 'price', 'description', 'icon_type', 'savings_text']
        read_only_fields = ['id']

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plans"""
    
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'plan_type', 'duration_months', 'price',
            'can_upload_packages', 'priority_listing', 'badge_display',
            'lead_notifications', 'analytics_access', 'max_packages',
            'unlimited_business_types', 'cross_business_leads', 
            'unlimited_uploads', 'featured_in_all_categories', 
            'dedicated_support',
            'verified_seal', 'iata_verify_stamp', 'lead_catalogue',
            'online_catalogue', 'guaranteed_leads',
            'is_growth_plan', 'credits_included',
            'description', 'features', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CreditTransactionSerializer(serializers.ModelSerializer):
    """Serializer for credit transactions"""
    transaction_type = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='timestamp', read_only=True)

    class Meta:
        model = CreditTransaction
        fields = ['id', 'action', 'amount', 'reference_id', 'metadata', 'timestamp', 'created_at', 'transaction_type', 'description']
        read_only_fields = ['id', 'timestamp', 'created_at']

    def get_transaction_type(self, obj):
        return "debit" if obj.amount < 0 else "credit"

    def get_description(self, obj):
        # Convert action choice to readable description
        action_map = {
            'impression': 'Search Impression',
            'view_contact': 'Contact Detail View',
            'valid_lead': 'Lead Generation',
            'recharge': 'Wallet Recharge',
            'bonus': 'Special Bonus'
        }
        return action_map.get(obj.action, obj.action.capitalize())


class CreditWalletSerializer(serializers.ModelSerializer):
    """Serializer for credit wallet"""
    transactions = CreditTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = CreditWallet
        fields = ['id', 'balance', 'updated_at', 'transactions']
        read_only_fields = ['id', 'updated_at']


class GrowthPlanAreaSerializer(serializers.ModelSerializer):
    """Serializer for Growth Plan areas (pincodes)"""
    class Meta:
        model = GrowthPlanArea
        fields = ['id', 'pincode', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate_price(self, value):
        """Validate price is not negative"""
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative")
        return value
    
    def validate_max_packages(self, value):
        """Validate max packages is positive"""
        if value <= 0:
            raise serializers.ValidationError("Max packages must be positive")
        return value


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for subscriptions"""
    
    plan_details = SubscriptionPlanSerializer(source='plan', read_only=True)
    user_details = UserProfileSerializer(source='user', read_only=True)
    is_active = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    growth_areas = serializers.SerializerMethodField()
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'user','user_details', 'plan', 'plan_details', 'start_date', 'end_date',
            'status', 'payment_id', 'amount_paid', 'auto_renew',
            'is_active', 'days_remaining', 'is_expired', 'created_at', 'updated_at',
            'growth_areas'
        ]
    
    def get_growth_areas(self, obj):
        profile = getattr(obj.user, 'service_provider_profile', None)
        if profile:
            from .models import GrowthPlanArea
            areas = GrowthPlanArea.objects.filter(provider=profile, is_active=True)
            return [area.pincode for area in areas]
        return []
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validate subscription data"""
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise serializers.ValidationError(
                    "Start date must be before end date"
                )
        
        return data
    
    def create(self, validated_data):
        """Create subscription with proper dates"""
        plan = validated_data['plan']
        if not validated_data.get('start_date'):
            validated_data['start_date'] = timezone.now()
        
        if not validated_data.get('end_date'):
            validated_data['end_date'] = validated_data['start_date'] + timedelta(
                days=30 * plan.duration_months
            )
        
        return super().create(validated_data)


class SubscriptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating subscriptions"""
    pincodes = serializers.ListField(
        child=serializers.CharField(max_length=10),
        required=False,
        write_only=True,
        help_text="List of pincodes for Growth Plan"
    )
    
    class Meta:
        model = Subscription
        fields = ['plan', 'auto_renew', 'pincodes']
    
    def validate(self, data):
        plan = data.get('plan')
        pincodes = data.get('pincodes')
        
        if plan and plan.plan_type == 'growth' and not pincodes:
            raise serializers.ValidationError(
                {"pincodes": "Pincodes are required for Growth Plan"}
            )
        return data

    def create(self, validated_data):
        """Create subscription with user and proper dates"""
        user = self.context['request'].user
        plan = validated_data['plan']
        pincodes = validated_data.pop('pincodes', [])
        
        # Check if user already has active subscription
        existing_subscription = Subscription.objects.filter(
            user=user,
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        if existing_subscription:
            raise serializers.ValidationError(
                "User already has an active subscription"
            )
        
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30 * plan.duration_months),
            amount_paid=plan.price,
            auto_renew=validated_data.get('auto_renew', False),
            status='pending'
        )
        
        # If it's a growth plan, save the requested pincodes
        if plan.plan_type == 'growth' and pincodes:
            from .models import GrowthPlanArea
            provider_profile = getattr(user, 'service_provider_profile', None)
            if provider_profile:
                for code in pincodes:
                    GrowthPlanArea.objects.get_or_create(
                        provider=provider_profile,
                        pincode=code
                    )
        
        # Create history record
        SubscriptionHistory.objects.create(
            subscription=subscription,
            action='created',
            new_plan=plan,
            amount=plan.price,
            created_by=user
        )
        
        return subscription


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    """Serializer for subscription history"""
    
    previous_plan_details = SubscriptionPlanSerializer(source='previous_plan', read_only=True)
    new_plan_details = SubscriptionPlanSerializer(source='new_plan', read_only=True)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True)
    
    class Meta:
        model = SubscriptionHistory
        fields = [
            'id', 'subscription', 'action', 'previous_plan', 'new_plan',
            'previous_plan_details', 'new_plan_details', 'amount', 'notes',
            'created_at', 'created_by', 'created_by_email'
        ]
        read_only_fields = ['id', 'created_at']


class SubscriptionFeatureSerializer(serializers.ModelSerializer):
    """Serializer for subscription features"""
    
    is_limit_reached = serializers.ReadOnlyField()
    remaining_usage = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscriptionFeature
        fields = [
            'id', 'subscription', 'feature_name', 'usage_count', 'limit',
            'is_limit_reached', 'remaining_usage', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_remaining_usage(self, obj):
        """Get remaining usage count"""
        if obj.limit is None:
            return None
        return max(0, obj.limit - obj.usage_count)


class SubscriptionAlertSerializer(serializers.ModelSerializer):
    """Serializer for subscription alerts"""
    
    class Meta:
        model = SubscriptionAlert
        fields = [
            'id', 'subscription', 'alert_type', 'message',
            'is_sent', 'sent_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'sent_at']


class SubscriptionRenewalSerializer(serializers.Serializer):
    """Serializer for subscription renewal"""
    
    plan_id = serializers.IntegerField()
    auto_renew = serializers.BooleanField(default=False)
    
    def validate_plan_id(self, value):
        """Validate plan exists and is active"""
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
            return value
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive plan")


class SubscriptionUpgradeSerializer(serializers.Serializer):
    """Serializer for subscription upgrade/downgrade"""
    
    new_plan_id = serializers.IntegerField()
    
    def validate_new_plan_id(self, value):
        """Validate new plan exists and is active"""
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
            return value
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive plan")
    
    def validate(self, data):
        """Validate upgrade request"""
        subscription = self.context['subscription']
        new_plan_id = data['new_plan_id']
        
        if subscription.plan.id == new_plan_id:
            raise serializers.ValidationError("Cannot upgrade to the same plan")
        
        return data


class SubscriptionStatusSerializer(serializers.ModelSerializer):
    """Serializer for subscription status updates"""
    
    class Meta:
        model = Subscription
        fields = ['status', 'payment_id']
    
    def validate_status(self, value):
        """Validate status transition"""
        if self.instance:
            current_status = self.instance.status
            allowed_transitions = {
                'pending': ['active', 'cancelled'],
                'active': ['expired', 'cancelled'],
                'expired': ['active'],
                'cancelled': []
            }
            
            if value not in allowed_transitions.get(current_status, []):
                raise serializers.ValidationError(
                    f"Cannot change status from {current_status} to {value}"
                )
        
        return value


class UserSubscriptionSummarySerializer(serializers.Serializer):
    """Serializer for user subscription summary"""
    
    current_subscription = SubscriptionSerializer(read_only=True)
    subscription_history = SubscriptionHistorySerializer(many=True, read_only=True)
    feature_usage = SubscriptionFeatureSerializer(many=True, read_only=True)
    alerts = SubscriptionAlertSerializer(many=True, read_only=True)
    
    def to_representation(self, instance):
        """Custom representation for user subscription data"""
        user = instance
        
        # Get current active subscription
        current_subscription = Subscription.objects.filter(
            user=user,
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        # Get subscription history
        history = SubscriptionHistory.objects.filter(
            subscription__user=user
        ).order_by('-created_at')[:10]
        
        # Get feature usage for current subscription
        feature_usage = []
        if current_subscription:
            feature_usage = SubscriptionFeature.objects.filter(
                subscription=current_subscription
            )
        
        # Get recent alerts
        alerts = SubscriptionAlert.objects.filter(
            subscription__user=user
        ).order_by('-created_at')[:5]
        
        return {
            'current_subscription': SubscriptionSerializer(current_subscription).data if current_subscription else None,
            'subscription_history': SubscriptionHistorySerializer(history, many=True).data,
            'feature_usage': SubscriptionFeatureSerializer(feature_usage, many=True).data,
            'alerts': SubscriptionAlertSerializer(alerts, many=True).data,
        }