import random
import requests
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

def generate_login_otp():
    return str(random.randint(100000, 999999))


def send_email_otp(to_email, otp, purpose="login"):
    subject = f"Your OTP for {purpose.capitalize()}"
    message = f"Your OTP is {otp}. It is valid for 5 minutes."
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email])


def send_sms_otp(to_phone, otp, purpose="login"):
    """
    Sends OTP via SMS (Wappie API) for Indian numbers (+91).
    For international numbers, placeholder for WhatsApp integration.
    """
    try:
        # Sanitize phone number and identify country
        phone_str = str(to_phone).strip()
        
        # Determine if Indian number
        # 10 digits -> India
        # Starts with +91 or 91 -> India
        is_india = False
        clean_phone = phone_str
        country_code = "+91" # Default to +91 if we detect India

        if phone_str.startswith('+91'):
            is_india = True
            clean_phone = phone_str[3:]
            country_code = "+91"
        elif phone_str.startswith('91') and len(phone_str) > 10:
            is_india = True
            clean_phone = phone_str[2:]
            country_code = "+91"
        elif len(phone_str) == 10:
            is_india = True
            clean_phone = phone_str
            country_code = "+91"
        
        if is_india:
            # Wappie SMS API for India
            access_token = "1648c635eab1561d92b0d5e4ab2ce19b"
            sender = "UMCHLO"
            service = "SI"
            
            # The template message provided by the user
            # {{1}} = OTP, {{2}} = validity
            message_template = "Your OTP for Signup on Umrah Chalo is {otp}. This OTP is valid for 5 minutes. Do not share it with anyone. - Team Umrah Chalo"
            message = message_template.format(otp=otp)
            
            url = "https://apis.wappie.shop/v1/sms/messages"
            params = {
                "access_token": access_token,
                "to": clean_phone,
                "country_code": country_code,
                "sender": sender,
                "service": service,
                "message": message
            }
            
            logger.info(f"Sending SMS to {country_code}{clean_phone} via Wappie API")
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                logger.info(f"SMS sent successfully: {response.text}")
                return True
            else:
                logger.error(f"Failed to send SMS via Wappie: {response.status_code} - {response.text}")
                return False
        else:
            # Placeholder for WhatsApp API (Other countries)
            # User mentioned this will be available in 2 days.
            logger.warning(f"International number detected: {phone_str}. WhatsApp integration pending.")
            # For now, just log it or use an alternative if available
            return False

    except Exception as e:
        logger.error(f"Error in send_sms_otp: {str(e)}")
        return False
