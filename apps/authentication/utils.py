import random
import requests
import logging
import phonenumbers
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


# ==========================================================
# OTP SERVICE — Redis-backed, expiry, retry limiting
# ==========================================================

class OTPService:
    """
    Unified service for generating, storing, and verifying OTPs using Redis.
    - 5-minute auto expiry
    - Max 5 retry attempts
    - Rate limit: 3 OTP requests per 10 minutes per identifier
    """

    @staticmethod
    def generate_otp(length=6):
        return "".join([str(random.randint(0, 9)) for _ in range(length)])

    @staticmethod
    def _otp_key(identifier, purpose):
        return f"otp:{purpose}:{identifier}"

    @staticmethod
    def _attempts_key(identifier, purpose):
        return f"otp_attempts:{purpose}:{identifier}"

    @staticmethod
    def _rate_key(identifier):
        return f"otp_rate:{identifier}"

    @classmethod
    def check_rate_limit(cls, identifier, limit=4, window=600):
        """
        Returns (is_allowed: bool, seconds_left: int).
        Limit: 4 OTP requests per 10 minutes per identifier.
        """
        key = cls._rate_key(identifier)
        count = cache.get(key, 0)
        
        if count >= limit:
            # Get remaining time from cache
            # Note: Redis TTL returns seconds. Django cache wrapper might vary, 
            # but we can estimate or use the raw client if needed.
            # Using 600 as default if ttl is not available.
            try:
                ttl = cache.ttl(key) if hasattr(cache, 'ttl') else window
                return False, max(0, ttl)
            except:
                return False, window

        cache.set(key, count + 1, timeout=window)
        return True, 0

    @classmethod
    def store_otp(cls, identifier, otp, purpose, timeout=300):
        """
        Stores OTP in Redis with a 5-minute TTL. Resets attempt counter.
        """
        cache.set(cls._otp_key(identifier, purpose), otp, timeout=timeout)
        cache.set(cls._attempts_key(identifier, purpose), 0, timeout=timeout)
        logger.info(f"OTP stored for [{purpose}] -> {identifier}")
        return True

    @classmethod
    def verify_otp(cls, identifier, otp, purpose, max_attempts=5):
        """
        Verifies OTP with retry limiting.
        Returns: (success: bool, message: str)
        """
        otp_key = cls._otp_key(identifier, purpose)
        attempts_key = cls._attempts_key(identifier, purpose)

        stored_otp = cache.get(otp_key)
        attempts = cache.get(attempts_key, 0)

        if stored_otp is None:
            return False, "OTP expired or not found. Please request a new one."

        if attempts >= max_attempts:
            cache.delete(otp_key)
            cache.delete(attempts_key)
            return False, "Too many failed attempts. Please request a new OTP."

        if str(stored_otp) == str(otp).strip():
            cache.delete(otp_key)
            cache.delete(attempts_key)
            return True, "Verification successful."

        attempts += 1
        cache.set(attempts_key, attempts, timeout=300)
        remaining = max_attempts - attempts
        return False, f"Invalid OTP. {remaining} attempt(s) remaining."

    @classmethod
    def delete_otp(cls, identifier, purpose):
        """Manually invalidate an OTP (e.g., after registration complete)."""
        cache.delete(cls._otp_key(identifier, purpose))
        cache.delete(cls._attempts_key(identifier, purpose))


# ==========================================================
# SMS SERVICE - Wappie (India) + SprintSMS (International)
# ==========================================================

