from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from apps.authentication.models import ServiceProviderProfile
from apps.subscriptions.models import Subscription
from apps.notifications.tasks import send_lead_notification
from .models import Lead, LeadDistribution


@shared_task
def distribute_lead_to_providers(lead_id):
    """
    Distribute lead to relevant service providers
    """
    try:
        lead = Lead.objects.get(id=lead_id)
        
        # Get eligible providers based on lead type
        eligible_providers = get_eligible_providers(lead)
        
        # Create lead distributions
        distributions = []
        for provider in eligible_providers:
            distribution, created = LeadDistribution.objects.get_or_create(
                lead=lead,
                provider=provider,
                defaults={
                    'status': 'sent',
                    'sent_at': timezone.now()
                }
            )
            
            if created:
                distributions.append(distribution)
        
        # Mark lead as distributed
        lead.is_distributed = True
        lead.distribution_date = timezone.now()
        lead.save()
        
        # Send notifications to providers
        for distribution in distributions:
            send_lead_notification.delay(
                distribution.id,
                'new_lead'
            )
        
        return f"Lead {lead_id} distributed to {len(distributions)} providers"
        
    except Lead.DoesNotExist:
        return f"Lead {lead_id} not found"
    except Exception as e:
        return f"Error distributing lead {lead_id}: {str(e)}"


def get_eligible_providers(lead):
    """
    Get eligible service providers for a lead
    """
    providers = ServiceProviderProfile.objects.filter(
        is_active=True,
        is_verified=True
    )
    
    # Filter by active subscription
    active_subscriptions = Subscription.objects.filter(
        is_active=True,
        expires_at__gt=timezone.now()
    )
    
    providers = providers.filter(
        subscriptions__in=active_subscriptions
    ).distinct()
    
    # Filter by service/package type
    if lead.package:
        # For package leads, only the package owner gets the lead
        providers = providers.filter(id=lead.package.provider.id)
    elif lead.service:
        # For service leads, only the service owner gets the lead
        providers = providers.filter(id=lead.service.provider.id)
    else:
        # For custom leads, get providers who offer relevant services
        if lead.selected_services:
            service_types = lead.selected_services.keys()
            providers = providers.filter(
                services__service_type__in=service_types
            ).distinct()
    
    # Sort by subscription type (Premium first)
    providers = providers.order_by(
        '-subscriptions__plan__priority',
        '-subscriptions__created_at'
    )
    
    return providers


@shared_task
def expire_old_leads():
    """
    Mark old leads as expired
    """
    expired_count = 0
    
    # Get leads that should be expired
    expired_leads = Lead.objects.filter(
        expires_at__lt=timezone.now(),
        status__in=['pending', 'contacted']
    )
    
    for lead in expired_leads:
        lead.status = 'expired'
        lead.save()
        expired_count += 1
    
    return f"Expired {expired_count} leads"


@shared_task
def send_lead_follow_up_reminders():
    """
    Send reminders for lead follow-ups
    """
    from .models import LeadInteraction
    
    # Get interactions that need follow-up
    follow_ups = LeadInteraction.objects.filter(
        follow_up_date__date=timezone.now().date(),
        follow_up_date__lte=timezone.now()
    )
    
    reminder_count = 0
    
    for interaction in follow_ups:
        # Send reminder notification
        send_lead_notification.delay(
            interaction.id,
            'follow_up_reminder'
        )
        reminder_count += 1
    
    return f"Sent {reminder_count} follow-up reminders"


@shared_task
def generate_lead_analytics():
    """
    Generate daily lead analytics
    """
    from django.db.models import Count, Q
    from datetime import date, timedelta
    
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    # Daily stats
    daily_stats = {
        'date': today,
        'total_leads': Lead.objects.filter(created_at__date=today).count(),
        'pending_leads': Lead.objects.filter(
            created_at__date=today,
            status='pending'
        ).count(),
        'contacted_leads': Lead.objects.filter(
            created_at__date=today,
            status='contacted'
        ).count(),
        'converted_leads': Lead.objects.filter(
            created_at__date=today,
            status='converted'
        ).count(),
    }
    
    # Provider performance
    provider_stats = ServiceProviderProfile.objects.filter(
        received_leads__lead__created_at__date=today
    ).annotate(
        leads_received=Count('received_leads'),
        leads_responded=Count(
            'received_leads',
            filter=Q(received_leads__status='responded')
        )
    ).values(
        'business_name',
        'leads_received',
        'leads_responded'
    )
    
    # Store analytics (you might want to create an Analytics model)
    # For now, just return the stats
    return {
        'daily_stats': daily_stats,
        'provider_stats': list(provider_stats)
    }


