from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_lead_notification(distribution_id, notification_type):
    """
    Send lead notification to service provider
    """
    try:
        from apps.leads.models import LeadDistribution, LeadInteraction
        
        if notification_type == 'follow_up_reminder':
            # Handle follow-up reminder notifications
            interaction = LeadInteraction.objects.get(id=distribution_id)
            provider = interaction.distribution.provider
            lead = interaction.distribution.lead
            
            subject = f"Follow-up Reminder - Lead #{lead.id}"
            message = f"""
            Dear {provider.business_name},
            
            This is a reminder to follow up on lead #{lead.id}.
            
            Customer: {lead.customer_name}
            Phone: {lead.phone}
            Email: {lead.email}
            Service: {lead.service.name if lead.service else 'Custom Request'}
            
            Follow-up scheduled for: {interaction.follow_up_date.strftime('%Y-%m-%d %H:%M')}
            
            Please log in to your dashboard to view full details and update the lead status.
            
            Best regards,
            Umrah Chalo Team
            """
            
        else:
            # Handle new lead notifications
            distribution = LeadDistribution.objects.get(id=distribution_id)
            provider = distribution.provider
            lead = distribution.lead
            
            if notification_type == 'new_lead':
                subject = f"New Lead Received - #{lead.id}"
                message = f"""
                Dear {provider.business_name},
                
                You have received a new lead!
                
                Lead Details:
                - Customer: {lead.customer_name}
                - Phone: {lead.phone}
                - Email: {lead.email}
                - Service: {lead.service.name if lead.service else lead.package.name if lead.package else 'Custom Request'}
                - Budget: {lead.budget if lead.budget else 'Not specified'}
                - Travel Date: {lead.travel_date.strftime('%Y-%m-%d') if lead.travel_date else 'Not specified'}
                - Message: {lead.message or 'No additional message'}
                
                Please log in to your dashboard to view full details and respond to this lead.
                
                Dashboard URL: {settings.FRONTEND_URL}/provider/dashboard/leads/
                
                Best regards,
                Umrah Chalo Team
                """
            
            elif notification_type == 'lead_response':
                subject = f"Lead Response Required - #{lead.id}"
                message = f"""
                Dear {provider.business_name},
                
                Customer {lead.customer_name} is waiting for your response to lead #{lead.id}.
                
                Please respond as soon as possible to maintain good customer service.
                
                Dashboard URL: {settings.FRONTEND_URL}/provider/dashboard/leads/{lead.id}/
                
                Best regards,
                Umrah Chalo Team
                """
            
            else:
                logger.warning(f"Unknown notification type: {notification_type}")
                return f"Unknown notification type: {notification_type}"
        
        # Send email notification
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [provider.user.email],
            fail_silently=False,
        )
        
        # Log the notification
        logger.info(f"Sent {notification_type} notification to {provider.business_name}")
        
        return f"Notification sent successfully to {provider.business_name}"
        
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return f"Error sending notification: {str(e)}"


@shared_task
def send_bulk_notifications(provider_ids, notification_type, context=None):
    """
    Send bulk notifications to multiple providers
    """
    try:
        from apps.authentication.models import ServiceProviderProfile
        
        providers = ServiceProviderProfile.objects.filter(id__in=provider_ids)
        sent_count = 0
        
        for provider in providers:
            try:
                if notification_type == 'subscription_expiry':
                    subject = "Subscription Expiry Reminder"
                    message = f"""
                    Dear {provider.business_name},
                    
                    Your subscription is expiring soon. Please renew to continue receiving leads.
                    
                    Expiry Date: {context.get('expiry_date', 'N/A')}
                    
                    Renew now: {settings.FRONTEND_URL}/provider/subscription/
                    
                    Best regards,
                    Umrah Chalo Team
                    """
                
                elif notification_type == 'system_maintenance':
                    subject = "System Maintenance Notification"
                    message = f"""
                    Dear {provider.business_name},
                    
                    We will be performing system maintenance on {context.get('maintenance_date', 'TBD')}.
                    
                    Duration: {context.get('duration', 'TBD')}
                    
                    During this time, some features may be temporarily unavailable.
                    
                    Best regards,
                    Umrah Chalo Team
                    """
                
                elif notification_type == 'new_features':
                    subject = "New Features Available"
                    message = f"""
                    Dear {provider.business_name},
                    
                    We've added new features to improve your experience:
                    
                    {context.get('features', 'Check your dashboard for details')}
                    
                    Log in to explore: {settings.FRONTEND_URL}/provider/dashboard/
                    
                    Best regards,
                    Umrah Chalo Team
                    """
                
                else:
                    continue
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [provider.user.email],
                    fail_silently=False,
                )
                
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Error sending notification to {provider.business_name}: {str(e)}")
                continue
        
        return f"Bulk notification sent to {sent_count} providers"
        
    except Exception as e:
        logger.error(f"Error in bulk notification: {str(e)}")
        return f"Error in bulk notification: {str(e)}"


