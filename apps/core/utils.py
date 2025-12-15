import re
import uuid
import random
import string
import logging
import os
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Q
from django.core.exceptions import ValidationError
from PIL import Image
import requests
import json
from decimal import Decimal

logger = logging.getLogger(__name__)

# ==================== OTP AND AUTHENTICATION ====================

def generate_otp(length: int = 6) -> str:
    """Generate numeric OTP"""
    return ''.join(random.choices(string.digits, k=length))


def generate_unique_code(length: int = 6, prefix: str = '') -> str:
    """Generate a unique code with optional prefix"""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    return f"{prefix}{code}" if prefix else code


def generate_session_key() -> str:
    """Generate a unique session key"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=40))


def generate_api_key(length: int = 32) -> str:
    """Generate API key for third-party integrations"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_jwt_token(user_id: str, token_type: str = 'access') -> str:
    """Generate JWT token for user"""
    now = timezone.now()
    
    if token_type == 'access':
        exp = now + timedelta(seconds=getattr(settings, 'JWT_ACCESS_TOKEN_LIFETIME', 3600))
    else:
        exp = now + timedelta(seconds=getattr(settings, 'JWT_REFRESH_TOKEN_LIFETIME', 86400))
    
    payload = {
        'user_id': str(user_id),
        'token_type': token_type,
        'exp': exp.timestamp(),
        'iat': now.timestamp(),
        'jti': str(uuid.uuid4())
    }
    
    return jwt.encode(payload, getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY), algorithm='HS256')


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Decode JWT token and return payload"""
    try:
        payload = jwt.decode(token, getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY), algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")


def generate_referral_code(user_id: str, length: int = 8) -> str:
    """Generate referral code for user"""
    base_code = str(user_id)[:4].upper()
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length-4))
    return f"{base_code}{random_part}"


# ==================== VALIDATION FUNCTIONS ====================

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    pattern = r'^\+?1?\d{9,15}$'
    return re.match(pattern, phone) is not None


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password_strength(password: str) -> List[str]:
    """Validate password strength and return list of errors"""
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    
    if not any(char.isupper() for char in password):
        errors.append("Password must contain at least one uppercase letter.")
    
    if not any(char.islower() for char in password):
        errors.append("Password must contain at least one lowercase letter.")
    
    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one digit.")
    
    if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in password):
        errors.append("Password must contain at least one special character.")
    
    return errors


def validate_url(url: str) -> bool:
    """Validate URL format"""
    pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
    return re.match(pattern, url) is not None


def validate_date_format(date_str: str, format: str = '%Y-%m-%d') -> bool:
    """Validate date format"""
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False


def validate_credit_card(card_number: str) -> bool:
    """Validate credit card number using Luhn algorithm"""
    def luhn_check(card_num):
        def digits_of(n):
            return [int(d) for d in str(n)]
        
        digits = digits_of(card_num)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d*2))
        return checksum % 10 == 0
    
    return luhn_check(card_number.replace(' ', '').replace('-', ''))


# ==================== PHONE AND EMAIL UTILITIES ====================

def clean_phone_number(phone: str) -> str:
    """Clean phone number by removing non-numeric characters"""
    return re.sub(r'\D', '', phone)


def format_phone_number(phone: str, country_code: str = '+91') -> str:
    """Format phone number with country code"""
    cleaned = clean_phone_number(phone)
    if not cleaned.startswith(country_code.replace('+', '')):
        return f"{country_code}{cleaned}"
    return f"+{cleaned}"


def sanitize_phone_number(phone: str) -> Optional[str]:
    """Sanitize and format phone number"""
    if not phone:
        return None
    
    # Remove all non-digit characters
    phone = ''.join(filter(str.isdigit, phone))
    
    # Add country code if not present
    if len(phone) == 10:
        phone = '91' + phone  # Default to India
    
    return phone


def generate_username_from_email(email: str) -> str:
    """Generate username from email"""
    username = email.split('@')[0]
    # Remove any special characters
    username = ''.join(char for char in username if char.isalnum())
    return username.lower()


def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """Mask sensitive data like phone numbers, emails"""
    if len(data) <= visible_chars:
        return mask_char * len(data)
    
    if '@' in data:  # Email
        local, domain = data.split('@')
        masked_local = local[:2] + mask_char * (len(local) - 2)
        return f"{masked_local}@{domain}"
    else:  # Phone or other
        visible_end = data[-visible_chars:]
        masked_part = mask_char * (len(data) - visible_chars)
        return masked_part + visible_end


# ==================== EMAIL FUNCTIONS ====================

def send_otp(email: str, otp: str, purpose: str) -> bool:
    """Send OTP via email"""
    try:
        subject_mapping = {
            'email_verification': 'Verify Your Email - Umrah Chalo',
            'phone_verification': 'Verify Your Phone - Umrah Chalo',
            'password_reset': 'Reset Your Password - Umrah Chalo',
            'login': 'Login OTP - Umrah Chalo',
        }
        
        template_mapping = {
            'email_verification': 'email/email_verification.html',
            'phone_verification': 'email/phone_verification.html',
            'password_reset': 'email/password_reset.html',
            'login': 'email/login_otp.html',
        }
        
        subject = subject_mapping.get(purpose, 'OTP - Umrah Chalo')
        template = template_mapping.get(purpose, 'email/default_otp.html')
        
        context = {
            'otp': otp,
             'purpose': purpose,
             'expires_in': 10 if purpose == 'password_reset' else 5,
              'site_name': 'Umrah Chalo',
             'user_email': email,
              'expiry_datetime': (timezone.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M'),
           }
        
        # ✅ Pass template as is, do NOT modify
        return send_email_notification(email, subject, template, context)
        
    except Exception as e:
        logger.error(f"Failed to send OTP to {email}: {str(e)}")
        return False


def send_email_notification(
    to_email: str,
    subject: str,
    template_name: str,
    context: Dict[str, Any],
    from_email: str = None
) -> bool:
    """Send email notification using template"""
    try:
        # ✅ Use template_name directly, do not add .html
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=[to_email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        return False

def send_welcome_email(user) -> bool:
    """Send welcome email to new user"""
    context = {
        'user': user,
        'site_name': 'Umrah Chalo',
        'login_url': f"{getattr(settings, 'FRONTEND_URL', '')}/login"
    }
    
    return send_email_notification(
        user.email,
        'Welcome to Umrah Chalo!',
        'welcome',
        context
    )


def send_password_changed_notification(user) -> bool:
    """Send notification when password is changed"""
    context = {
        'user': user,
        'site_name': 'Umrah Chalo',
        'change_time': timezone.now()
    }
    
    return send_email_notification(
        user.email,
        'Password Changed - Umrah Chalo',
        'password_changed',
        context
    )


def send_bulk_email(recipients: List[str], subject: str, template_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Send bulk email notifications"""
    success_count = 0
    failed_recipients = []
    
    for email in recipients:
        try:
            if send_email_notification(email, subject, template_name, context):
                success_count += 1
            else:
                failed_recipients.append(email)
        except Exception as e:
            logger.error(f"Failed to send bulk email to {email}: {e}")
            failed_recipients.append(email)
    
    return {
        'success_count': success_count,
        'failed_count': len(failed_recipients),
        'failed_recipients': failed_recipients
    }