@shared_task
def cleanup_old_lead_data():
    """
    Clean up old lead data (older than 1 year)
    """
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=365)
    
    # Delete old leads
    old_leads = Lead.objects.filter(
        created_at__lt=cutoff_date,
        status__in=['expired', 'rejected']
    )
    
    deleted_count = old_leads.count()
    old_leads.delete()
    
    return f"Cleaned up {deleted_count} old leads"


@shared_task
def send_lead_summary_email(provider_id, period='daily'):
    """
    Send lead summary email to provider
    """
    try:
        provider = ServiceProviderProfile.objects.get(id=provider_id)
        
        # Calculate date range
        if period == 'daily':
            start_date = timezone.now().date()
            end_date = start_date
        elif period == 'weekly':
            end_date = timezone.now().date()
            start_date = end_date - timezone.timedelta(days=7)
        elif period == 'monthly':
            end_date = timezone.now().date()
            start_date = end_date - timezone.timedelta(days=30)
        
        # Get lead statistics
        leads = Lead.objects.filter(
            distributions__provider=provider,
            created_at__date__range=[start_date, end_date]
        ).distinct()
        
        stats = {
            'total_leads': leads.count(),
            'pending_leads': leads.filter(status='pending').count(),
            'contacted_leads': leads.filter(status='contacted').count(),
            'converted_leads': leads.filter(status='converted').count(),
            'rejected_leads': leads.filter(status='rejected').count(),
        }
        
        # Send email
        subject = f"Lead Summary - {period.title()} Report"
        message = f"""
        Dear {provider.business_name},
        
        Here's your {period} lead summary:
        
        Total Leads: {stats['total_leads']}
        Pending: {stats['pending_leads']}
        Contacted: {stats['contacted_leads']}
        Converted: {stats['converted_leads']}
        Rejected: {stats['rejected_leads']}
        
        Best regards,
        Umrah Chalo Team
        """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [provider.user.email],
            fail_silently=False,
        )
        
        return f"Lead summary sent to {provider.business_name}"
        
    except ServiceProviderProfile.DoesNotExist:
        return f"Provider {provider_id} not found"
    except Exception as e:
        return f"Error sending lead summary: {str(e)}"


@shared_task
def auto_assign_leads_to_premium_providers():
    """
    Auto-assign leads to premium providers based on availability
    """
    from apps.subscriptions.models import SubscriptionPlan
    
    # Get pending leads
    pending_leads = Lead.objects.filter(
        status='pending',
        is_distributed=False
    )
    
    # Get premium providers
    premium_plan = SubscriptionPlan.objects.filter(
        name__icontains='premium'
    ).first()
    
    if not premium_plan:
        return "No premium plan found"
    
    premium_providers = ServiceProviderProfile.objects.filter(
        subscriptions__plan=premium_plan,
        subscriptions__is_active=True,
        subscriptions__expires_at__gt=timezone.now()
    )
    
    assigned_count = 0
    
    for lead in pending_leads:
        # Auto-assign to premium providers first
        eligible_providers = get_eligible_providers(lead)
        premium_eligible = [p for p in eligible_providers if p in premium_providers]
        
        if premium_eligible:
            # Distribute to premium providers
            for provider in premium_eligible:
                LeadDistribution.objects.get_or_create(
                    lead=lead,
                    provider=provider,
                    defaults={
                        'status': 'sent',
                        'sent_at': timezone.now()
                    }
                )
            
            lead.is_distributed = True
            lead.distribution_date = timezone.now()
            lead.priority = 1  # High priority for premium
            lead.save()
            
            assigned_count += 1
    
    return f"Auto-assigned {assigned_count} leads to premium providers"