@shared_task
def send_customer_notification(lead_id, notification_type):
    """
    Send notifications to customers
    """
    try:
        from apps.leads.models import Lead
        
        lead = Lead.objects.get(id=lead_id)
        
        if notification_type == 'lead_confirmed':
            subject = "Lead Submission Confirmed"
            message = f"""
            Dear {lead.customer_name},
            
            Thank you for submitting your inquiry through Umrah Chalo.
            
            Your request has been received and will be forwarded to relevant service providers.
            
            Reference ID: #{lead.id}
            
            You should expect to hear from service providers within 24-48 hours.
            
            Best regards,
            Umrah Chalo Team
            """
            
        elif notification_type == 'provider_response':
            subject = "Service Provider Response Received"
            message = f"""
            Dear {lead.customer_name},
            
            A service provider has responded to your inquiry (Reference: #{lead.id}).
            
            Please check your email and phone for direct communication from the provider.
            
            If you need any assistance, please contact our support team.
            
            Best regards,
            Umrah Chalo Team
            """
            
        else:
            logger.warning(f"Unknown customer notification type: {notification_type}")
            return f"Unknown notification type: {notification_type}"
        
        # Send email to customer
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [lead.email],
            fail_silently=False,
        )
        
        logger.info(f"Sent {notification_type} notification to customer {lead.customer_name}")
        
        return f"Customer notification sent successfully"
        
    except Exception as e:
        logger.error(f"Error sending customer notification: {str(e)}")
        return f"Error sending customer notification: {str(e)}"


@shared_task
def send_admin_notification(notification_type, context=None):
    """
    Send notifications to admin users
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()

        
        # Get admin users
        admin_users = User.objects.filter(is_staff=True, is_superuser=True)
        
        if notification_type == 'new_provider_registration':
            subject = "New Provider Registration"
            provider_name = context.get('provider_name', 'Unknown')
            message = f"""
            New service provider has registered: {provider_name}
            
            Please review and approve the registration.
            
            Admin Panel: {settings.FRONTEND_URL}/admin/
            """
            
        elif notification_type == 'high_lead_volume':
            subject = "High Lead Volume Alert"
            lead_count = context.get('lead_count', 0)
            message = f"""
            High lead volume detected: {lead_count} leads in the last hour.
            
            Please monitor system performance.
            
            Admin Panel: {settings.FRONTEND_URL}/admin/
            """
            
        elif notification_type == 'system_error':
            subject = "System Error Alert"
            error_message = context.get('error', 'Unknown error')
            message = f"""
            System error detected:
            
            Error: {error_message}
            
            Please investigate immediately.
            """
            
        else:
            logger.warning(f"Unknown admin notification type: {notification_type}")
            return f"Unknown notification type: {notification_type}"
        
        # Send to all admin users
        admin_emails = [user.email for user in admin_users if user.email]
        
        if admin_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=False,
            )
            
            logger.info(f"Sent {notification_type} notification to {len(admin_emails)} admins")
            return f"Admin notification sent to {len(admin_emails)} users"
        else:
            logger.warning("No admin emails found")
            return "No admin emails found"
        
    except Exception as e:
        logger.error(f"Error sending admin notification: {str(e)}")
        return f"Error sending admin notification: {str(e)}"


@shared_task
def send_sms_notification(phone_number, message):
    """
    Send SMS notification (placeholder for SMS service integration)
    """
    try:
        # TODO: Integrate with SMS service (Twilio, AWS SNS, etc.)
        # For now, just log the message
        logger.info(f"SMS to {phone_number}: {message}")
        
        # Example integration with Twilio:
        # from twilio.rest import Client
        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # client.messages.create(
        #     body=message,
        #     from_=settings.TWILIO_PHONE_NUMBER,
        #     to=phone_number
        # )
        
        return f"SMS sent successfully to {phone_number}"
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return f"Error sending SMS: {str(e)}"


@shared_task
def send_whatsapp_notification(phone_number, message):
    """
    Send WhatsApp notification (placeholder for WhatsApp Business API)
    """
    try:
        # TODO: Integrate with WhatsApp Business API
        # For now, just log the message
        logger.info(f"WhatsApp to {phone_number}: {message}")
        
        return f"WhatsApp message sent successfully to {phone_number}"
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return f"Error sending WhatsApp message: {str(e)}"


@shared_task
def cleanup_old_notifications():
    """
    Clean up old notification logs (if you have a notification model)
    """
    try:
        from datetime import timedelta
        
        # TODO: If you have a Notification model, clean up old records
        # cutoff_date = timezone.now() - timedelta(days=90)
        # old_notifications = Notification.objects.filter(created_at__lt=cutoff_date)
        # deleted_count = old_notifications.count()
        # old_notifications.delete()
        
        logger.info("Notification cleanup completed")
        return "Notification cleanup completed"
        
    except Exception as e:
        logger.error(f"Error in notification cleanup: {str(e)}")
        return f"Error in notification cleanup: {str(e)}"