# ==================== SMS FUNCTIONS ====================

def send_sms_otp(phone: str, otp: str, purpose: str) -> bool:
    """Send OTP via SMS"""
    try:
        # Log the OTP for development
        logger.info(f"SMS OTP for {phone}: {otp} (Purpose: {purpose})")
        
        # Implement actual SMS service integration here
        # Example with Twilio:
        # from twilio.rest import Client
        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # message = client.messages.create(
        #     body=f"Your Umrah Chalo OTP is: {otp}. Valid for 5 minutes.",
        #     from_=settings.TWILIO_PHONE_NUMBER,
        #     to=phone
        # )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send SMS OTP to {phone}: {str(e)}")
        return False


def send_sms_notification(phone: str, message: str) -> bool:
    """Send SMS notification"""
    try:
        # Implement SMS service integration
        logger.info(f"SMS notification to {phone}: {message}")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone}: {e}")
        return False


# ==================== CACHING UTILITIES ====================

def cache_key(prefix: str, *args) -> str:
    """Generate cache key with prefix and arguments"""
    key_parts = [str(arg) for arg in args]
    return f"{prefix}:{'_'.join(key_parts)}"


def get_cached_data(key: str, default=None):
    """Get data from cache"""
    return cache.get(key, default)


def set_cached_data(key: str, value: Any, timeout: int = 300):
    """Set data in cache with timeout"""
    cache.set(key, value, timeout)


def delete_cached_data(key: str):
    """Delete data from cache"""
    cache.delete(key)