class SMSService:
    """
    Smart SMS routing:
      - India (+91)       -> Wappie API
      - International     -> SprintSMS
    Phone validation via the `phonenumbers` library.
    """

    @staticmethod
    def validate_phone(phone_str):
        """
        Parse and validate a phone number.
        Returns: (is_valid: bool, country_code: str, national_number: str)
        """
        try:
            raw = str(phone_str).strip()

            # Auto-fix bare Indian numbers
            if not raw.startswith('+'):
                if len(raw) == 10 and raw.isdigit():
                    raw = f"+91{raw}"
                elif raw.startswith('91') and len(raw) == 12 and raw.isdigit():
                    raw = f"+{raw}"

            parsed = phonenumbers.parse(raw, None)
            
            # If invalid but has a leading zero after country code, try fixing it (e.g. +96605... -> +9665...)
            if not phonenumbers.is_valid_number(parsed):
                national_str = str(parsed.national_number)
                if national_str.startswith('0'):
                    fixed_raw = f"+{parsed.country_code}{national_str[1:]}"
                    parsed = phonenumbers.parse(fixed_raw, None)

            # Use is_possible_number for more flexibility with new prefixes
            if not phonenumbers.is_possible_number(parsed):
                return False, None, None

            country_code = f"+{parsed.country_code}"
            national_number = str(parsed.national_number)
            return True, country_code, national_number

        except Exception as e:
            logger.error(f"Phone validation error for '{phone_str}': {e}")
            return False, None, None

    @classmethod
    def send_otp(cls, phone_str, otp, purpose="login"):
        """
        Main entry point: validates phone and routes to correct gateway.
        - India (+91) -> Wappie
        - International   -> SprintSMS
        """
        is_valid, country_code, national_number = cls.validate_phone(phone_str)
        if not is_valid:
            logger.error(f"Invalid phone number rejected: {phone_str}")
            return False

        if country_code == "+91":
            # Indian DLT Approved Template
            message = (
                f"Your OTP for Signup on Umrah Chalo is {otp}. "
                f"This OTP is valid for 5 minutes. Do not share it with anyone. - Team Umrah Chalo"
            )
            return cls._send_via_wappie(national_number, country_code, message)
        else:
            # International Template
            message = (
                f"Your OTP for Umrah Chalo is {otp}. "
                f"Valid for 5 minutes. Do not share it with anyone. - Team Umrah Chalo"
            )
            full_number = f"{country_code}{national_number}"
            return cls._send_via_sprintsms(full_number, message)

    @staticmethod
    def _send_via_wappie(national_number, country_code, message):
        """
        Sends SMS via Wappie for Indian numbers.
        Checks both HTTP status and response body for real delivery confirmation.
        """
        cfg = settings.SMS_CONFIG['WAPPIE']
        params = {
            "access_token": cfg['ACCESS_TOKEN'],
            "to": national_number,
            "country_code": country_code.replace('+', ''), # Remove '+' for Wappie
            "sender": cfg['SENDER'],
            "service": cfg['SERVICE'],
            "template_id": cfg.get('TEMPLATE_ID'),          # Pass DLT Template ID
            "message": message,
        }
        try:
            response = requests.get(cfg['BASE_URL'], params=params, timeout=10)
            logger.info(f"Wappie response [{response.status_code}]: {response.text}")

            if response.status_code != 200:
                logger.error(f"Wappie HTTP error: {response.status_code} — {response.text}")
                return False

            # Parse body for real delivery confirmation
            try:
                data = response.json()
                # Wappie success often contains 'success', 'accepted', 'ok', or a true 'success' flag
                msg = data.get('message', '').lower()
                status = data.get('status', '').lower()
                if any(k in msg for k in ('success', 'accepted', 'delivered')) or \
                   status in ('success', '1', 'ok') or \
                   data.get('success') is True:
                    logger.info(f"Wappie SMS confirmed sent to {country_code}{national_number}")
                    return True
                else:
                    logger.error(f"Wappie delivery failed (body): {data}")
                    return False
            except Exception:
                # If response is plain text and 200, consider it success
                if response.text and len(response.text) > 0:
                    logger.info(f"Wappie SMS sent (plain text response): {response.text}")
                    return True
                return False

        except requests.exceptions.Timeout:
            logger.error("Wappie API timed out.")
            return False
        except Exception as e:
            logger.error(f"Wappie API exception: {e}")
            return False

    @staticmethod
    def _send_via_sprintsms(full_number, message):
        """
        Sends SMS via SprintSMS for international numbers.
        Forces %20 encoding for spaces to prevent 'blank content' issues.
        """
        import urllib.parse
        cfg = settings.SMS_CONFIG['SPRINTSMS']
        
        params = {
            'api_id': cfg['API_ID'],
            'api_password': cfg['API_PASSWORD'],
            'sms_type': 'O',
            'encoding': 'T',
            'sender_id': cfg['SENDER_ID'],
            'phonenumber': full_number.replace('+', ''),
            'textmessage': message,
        }
        
        # Use quote instead of quote_plus to ensure spaces are %20
        query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        url = f"{cfg['BASE_URL']}?{query_string}"
        
        # Mask password in logs for security
        masked_url = url.replace(cfg['API_PASSWORD'], "********")
        logger.info(f"SprintSMS Debug: Sending Message: '{message}'")
        logger.info(f"SprintSMS Debug: Request URL: {masked_url}")
        
        try:
            response = requests.get(url, timeout=10)
            logger.info(f"SprintSMS response [{response.status_code}] to {full_number}: {response.text}")

            if response.status_code != 200:
                logger.error(f"SprintSMS HTTP error {response.status_code}: {response.text}")
                return False

            data = response.json()
            if data.get('status') == 'S':
                logger.info(f"SprintSMS: Message confirmed sent to {full_number}")
                return True
            else:
                logger.error(f"SprintSMS delivery failed (body): {data}")
                return False

        except Exception as e:
            logger.error(f"SprintSMS API exception: {e}")
            return False
        except requests.exceptions.Timeout:
            logger.error(f"SprintSMS API timed out for {full_number}")
            return False


# ==========================================================
# EMAIL OTP
# ==========================================================

def send_email_otp(to_email, otp, purpose="login"):
    """
    Sends OTP via email using Django's email backend.
    """
    try:
        subject = f"Your OTP for Umrah Chalo - {purpose.replace('_', ' ').capitalize()}"
        message = (
            f"Hello,\n\n"
            f"Your OTP for Umrah Chalo is: {otp}\n\n"
            f"This OTP is valid for 5 minutes. Do not share it with anyone.\n\n"
            f"- Team Umrah Chalo"
        )
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            fail_silently=False,
        )
        logger.info(f"OTP email sent to {to_email} for [{purpose}]")
        return True
    except Exception as e:
        logger.error(f"Email OTP error for {to_email}: {e}")
        return False


# ==========================================================
# LEGACY WRAPPERS (backward compatibility)
# ==========================================================

def generate_login_otp():
    return OTPService.generate_otp()

def send_sms_otp(to_phone, otp, purpose="login"):
    return SMSService.send_otp(to_phone, otp, purpose)
