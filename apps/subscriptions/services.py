from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
from .models import CreditWallet, CreditTransaction, ImpressionLog, Subscription

class CreditService:
    @staticmethod
    def deduct_impression_credits(provider, request):
        """
        Deduct 2 credits for an impression, with safety checks.
        Supports request=None for async task execution.
        """
        # Extract request context safely
        user = None
        session_id = None
        ip_address = '0.0.0.0'
        
        if request is not None:
            try:
                user = request.user if request.user.is_authenticated else None
            except AttributeError:
                user = None
            try:
                session_id = request.session.session_key or request.data.get('session_id')
            except AttributeError:
                session_id = None
            try:
                from apps.core.utils import get_client_ip
                ip_address = get_client_ip(request)
            except Exception:
                ip_address = '0.0.0.0'

        # 1. Check if provider has active Growth Plan
        has_growth = Subscription.objects.filter(
            user=provider.user,
            plan__plan_type='growth',
            status='active',
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).exists()

        if not has_growth:
            return False, "Provider does not have an active Growth Plan."

        # 2. Safety Layer Validation
        now = timezone.now()
        thirty_mins_ago = now - timedelta(minutes=30)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # A. Unique provider per 30 minutes for this user/session
        recent_impression = ImpressionLog.objects.filter(
            provider=provider,
            timestamp__gte=thirty_mins_ago
        )
        if user:
            recent_impression = recent_impression.filter(user_id=user.id)
        else:
            recent_impression = recent_impression.filter(session_id=session_id)
        
        if recent_impression.exists():
            return False, "Impression already logged within 30 minutes."

        # B. Max 3 impressions per user per provider per day
        daily_count = ImpressionLog.objects.filter(
            provider=provider,
            timestamp__gte=today_start
        )
        if user:
            daily_count = daily_count.filter(user_id=user.id).count()
        else:
            daily_count = daily_count.filter(session_id=session_id).count()

        if daily_count >= 3:
            return False, "Daily impression limit reached for this user."

        # C. IP Protection (Optional: Max X impressions per IP per day total)
        ip_daily_count = ImpressionLog.objects.filter(ip_address=ip_address, timestamp__gte=today_start).count()
        if ip_daily_count > 100: # Threshold for bot protection
            return False, "IP address exceeded daily limit."

        # 3. Deduct Credits
        wallet, created = CreditWallet.objects.get_or_create(user=provider.user)
        if wallet.balance < 1:
            return False, "Insufficient credits."
        
        wallet.balance -= 1
        wallet.save()

        # 4. Log Transaction and Impression
        CreditTransaction.objects.create(
            wallet=wallet,
            action='impression',
            amount=-1,
            metadata={
                'ip': ip_address,
                'user_id': str(user.id) if user else None,
                'session_id': session_id
            }
        )

        ImpressionLog.objects.create(
            provider=provider,
            user_id=str(user.id) if user else None,
            session_id=session_id,
            ip_address=ip_address
        )

        return True, "Credits deducted successfully."

    @staticmethod
    def deduct_lead_credits(provider, lead=None, user=None):
        """
        Consolidated method for deducting credits for leads and contact views.
        Deducts 4 credits.
        """
        # 1. Implementation Safety Checks
        has_growth = Subscription.objects.filter(
            user=provider.user,
            plan__plan_type='growth',
            status='active',
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).exists()

        if not has_growth:
            return False, "Provider does not have an active Growth Plan."

        # 2. Deduct Credits
        wallet, created = CreditWallet.objects.get_or_create(user=provider.user)
        if wallet.balance < 4:
            return False, "Insufficient credits."
        
        wallet.balance -= 4
        wallet.save()

        # 3. Create Transaction record
        description = f"Lead deduction for lead #{lead.id if lead else 'Contact View'}"
        CreditTransaction.objects.create(
            wallet=wallet,
            amount=-4, # Changed to negative as it's a deduction
            action='lead_or_view', # Consolidated action type
            metadata={
                'lead_id': str(lead.id) if lead else None,
                'user_id': str(user.id) if user else None,
                'event': 'lead_distribution' if lead else 'contact_view'
            }
        )
        
        return True, "Credits deducted successfully."

    @staticmethod
    def add_credits(user, amount, action='recharge', metadata=None):
        """
        Add credits to a user's wallet.
        """
        wallet, created = CreditWallet.objects.get_or_create(user=user)
        wallet.balance += amount
        wallet.save()

        CreditTransaction.objects.create(
            wallet=wallet,
            action=action,
            amount=amount,
            metadata=metadata or {}
        )
        return True, f"{amount} credits added successfully."