def cache_model_data(model_class, pk, timeout: int = 300):
    """Cache model instance data"""
    key = cache_key('model', model_class.__name__, pk)
    cached_data = get_cached_data(key)
    
    if cached_data is None:
        try:
            instance = model_class.objects.get(pk=pk)
            set_cached_data(key, instance, timeout)
            return instance
        except model_class.DoesNotExist:
            return None
    
    return cached_data


def invalidate_model_cache(model_class, pk):
    """Invalidate cached model data"""
    key = cache_key('model', model_class.__name__, pk)
    delete_cached_data(key)


# ==================== REQUEST UTILITIES ====================

def get_client_ip(request) -> str:
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request) -> str:
    """Get user agent from request"""
    return request.META.get('HTTP_USER_AGENT', '')


def get_device_type(request) -> str:
    """Detect device type from user agent"""
    user_agent = get_user_agent(request).lower()
    
    if 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent:
        return 'mobile'
    elif 'tablet' in user_agent or 'ipad' in user_agent:
        return 'tablet'
    else:
        return 'desktop'


def is_ajax_request(request) -> bool:
    """Check if request is AJAX"""
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


def get_request_data(request) -> Dict[str, Any]:
    """Get request data from GET or POST"""
    if request.method == 'GET':
        return request.GET.dict()
    elif request.method == 'POST':
        return request.POST.dict()
    else:
        return {}


# ==================== SECURITY UTILITIES ====================

def check_rate_limit(identifier: str, action: str, limit: int = 5, window_minutes: int = 15) -> bool:
    """Check if user has exceeded rate limit for a specific action"""
    key = cache_key('rate_limit', identifier, action)
    attempts = get_cached_data(key, 0)
    
    if attempts >= limit:
        return False
    
    set_cached_data(key, attempts + 1, window_minutes * 60)
    return True


def create_user_session(user, request):
    """Create a new user session"""
    from apps.core.models import UserSession
    
    session_key = generate_session_key()
    device_info = get_user_agent(request)
    ip_address = get_client_ip(request)
    
    session = UserSession.objects.create(
        user=user,
        session_key=session_key,
        device_info=device_info,
        ip_address=ip_address
    )
    
    return session


def invalidate_user_sessions(user, exclude_session=None):
    """Invalidate all user sessions except the current one"""
    from apps.core.models import UserSession
    
    sessions = UserSession.objects.filter(user=user, is_active=True)
    
    if exclude_session:
        sessions = sessions.exclude(id=exclude_session.id)
    
    sessions.update(is_active=False)


def log_security_event(user, event_type: str, details: str, request=None):
    """Log security-related events"""
    logger.warning(f"Security Event - User: {user.email}, Type: {event_type}, Details: {details}")
    
    if request:
        logger.warning(f"IP: {get_client_ip(request)}, User Agent: {get_user_agent(request)}")


def check_user_permissions(user, required_permissions: List[str]) -> bool:
    """Check if user has required permissions"""
    if hasattr(user, 'user_type') and user.user_type == 'admin':
        return True
    
    # Define permission mappings
    permission_mappings = {
        'can_manage_packages': ['provider', 'admin'],
        'can_view_leads': ['provider', 'admin'],
        'can_manage_subscriptions': ['provider', 'admin'],
        'can_access_reviews': ['pilgrim', 'provider', 'admin'],
        'can_admin_functions': ['admin'],
    }
    
    for permission in required_permissions:
        allowed_roles = permission_mappings.get(permission, [])
        if hasattr(user, 'user_type') and user.user_type not in allowed_roles:
            return False
    
    return True


# ==================== LOGGING AND ACTIVITY ====================

def log_activity(user, action: str, model_name: str, object_id: str = '', request=None, details: Dict = None):
    """Log user activity"""
    from apps.core.models import ActivityLog
    
    activity_data = {
        'user': user,
        'action': action,
        'model_name': model_name,
        'object_id': object_id,
        'details': details or {}
    }
    
    if request:
        activity_data['ip_address'] = get_client_ip(request)
        activity_data['user_agent'] = get_user_agent(request)
    
    try:
        ActivityLog.objects.create(**activity_data)
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")


def log_error(error: Exception, context: Dict[str, Any] = None):
    """Log error with context"""
    logger.error(f"Error: {str(error)}", extra={'context': context or {}})


def log_api_call(endpoint: str, method: str, user=None, response_status: int = None, duration: float = None):
    """Log API call details"""
    logger.info(f"API Call: {method} {endpoint} - User: {user} - Status: {response_status} - Duration: {duration}ms")


# ==================== FILE UTILITIES ====================

