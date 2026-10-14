import re
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def format_e164(phone_number: str, default_country_code: str = "+91") -> str:
    """
    Format a phone number into strict E.164 format (+91XXXXXXXXXX) required by Exotel.
    """
    if not phone_number:
        return ""

    cleaned = re.sub(r'[\s\-\(\)\.]', '', str(phone_number).strip())

    if not cleaned:
        return ""

    if cleaned.startswith('+'):
        return cleaned

    if cleaned.startswith('00'):
        return f"+{cleaned[2:]}"

    if cleaned.startswith('0'):
        cleaned = cleaned[1:]

    # 12 digits starting with country code 91
    if len(cleaned) == 12 and cleaned.startswith('91'):
        return f"+{cleaned}"

    # Standard 10 digit Indian number
    if len(cleaned) == 10:
        return f"{default_country_code}{cleaned}"

    if len(cleaned) > 10 and not cleaned.startswith('+'):
        return f"+{cleaned}"

    return f"{default_country_code}{cleaned}"


def parse_custom_field(custom_field: str) -> Dict[str, Any]:
    """
    Parse Exotel's CustomField into structured dictionary.
    Supports JSON strings (e.g. {"provider_id": 12}) or key=value (e.g. provider_id=12)
    or raw numeric ID or phone number.
    """
    result: Dict[str, Any] = {}
    if not custom_field:
        return result

    val = str(custom_field).strip()

    # Try JSON
    if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # Try query string format: key=value&key2=value2
    if '=' in val:
        try:
            parts = val.split('&')
            for part in parts:
                if '=' in part:
                    k, v = part.split('=', 1)
                    result[k.strip()] = v.strip()
            if result:
                return result
        except Exception:
            pass

    # Direct phone or ID
    if val.startswith('+') or (val.isdigit() and len(val) >= 10):
        result['phone'] = val
    elif val.isdigit():
        result['provider_id'] = int(val)
    else:
        result['raw'] = val

    return result
