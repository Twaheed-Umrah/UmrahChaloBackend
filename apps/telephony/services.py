# apps/telephony/services.py

import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings
from .models import CallLog
from .utils import format_e164

logger = logging.getLogger(__name__)


class ExotelService:
    """
    Service for integrating with Exotel Telephony Cloud APIs.
    Handles Outbound Connect (Connecting two phone numbers), Call status inquiries,
    and call logging.
    """

    @classmethod
    def get_credentials(cls) -> Dict[str, str]:
        """Fetch Exotel API credentials and configuration from settings"""
        return {
            'account_sid': getattr(settings, 'EXOTEL_ACCOUNT_SID', '').strip(),
            'api_key': getattr(settings, 'EXOTEL_API_KEY', '').strip(),
            'api_token': getattr(settings, 'EXOTEL_API_TOKEN', '').strip(),
            'subdomain': getattr(settings, 'EXOTEL_SUBDOMAIN', 'api.exotel.com').strip() or 'api.exotel.com',
            'outgoing_phone': getattr(settings, 'EXOTEL_OUTGOING_PHONE_NUMBER', '080-472-89252').strip(),
            'status_callback': getattr(
                settings,
                'EXOTEL_STATUS_CALLBACK_URL',
                'https://umrahapi.umrachalo.com/api/v1/telephony/exotel/event/'
            ).strip()
        }

    @classmethod
    def sanitize_caller_id(cls, caller_id: Optional[str] = None) -> str:
        """
        Sanitize ExoPhone CallerId for Exotel API.
        Removes spaces, dashes, parentheses and leading plus.
        Example: '080-472-89252' -> '08047289252'
        """
        raw_number = caller_id or getattr(settings, 'EXOTEL_OUTGOING_PHONE_NUMBER', '080-472-89252')
        cleaned = str(raw_number).replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').strip()
        return cleaned

    @classmethod
    def connect_two_numbers(
        cls,
        from_phone: str,
        to_phone: str,
        caller_id: Optional[str] = None,
        provider=None,
        lead=None,
        package=None,
        custom_field: Optional[str] = None,
        time_limit: Optional[int] = None,
        timeout: Optional[int] = None,
        wait_url: Optional[str] = None,
        record: Optional[bool] = None,
        recording_channels: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate an outbound bridge call connecting two phone numbers.
        Exotel dials the 'From' number first (e.g. Service Provider / Agent).
        Once they answer, Exotel immediately dials the 'To' number (e.g. Pilgrim / Customer)
        and bridges both legs together.

        API Specification:
        POST https://<subdomain>/v1/Accounts/<account_sid>/Calls/connect.json
        Headers: Content-Type: application/x-www-form-urlencoded
        Auth: Basic Auth (API_KEY, API_TOKEN)

        :param from_phone: Phone number to call first (E.164, e.g. +919900XXXXXX)
        :param to_phone: Destination phone number (E.164, e.g. +918800XXXXXX)
        :param caller_id: ExoPhone virtual number to display
        :param provider: ServiceProviderProfile model instance (optional)
        :param lead: Lead model instance (optional)
        :param package: Package model instance (optional)
        :param custom_field: Metadata string (max 128 chars) passed to StatusCallback
        :param time_limit: Max call duration in seconds (default 3600)
        :param timeout: Ring timeout in seconds for each leg (default 45)
        :param wait_url: Audio URL (WAV/MP3) played while waiting for 2nd leg
        :param record: Whether to record the call (default True)
        :param recording_channels: 'single' or 'dual' (default 'dual')
        :return: Dict with success status, call_sid, and data/error
        """
        creds = cls.get_credentials()
        account_sid = creds['account_sid']
        api_key = creds['api_key']
        api_token = creds['api_token']
        subdomain = creds['subdomain']

        if not account_sid or not api_key or not api_token:
            logger.error("Exotel API credentials are not configured in settings/environment.")
            return {
                'success': False,
                'error': 'Exotel credentials (EXOTEL_ACCOUNT_SID, EXOTEL_API_KEY, EXOTEL_API_TOKEN) are not configured.'
            }

        # 1. Format and validate phone numbers
        from_e164 = format_e164(from_phone)
        to_e164 = format_e164(to_phone)

        if not from_e164:
            return {'success': False, 'error': f"Invalid 'From' phone number: {from_phone}"}
        if not to_e164:
            return {'success': False, 'error': f"Invalid 'To' phone number: {to_phone}"}

        # 2. Prepare CallerId
        clean_caller_id = cls.sanitize_caller_id(caller_id or creds['outgoing_phone'])

        # 3. Build CustomField if not explicitly provided
        metadata_parts = []
        if custom_field:
            metadata_parts.append(str(custom_field).strip())
        else:
            if lead:
                metadata_parts.append(f"lead_id={lead.id}")
            if provider:
                metadata_parts.append(f"provider_id={provider.id}")
            if package:
                metadata_parts.append(f"package_id={package.id}")
        
        final_custom_field = "&".join(metadata_parts)[:128] if metadata_parts else ""

        # 4. Build API endpoint URL (CRITICAL: append .json to prevent XML output)
        url = f"https://{subdomain}/v1/Accounts/{account_sid}/Calls/connect.json"

        # 5. Build Form Payload (application/x-www-form-urlencoded)
        is_record = record if record is not None else getattr(settings, 'EXOTEL_RECORD_CALLS', True)
        rec_channels = recording_channels or getattr(settings, 'EXOTEL_RECORDING_CHANNELS', 'dual')
        max_duration = time_limit or getattr(settings, 'EXOTEL_MAX_CONVERSATION_DURATION', 3600)
        ring_timeout = timeout or getattr(settings, 'EXOTEL_MAX_RINGING_DURATION', 45)

        payload = {
            'From': from_e164,
            'To': to_e164,
            'CallerId': clean_caller_id,
            'CallType': 'trans',
            'TimeLimit': max_duration,
            'TimeOut': ring_timeout,
            'Record': 'true' if is_record else 'false',
            'RecordingChannels': rec_channels,
            'RecordingFormat': 'mp3',
            'StatusCallback': creds['status_callback'],
            'StatusCallbackEvents[0]': 'terminal',
            'StatusCallbackEvents[1]': 'answered',
            'StatusCallbackContentType': 'application/json',
        }

        if final_custom_field:
            payload['CustomField'] = final_custom_field

        if wait_url:
            payload['WaitUrl'] = wait_url

        logger.info(
            f"Initiating Exotel Outbound Connect: From={from_e164} -> To={to_e164} "
            f"CallerId={clean_caller_id} URL={url}"
        )

        # 6. Execute HTTP POST request with Basic Auth
        try:
            response = requests.post(
                url,
                data=payload,  # Form-encoded as required by Exotel
                auth=(api_key, api_token),
                timeout=20
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request to Exotel Connect API failed: {e}")
            return {
                'success': False,
                'error': f"Failed to connect to Exotel server: {str(e)}"
            }

        # 7. Parse Response
        try:
            res_json = response.json()
        except Exception:
            logger.error(f"Failed to parse Exotel response as JSON: {response.text}")
            return {
                'success': False,
                'error': f"Exotel returned non-JSON response (HTTP {response.status_code})",
                'raw_response': response.text
            }

        if response.status_code in [200, 201]:
            call_data = res_json.get('Call', {})
            call_sid = call_data.get('Sid')
            call_status = call_data.get('Status', 'in-progress')

            logger.info(f"Exotel Outbound Call connected successfully. CallSid={call_sid}, Status={call_status}")

            # Persist CallLog in Database
            call_log = None
            if call_sid:
                try:
                    call_log, _ = CallLog.objects.update_or_create(
                        call_sid=call_sid,
                        defaults={
                            'call_from': from_e164,
                            'call_to': to_e164,
                            'direction': 'outbound-api',
                            'destination_numbers': [to_e164],
                            'dialed_number': to_e164,
                            'provider': provider,
                            'lead': lead,
                            'package': package,
                            'custom_field': final_custom_field,
                            'status': call_status.lower() if call_status else 'in-progress',
                            'raw_connect_payload': res_json,
                            'notes': f"Outbound call bridged by Exotel ({from_e164} -> {to_e164})"
                        }
                    )
                except Exception as e:
                    logger.error(f"Error saving CallLog for CallSid {call_sid}: {e}")

            return {
                'success': True,
                'call_sid': call_sid,
                'status': call_status,
                'call_log_id': call_log.id if call_log else None,
                'details': call_data
            }

        else:
            # Handle Error Response (RestException)
            rest_exception = res_json.get('RestException', {})
            error_status = rest_exception.get('Status', response.status_code)
            error_message = rest_exception.get('Message', 'Unknown Exotel API error')

            logger.error(
                f"Exotel Outbound Connect failed: HTTP {response.status_code} | "
                f"Code: {error_status} | Message: {error_message}"
            )

            return {
                'success': False,
                'status_code': response.status_code,
                'error_code': error_status,
                'error': error_message,
                'details': rest_exception
            }

    @classmethod
    def get_call_details(cls, call_sid: str) -> Dict[str, Any]:
        """
        Fetch call status and recording URL directly from Exotel Call Details API.
        GET https://<subdomain>/v1/Accounts/<account_sid>/Calls/<call_sid>.json
        """
        creds = cls.get_credentials()
        account_sid = creds['account_sid']
        api_key = creds['api_key']
        api_token = creds['api_token']
        subdomain = creds['subdomain']

        if not account_sid or not api_key or not api_token or not call_sid:
            return {'success': False, 'error': 'Missing parameters or Exotel credentials.'}

        url = f"https://{subdomain}/v1/Accounts/{account_sid}/Calls/{call_sid}.json"

        try:
            response = requests.get(url, auth=(api_key, api_token), timeout=15)
            if response.status_code == 200:
                data = response.json().get('Call', {})
                return {'success': True, 'call': data}
            else:
                return {'success': False, 'error': f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}