def compress_image(image_path: str, max_size: tuple = (800, 600), quality: int = 85) -> str:
    """Compress image and return the compressed image path"""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Resize if larger than max_size
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save compressed image
            compressed_path = image_path.replace('.', '_compressed.')
            img.save(compressed_path, optimize=True, quality=quality)
            
            return compressed_path
    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        return image_path


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return os.path.splitext(filename)[1].lower()


def is_valid_image(filename: str) -> bool:
    """Check if file is a valid image"""
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    return get_file_extension(filename) in valid_extensions


def is_valid_document(filename: str) -> bool:
    """Check if file is a valid document"""
    valid_extensions = ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx']
    return get_file_extension(filename) in valid_extensions


def generate_unique_filename(filename: str) -> str:
    """Generate unique filename with timestamp and uuid"""
    name, ext = os.path.splitext(filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"{name}_{timestamp}_{unique_id}{ext}"


def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"


# ==================== STRING UTILITIES ====================

def slugify_text(text: str) -> str:
    """Create slug from text"""
    return slugify(text)


def truncate_text(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """Truncate text to specified length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def capitalize_words(text: str) -> str:
    """Capitalize first letter of each word"""
    return ' '.join(word.capitalize() for word in text.split())


def remove_html_tags(text: str) -> str:
    """Remove HTML tags from text"""
    return strip_tags(text)


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Extract keywords from text"""
    # Simple keyword extraction (remove common words)
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall', 'this', 'that', 'these', 'those'}
    
    words = re.findall(r'\b\w+\b', text.lower())
    keywords = [word for word in words if word not in common_words and len(word) > 2]
    
    # Count frequency and return top keywords
    from collections import Counter
    word_counts = Counter(keywords)
    return [word for word, count in word_counts.most_common(max_keywords)]


# ==================== MATHEMATICAL UTILITIES ====================

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates using Haversine formula"""
    from math import radians, cos, sin, asin, sqrt
    
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    
    return c * r


def calculate_percentage(part: float, total: float) -> float:
    """Calculate percentage"""
    if total == 0:
        return 0
    return (part / total) * 100


def round_to_nearest(value: float, nearest: float = 0.5) -> float:
    """Round to nearest specified value"""
    return round(value / nearest) * nearest


def calculate_tax(amount: Decimal, tax_rate: Decimal) -> Decimal:
    """Calculate tax amount"""
    return amount * (tax_rate / 100)


def calculate_discount(original_price: Decimal, discount_percentage: Decimal) -> Decimal:
    """Calculate discount amount"""
    return original_price * (discount_percentage / 100)


# ==================== FORMATTING UTILITIES ====================

def format_currency(amount: float, currency: str = 'INR') -> str:
    """Format currency amount"""
    currency_symbols = {
        'INR': '₹',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'JPY': '¥',
        'CAD': 'C$',
        'AUD': 'A$'
    }
    
    symbol = currency_symbols.get(currency, currency)
    return f"{symbol}{amount:,.2f}"


def format_date(date_obj, format: str = '%d %B %Y') -> str:
    """Format date object"""
    if date_obj:
        return date_obj.strftime(format)
    return ''


def format_datetime(datetime_obj, format: str = '%d %B %Y %I:%M %p') -> str:
    """Format datetime object"""
    if datetime_obj:
        return datetime_obj.strftime(format)
    return ''


def format_phone_display(phone: str) -> str:
    """Format phone number for display"""
    if len(phone) >= 10:
        return f"{phone[:-10]} {phone[-10:-7]} {phone[-7:-4]} {phone[-4:]}"
    return phone


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minutes"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} hours {minutes} minutes"


# ==================== DATETIME UTILITIES ====================

def is_business_hours(start_time: str = '09:00', end_time: str = '18:00') -> bool:
    """Check if current time is within business hours"""
    now = datetime.now().time()
    start = datetime.strptime(start_time, '%H:%M').time()
    end = datetime.strptime(end_time, '%H:%M').time()
    
    return start <= now <= end


def get_business_days_between(start_date, end_date) -> int:
    """Calculate business days between two dates"""
    from datetime import timedelta
    
    business_days = 0
    current_date = start_date
    
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Monday to Friday
            business_days += 1
        current_date += timedelta(days=1)
    
    return business_days


def get_next_business_day(date_obj):
    """Get next business day"""
    from datetime import timedelta
    
    next_day = date_obj + timedelta(days=1)
    while next_day.weekday() > 4:  # Saturday = 5, Sunday = 6
        next_day += timedelta(days=1)
    
    return next_day


def get_time_ago(datetime_obj) -> str:
    """Get human readable time ago string"""
    now = timezone.now()
    diff = now - datetime_obj
    
    if diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hours ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minutes ago"
    else:
        return "Just now"


# ==================== MISCELLANEOUS UTILITIES ====================

def get_random_color() -> str:
    """Generate random hex color"""
    return f"#{random.randint(0, 0xFFFFFF):06x}"


def generate_qr_code(data: str, file_path: str = None) -> str:
    """Generate QR code for given data"""
    try:
        import qrcode
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        if file_path:
            img.save(file_path)
            return file_path
        else:
            # Return base64 encoded image
            from io import BytesIO
            import base64
            
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            return f"data:image/png;base64,{img_str}"
            
    except ImportError:
        logger.error("qrcode library not installed")
        return None
    except Exception as e:
        logger.error(f"QR code generation failed: {e}")
        return None


def send_notification(user, title: str, message: str, notification_type: str = 'info') -> bool:
    """Send in-app notification to user"""
    try:
        from apps.core.models import Notification
        
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type
        )
        
        # Also log the notification
        logger.info(f"Notification sent to {user.email}: {title}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False


def get_weather_info(city: str) -> Dict[str, Any]:
    """Get weather information for a city"""
    try:
        # This would require an API key from a weather service
        # Example with OpenWeatherMap API
        api_key = getattr(settings, 'WEATHER_API_KEY', '')
        if not api_key:
            return {}
            
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'temperature': data['main']['temp'],
                'description': data['weather'][0]['description'],
                'humidity': data['main']['humidity'],
                'wind_speed': data['wind']['speed']
            }
        
        return {}
        
    except Exception as e:
        logger.error(f"Weather API call failed: {e}")
        return {}


# ==================== SEARCH AND FILTERING ====================

def build_search_query(search_term: str, fields: List[str]) -> Q:
    """Build Django Q object for search across multiple fields"""
    query = Q()
    
    if search_term:
        for field in fields:
            query |= Q(**{f"{field}__icontains": search_term})
    
    return query


def apply_filters(queryset, filters: Dict[str, Any]):
    """Apply filters to Django queryset"""
    for field, value in filters.items():
        if value is not None and value != '':
            if isinstance(value, list):
                queryset = queryset.filter(**{f"{field}__in": value})
            else:
                queryset = queryset.filter(**{field: value})
    
    return queryset


def paginate_queryset(queryset, page_number: int, page_size: int = 20):
    """Paginate Django queryset"""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    paginator = Paginator(queryset, page_size)
    
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    
    return {
        'items': page.object_list,
        'has_next': page.has_next(),
        'has_previous': page.has_previous(),
        'current_page': page.number,
        'total_pages': paginator.num_pages,
        'total_items': paginator.count
    }


# ==================== BACKUP AND EXPORT ====================

def export_to_csv(queryset, fields: List[str], filename: str = None) -> str:
    """Export queryset to CSV file"""
    import csv
    from django.http import HttpResponse
    
    if not filename:
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([field.replace('_', ' ').title() for field in fields])
    
    # Write data
    for obj in queryset:
        row = []
        for field in fields:
            value = getattr(obj, field, '')
            if hasattr(value, 'strftime'):
                value = value.strftime('%Y-%m-%d %H:%M:%S')
            row.append(str(value))
        writer.writerow(row)
    
    return response


def backup_database() -> bool:
    """Create database backup"""
    try:
        import subprocess
        from django.conf import settings
        
        db_settings = settings.DATABASES['default']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"backup_{timestamp}.sql"
        
        # This is for PostgreSQL - adjust for other databases
        cmd = [
            'pg_dump',
            '-h', db_settings['HOST'],
            '-p', str(db_settings['PORT']),
            '-U', db_settings['USER'],
            '-d', db_settings['NAME'],
            '-f', backup_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Database backup created: {backup_file}")
            return True
        else:
            logger.error(f"Database backup failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        return False


# ==================== THIRD-PARTY INTEGRATIONS ====================

def send_slack_notification(message: str, channel: str = None) -> bool:
    """Send notification to Slack"""
    try:
        slack_webhook = getattr(settings, 'SLACK_WEBHOOK_URL', '')
        if not slack_webhook:
            return False
            
        payload = {
            'text': message,
            'channel': channel or '#general'
        }
        
        response = requests.post(slack_webhook, json=payload, timeout=10)
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        return False


def upload_to_s3(file_obj, bucket_name: str, key: str) -> str:
    """Upload file to AWS S3"""
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', ''),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', ''),
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
        )
        
        s3_client.upload_fileobj(file_obj, bucket_name, key)
        
        # Generate public URL
        url = f"https://{bucket_name}.s3.amazonaws.com/{key}"
        return url
        
    except ClientError as e:
        logger.error(f"S3 upload failed: {e}")
        return None
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return None


def send_push_notification(user_tokens: List[str], title: str, body: str, data: Dict = None) -> bool:
    """Send push notification using FCM"""
    try:
        from pyfcm import FCMNotification
        
        push_service = FCMNotification(
            api_key=getattr(settings, 'FCM_SERVER_KEY', '')
        )
        
        result = push_service.notify_multiple_devices(
            registration_ids=user_tokens,
            message_title=title,
            message_body=body,
            data_message=data
        )
        
        return result['success'] > 0
        
    except Exception as e:
        logger.error(f"Push notification failed: {e}")
        return False


# ==================== TASK SCHEDULING ====================

def schedule_task(task_name: str, run_at: datetime, *args, **kwargs) -> bool:
    """Schedule a task to run at specific time"""
    try:
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        import json
        
        # Create crontab schedule
        crontab = CrontabSchedule.objects.create(
            minute=run_at.minute,
            hour=run_at.hour,
            day_of_month=run_at.day,
            month_of_year=run_at.month,
        )
        
        # Create periodic task
        PeriodicTask.objects.create(
            name=task_name,
            task=task_name,
            crontab=crontab,
            args=json.dumps(args),
            kwargs=json.dumps(kwargs),
            one_off=True
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Task scheduling failed: {e}")
        return False


# ==================== HEALTH CHECKS ====================

def check_database_health() -> Dict[str, Any]:
    """Check database connection health"""
    try:
        from django.db import connections
        from django.db.utils import OperationalError
        
        db_conn = connections['default']
        db_conn.cursor()
        
        return {
            'status': 'healthy',
            'database': 'connected',
            'timestamp': timezone.now().isoformat()
        }
        
    except OperationalError:
        return {
            'status': 'unhealthy',
            'database': 'disconnected',
            'timestamp': timezone.now().isoformat()
        }


def check_cache_health() -> Dict[str, Any]:
    """Check cache connection health"""
    try:
        cache.set('health_check', 'test', 10)
        result = cache.get('health_check')
        
        if result == 'test':
            return {
                'status': 'healthy',
                'cache': 'connected',
                'timestamp': timezone.now().isoformat()
            }
        else:
            return {
                'status': 'unhealthy',
                'cache': 'not_responding',
                'timestamp': timezone.now().isoformat()
            }
            
    except Exception as e:
        return {
            'status': 'unhealthy',
            'cache': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


def system_health_check() -> Dict[str, Any]:
    """Comprehensive system health check"""
    return {
        'database': check_database_health(),
        'cache': check_cache_health(),
        'timestamp': timezone.now().isoformat(),
        'version': getattr(settings, 'VERSION', '1.0.0')
    }


# ==================== CLEANUP UTILITIES ====================

def cleanup_old_files(directory: str, days_old: int = 30) -> int:
    """Clean up old files from directory"""
    import os
    from datetime import timedelta
    
    count = 0
    cutoff_date = datetime.now() - timedelta(days=days_old)
    
    try:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_time < cutoff_date:
                    os.remove(filepath)
                    count += 1
                    
        logger.info(f"Cleaned up {count} old files from {directory}")
        return count
        
    except Exception as e:
        logger.error(f"File cleanup failed: {e}")
        return 0


def cleanup_expired_sessions() -> int:
    """Clean up expired user sessions"""
    try:
        from apps.core.models import UserSession
        
        expired_sessions = UserSession.objects.filter(
            expires_at__lt=timezone.now()
        )
        
        count = expired_sessions.count()
        expired_sessions.delete()
        
        logger.info(f"Cleaned up {count} expired sessions")
        return count
        
    except Exception as e:
        logger.error(f"Session cleanup failed: {e}")
        return 0


def cleanup_old_logs(days_old: int = 90) -> bool:
    """Clean up old log entries"""
    try:
        from apps.core.models import ActivityLog
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        old_logs = ActivityLog.objects.filter(created_at__lt=cutoff_date)
        
        count = old_logs.count()
        old_logs.delete()
        
        logger.info(f"Cleaned up {count} old log entries")
        return True
        
    except Exception as e:
        logger.error(f"Log cleanup failed: {e}")