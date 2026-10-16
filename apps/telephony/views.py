# apps/telephony/views.py

import logging
from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions, viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from datetime import timedelta
from django.utils import timezone
from apps.authentication.models import ServiceProviderProfile
from apps.leads.models import Lead
from .models import CallLog, CallSession
from .serializers import CallLogSerializer
from .utils import format_e164, parse_custom_field
from .services import ExotelService

logger = logging.getLogger(__name__)


class InitiateCallSessionView(APIView):
    """
    API called when a pilgrim taps 'Call Partner' on the website or mobile app.
    Creates a 15-minute call session matching the pilgrim's phone to the provider,
    and returns a smart tel: URI with pause tones (tel:080XXXXX,,33#) that auto-dials
    the provider extension without requiring manual typing.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        provider_id = request.data.get('provider_id')
        package_id = request.data.get('package_id')
        pilgrim_phone = request.data.get('pilgrim_phone', '').strip()

        if not provider_id or not str(provider_id).strip().isdigit():
            return Response({'error': 'A valid numeric provider_id is required'}, status=400)

        provider = ServiceProviderProfile.objects.filter(id=int(provider_id)).select_related('user').first()
        if not provider:
            return Response({'error': f'Provider with id {provider_id} not found'}, status=404)

        # If pilgrim is authenticated and phone wasn't passed in payload, use user's phone
        if not pilgrim_phone and request.user.is_authenticated:
            pilgrim_phone = getattr(request.user, 'phone', '') or getattr(request.user, 'mobile_number', '') or ''
            if not pilgrim_phone and hasattr(request.user, 'profile'):
                pilgrim_phone = getattr(request.user.profile, 'phone', '') or getattr(request.user.profile, 'mobile_number', '') or ''

        clean_phone = format_e164(pilgrim_phone) if pilgrim_phone else ''
        provider_code = str(provider.id)
        expires_at = timezone.now() + timedelta(minutes=15)

        # Auto-create Lead record for the provider when pilgrim initiates call
        created_lead = None
        if request.user.is_authenticated:
            try:
                from apps.leads.models import Lead
                from apps.packages.models import Package

                pkg_obj = None
                if package_id and str(package_id).strip().isdigit():
                    pkg_obj = Package.objects.filter(id=int(package_id)).first()

                created_lead = Lead.objects.create(
                    user=request.user,
                    service_provider=provider,
                    package=pkg_obj,
                    lead_type='contact_view',
                    status='pending',
                    full_name=request.user.get_full_name() or request.user.username or 'Pilgrim Caller',
                    phone=clean_phone or getattr(request.user, 'phone', '') or 'N/A',
                    email=getattr(request.user, 'email', '') or '',
                    special_requirements=f"Pilgrim initiated call to {provider.business_name} via Exotel Telephony",
                    source='exotel_click_to_call'
                )
                from apps.leads.models import LeadDistribution
                LeadDistribution.objects.get_or_create(lead=created_lead, provider=provider, defaults={'status': 'sent'})
            except Exception as e:
                logger.warning(f"Could not auto-create lead on call session: {e}")

        session = CallSession.objects.create(
            pilgrim_phone=clean_phone,
            provider=provider,
            package_id=int(package_id) if package_id and str(package_id).strip().isdigit() else None,
            lead=created_lead,
            session_code=provider_code,
            is_active=True,
            expires_at=expires_at
        )

        exotel_number = getattr(settings, 'EXOTEL_OUTGOING_PHONE_NUMBER', '080-472-89252')
        clean_exotel = exotel_number.replace(' ', '').replace('-', '')
        
        # Clean standard tel: URI - no confusing commas, hashes, or extension codes
        # Direct session matching in ExotelConnectWebhookView links caller automatically
        tel_uri = f"tel:{clean_exotel}"

        return Response({
            'status': 'success',
            'session_id': session.id,
            'lead_id': created_lead.id if created_lead else None,
            'provider_id': provider.id,
            'provider_name': provider.business_name or (provider.user.get_full_name() if provider.user else 'Provider'),
            'exotel_number': exotel_number,
            'tel_uri': tel_uri,
            'expires_at': expires_at.isoformat(),
            'message': f'Call session established. Tap to call {exotel_number} to connect directly with {provider.business_name}.'
        }, status=200)


class ExotelConnectWebhookView(APIView):
    """
    Exotel Programmable Connect Applet Dynamic URL Webhook.
    Exotel issues a GET request with query parameters when a pilgrim calls.
    Plays greeting and routes directly to the service provider.
    Logs pilgrim's original phone number and call details.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        query_params = request.GET.dict()
        logger.info(f"Received Exotel Connect request: {query_params}")

        call_sid = query_params.get('CallSid', '').strip()
        call_from = query_params.get('CallFrom') or query_params.get('From', '')
        call_to = query_params.get('CallTo') or query_params.get('To', '')
        direction = query_params.get('Direction', 'incoming')
        raw_digits = query_params.get('digits', '')
        custom_field = query_params.get('CustomField', '').strip()
        flow_id = query_params.get('flow_id', '')
        param_provider_id = query_params.get('provider_id') or query_params.get('provider')

        # Clean digits (trim quotes as specified in Exotel doc)
        digits = raw_digits.strip('"').strip() if raw_digits else ''

        destination_numbers = []
        matched_provider = None
        matched_lead = None
        matched_package = None

        # 1. Check direct query parameter ?provider_id=X
        if param_provider_id:
            try:
                p_id = int(param_provider_id)
                provider = ServiceProviderProfile.objects.filter(id=p_id).select_related('user').first()
                if provider:
                    matched_provider = provider
                    phone = provider.business_phone or (provider.user.phone if provider.user else '')
                    formatted = format_e164(phone)
                    if formatted:
                        destination_numbers.append(formatted)
            except Exception as e:
                logger.error(f"Error resolving provider from query param: {e}")

        # 2. Check CustomField (Direct Phone / Provider ID / Lead ID)
        if not destination_numbers and custom_field:
            custom_data = parse_custom_field(custom_field)
            
            if 'phone' in custom_data:
                formatted = format_e164(custom_data['phone'])
                if formatted:
                    destination_numbers.append(formatted)

            elif 'provider_id' in custom_data:
                try:
                    p_id = int(custom_data['provider_id'])
                    provider = ServiceProviderProfile.objects.filter(id=p_id).select_related('user').first()
                    if provider:
                        matched_provider = provider
                        phone = provider.business_phone or (provider.user.phone if provider.user else '')
                        formatted = format_e164(phone)
                        if formatted:
                            destination_numbers.append(formatted)
                except Exception as e:
                    logger.error(f"Error resolving provider from CustomField: {e}")

            elif 'lead_id' in custom_data:
                try:
                    l_id = int(custom_data['lead_id'])
                    lead = Lead.objects.filter(id=l_id).first()
                    if lead:
                        matched_lead = lead
                        lead_prov = getattr(lead, 'service_provider', None) or getattr(lead, 'assigned_provider', None)
                        if lead_prov:
                            matched_provider = lead_prov
                            phone = lead_prov.business_phone or (lead_prov.user.phone if lead_prov.user else '')
                            formatted = format_e164(phone)
                            if formatted:
                                destination_numbers.append(formatted)
                except Exception as e:
                    logger.error(f"Error resolving lead from CustomField: {e}")

        # 3. Check IVR Digits / Provider Code (dialed manually or auto-sent via DTMF ,33#)
        if not destination_numbers and digits:
            if digits.isdigit():
                d_int = int(digits)
                prov = ServiceProviderProfile.objects.filter(id=d_int).select_related('user').first()
                if not prov and d_int > 1000:
                    prov = ServiceProviderProfile.objects.filter(id=d_int - 1000).select_related('user').first()
                if prov:
                    matched_provider = prov
                    phone = prov.business_phone or (prov.user.phone if prov.user else '')
                    formatted = format_e164(phone)
                    if formatted:
                        destination_numbers.append(formatted)

            # Department routing fallback (e.g. 1 for Umrah, 2 for Visa)
            if not destination_numbers:
                ivr_routing = getattr(settings, 'EXOTEL_IVR_ROUTING', {})
                if digits in ivr_routing:
                    dest = format_e164(ivr_routing[digits])
                    if dest:
                        destination_numbers.append(dest)

        # 4. Check CallSession (Click-to-Call session created from website/app)
        if not destination_numbers and call_from:
            clean_from = call_from.replace('+91', '').lstrip('0')[-10:]
            if len(clean_from) == 10:
                recent_session = CallSession.objects.filter(
                    pilgrim_phone__icontains=clean_from,
                    is_active=True,
                    expires_at__gte=timezone.now()
                ).select_related('provider', 'provider__user').order_by('-created_at').first()
                if recent_session and recent_session.provider:
                    matched_provider = recent_session.provider
                    matched_package = recent_session.package
                    if recent_session.lead:
                        matched_lead = recent_session.lead
                    phone = matched_provider.business_phone or (matched_provider.user.phone if matched_provider.user else '')
                    formatted = format_e164(phone)
                    if formatted:
                        destination_numbers.append(formatted)
                        # Atomic single-use consumption: deactivate session to prevent stale reuse
                        recent_session.is_active = False
                        recent_session.save(update_fields=['is_active'])

        # 5. Check Caller's Phone (CallFrom) matching an active Lead
        if not destination_numbers and call_from:
            clean_from = call_from.replace('+91', '').lstrip('0')[-10:]
            if len(clean_from) == 10:
                recent_lead = Lead.objects.filter(phone__icontains=clean_from).order_by('-created_at').first()
                if recent_lead:
                    matched_lead = recent_lead
                    lead_prov = getattr(recent_lead, 'service_provider', None) or getattr(recent_lead, 'assigned_provider', None)
                    if lead_prov:
                        matched_provider = lead_prov
                        phone = lead_prov.business_phone or (lead_prov.user.phone if lead_prov.user else '')
                        formatted = format_e164(phone)
                        if formatted:
                            destination_numbers.append(formatted)

        # 6. Umrah Chalo Support Team Fallback
        # If an agent is matched, destination_numbers has [agent_phone].
        # In Exotel, destination.numbers is an array dialed sequentially.
        # When an agent does not receive the call (timeout or busy), Exotel automatically dials
        # the next number: the Umrah Chalo Support Team (+919760316409)!
        default_support = getattr(settings, 'EXOTEL_DEFAULT_SUPPORT_NUMBER', '+919760316409')
        formatted_default = format_e164(default_support) or "+919760316409"
        if formatted_default and formatted_default not in destination_numbers:
            destination_numbers.append(formatted_default)

        # Greeting spoken to caller/both before connecting to the provider
        greeting_text = getattr(
            settings,
            'EXOTEL_CALL_GREETING',
            "Welcome to Umrah Chalo. Connecting your call to the service provider, please wait."
        )

        # If sequential dialing (Agent -> Support fallback), use 25s agent ring timeout
        ring_duration = (
            getattr(settings, 'EXOTEL_AGENT_RINGING_DURATION', 25)
            if len(destination_numbers) > 1
            else getattr(settings, 'EXOTEL_MAX_RINGING_DURATION', 45)
        )

        response_payload = {
            "fetch_after_attempt": False,
            "destination": {
                "numbers": destination_numbers
            },
            "record": getattr(settings, 'EXOTEL_RECORD_CALLS', True),
            "recording_channels": getattr(settings, 'EXOTEL_RECORDING_CHANNELS', "dual"),
            "max_ringing_duration": ring_duration,
            "max_conversation_duration": getattr(settings, 'EXOTEL_MAX_CONVERSATION_DURATION', 3600),
            "music_on_hold": {
                "type": getattr(settings, 'EXOTEL_MUSIC_ON_HOLD_TYPE', "operator_tone")
            },
            "start_call_playback": {
                "playback_to": "both",
                "type": "text",
                "value": greeting_text
            }
        }

        # Optional Outgoing ExoPhone
        outgoing_number = getattr(settings, 'EXOTEL_OUTGOING_PHONE_NUMBER', None)
        if outgoing_number:
            response_payload["outgoing_phone_number"] = format_e164(outgoing_number)

        # Passthrough Event URL for call end tracking
        try:
            event_url = request.build_absolute_uri(reverse('exotel-event'))
            response_payload["dial_passthru_event_url"] = event_url
        except Exception:
            pass

        # Record Initial Call Log with original pilgrim number
        if call_sid:
            try:
                CallLog.objects.update_or_create(
                    call_sid=call_sid,
                    defaults={
                        'call_from': call_from,
                        'call_to': call_to,
                        'direction': direction,
                        'destination_numbers': destination_numbers,
                        'dialed_number': destination_numbers[0] if destination_numbers else '',
                        'digits_pressed': digits,
                        'custom_field': custom_field,
                        'flow_id': flow_id,
                        'provider': matched_provider,
                        'lead': matched_lead,
                        'package': matched_package,
                        'status': 'initiated',
                        'raw_connect_payload': query_params,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to record CallLog for CallSid {call_sid}: {e}")

        return JsonResponse(response_payload, status=200)


class ExotelFallbackWebhookView(APIView):
    """
    Exotel Fallback Dynamic URL Webhook.
    Called by Exotel if the primary connect webhook times out or encounters an issue.
    Returns an instant (< 5ms) JSON response routing the caller directly to the
    UmrahChalo Central Support Team (080-472-89252), ensuring zero dropped calls.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        query_params = request.GET.dict()
        logger.warning(f"Exotel Fallback webhook invoked: {query_params}")

        call_sid = query_params.get('CallSid', '').strip()
        call_from = query_params.get('CallFrom') or query_params.get('From', '')
        call_to = query_params.get('CallTo') or query_params.get('To', '')

        default_support = getattr(settings, 'EXOTEL_DEFAULT_SUPPORT_NUMBER', '+919760316409')
        formatted_default = format_e164(default_support) or "+919760316409"

        response_payload = {
            "fetch_after_attempt": False,
            "destination": {
                "numbers": [formatted_default]
            },
            "record": getattr(settings, 'EXOTEL_RECORD_CALLS', True),
            "recording_channels": getattr(settings, 'EXOTEL_RECORDING_CHANNELS', "dual"),
            "max_ringing_duration": getattr(settings, 'EXOTEL_MAX_RINGING_DURATION', 45),
            "max_conversation_duration": getattr(settings, 'EXOTEL_MAX_CONVERSATION_DURATION', 3600),
            "music_on_hold": {
                "type": getattr(settings, 'EXOTEL_MUSIC_ON_HOLD_TYPE', "operator_tone")
            },
            "start_call_playback": {
                "playback_to": "both",
                "type": "text",
                "value": "Welcome to Umrah Chalo. Connecting you to customer support, please wait."
            }
        }

        try:
            event_url = request.build_absolute_uri(reverse('exotel-event'))
            response_payload["dial_passthru_event_url"] = event_url
        except Exception:
            pass

        if call_sid:
            try:
                CallLog.objects.update_or_create(
                    call_sid=call_sid,
                    defaults={
                        'call_from': call_from,
                        'call_to': call_to,
                        'dialed_number': formatted_default,
                        'status': 'initiated',
                        'notes': 'Routed via Exotel Fallback Webhook to Support',
                        'raw_connect_payload': query_params,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to record fallback CallLog: {e}")

        return JsonResponse(response_payload, status=200)

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class ExotelEventWebhookView(APIView):
    """
    Exotel event and status callback webhook.
    Tracks received calls (completed), missed calls (no-answer, busy), and cut calls (client-hangup).
    Preserves original pilgrim phone number and links call recording URL.
    Supports both JSON and form-encoded payloads from Exotel StatusCallback.
    """
    permission_classes = [permissions.AllowAny]

    def _process_event(self, request):
        # 1. Extract payload safely from DRF request.data or form/GET query params
        data = {}
        if hasattr(request, 'data') and request.data:
            if hasattr(request.data, 'dict'):
                data = request.data.dict()
            elif isinstance(request.data, dict):
                data = dict(request.data)
        if not data:
            data = request.POST.dict() if request.method == 'POST' else request.GET.dict()

        logger.info(f"Received Exotel event callback: {data}")

        # 2. Support nested {"Call": {...}} response structure
        if 'Call' in data and isinstance(data['Call'], dict):
            for k, v in data['Call'].items():
                if k not in data or not data[k]:
                    data[k] = v

        call_sid = (data.get('CallSid') or data.get('Sid') or '').strip()
        if not call_sid:
            return JsonResponse({"status": "ignored", "reason": "No CallSid provided"}, status=200)

        dial_status = data.get('DialCallStatus') or data.get('Status')
        dial_duration = data.get('DialCallDuration') or data.get('CallDuration') or data.get('Duration')
        recording_url = data.get('RecordingUrl') or data.get('recording_url')
        call_type = data.get('CallType') or data.get('call_type')
        dial_whom = data.get('DialWhomNumber') or data.get('DialWhom') or data.get('PhoneNumber')
        custom_field = data.get('CustomField') or data.get('custom_field', '')

        # Determine normalized status
        normalized_status = None
        if call_type == 'client-hangup':
            normalized_status = 'client-hangup'
        elif dial_status:
            normalized_status = str(dial_status).lower()
        elif call_type:
            normalized_status = str(call_type).lower()

        # Parse duration
        duration_sec = 0
        if dial_duration:
            try:
                duration_sec = int(float(dial_duration))
            except (ValueError, TypeError):
                duration_sec = 0

        call_log = CallLog.objects.filter(call_sid=call_sid).first()
        if call_log:
            if normalized_status:
                call_log.status = normalized_status
            if duration_sec > 0:
                call_log.duration = duration_sec
            if dial_whom:
                call_log.dialed_number = dial_whom
            if recording_url:
                call_log.recording_url = recording_url
            if call_type:
                call_log.call_type = call_type
            if custom_field and not call_log.custom_field:
                call_log.custom_field = custom_field
            call_log.raw_event_payload = data
            call_log.save()
            logger.info(f"Updated CallLog {call_sid} to status '{normalized_status}' with duration {duration_sec}s")
        else:
            try:
                # Attempt to resolve provider/lead from CustomField if available
                matched_prov = None
                matched_ld = None
                if custom_field:
                    parsed_cf = parse_custom_field(custom_field)
                    if 'provider_id' in parsed_cf:
                        matched_prov = ServiceProviderProfile.objects.filter(id=parsed_cf['provider_id']).first()
                    if 'lead_id' in parsed_cf:
                        matched_ld = Lead.objects.filter(id=parsed_cf['lead_id']).first()

                CallLog.objects.create(
                    call_sid=call_sid,
                    call_from=data.get('CallFrom') or data.get('From', ''),
                    call_to=data.get('CallTo') or data.get('To', ''),
                    direction=data.get('Direction', 'outbound-api'),
                    status=normalized_status or 'completed',
                    duration=duration_sec,
                    recording_url=recording_url,
                    call_type=call_type or '',
                    dialed_number=dial_whom or '',
                    custom_field=custom_field,
                    provider=matched_prov,
                    lead=matched_ld,
                    raw_event_payload=data
                )
            except Exception as e:
                logger.error(f"Failed to create CallLog from event: {e}")

        return JsonResponse({"status": "success", "message": "Event processed"}, status=200)

    def get(self, request, *args, **kwargs):
        return self._process_event(request)

    def post(self, request, *args, **kwargs):
        return self._process_event(request)


class OutboundCallConnectView(APIView):
    """
    API to initiate an outbound two-legged call via Exotel's Connect API:
    POST /v1/Accounts/{account_sid}/Calls/connect.json

    Flow:
    1. Exotel dials the 'From' number first (e.g. Service Provider / Agent).
    2. Once answered, Exotel immediately dials the 'To' number (e.g. Pilgrim / Lead).
    3. Both parties are bridged together into a recorded call.
    4. Neither party sees each other's private phone number; both see the ExoPhone virtual number.

    Accepted Parameters:
    - lead_id (int, optional): Auto-resolves Provider, Pilgrim phone, and Package from the lead.
    - provider_id (int, optional): Specify provider if admin is initiating the call.
    - package_id (int, optional): Associated package.
    - from_phone (str, optional): Custom first phone number (required if not provider user).
    - to_phone (str, optional): Custom destination phone number (required if no lead_id).
    - caller_id (str, optional): ExoPhone virtual number override.
    - time_limit (int, optional): Max conversation time in seconds (default 3600).
    - timeout (int, optional): Ring timeout in seconds (default 45).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        data = request.data

        lead_id = data.get('lead_id')
        provider_id = data.get('provider_id')
        package_id = data.get('package_id')
        from_phone = str(data.get('from_phone', '')).strip()
        to_phone = str(data.get('to_phone', '')).strip()
        caller_id = data.get('caller_id')
        custom_field = data.get('custom_field')
        time_limit = data.get('time_limit')
        timeout = data.get('timeout')

        matched_lead = None
        matched_provider = None
        matched_package = None

        # 1. Resolve Lead if lead_id is provided
        if lead_id and str(lead_id).strip().isdigit():
            try:
                matched_lead = Lead.objects.select_related('service_provider', 'package').get(id=int(lead_id))
                if not to_phone:
                    to_phone = matched_lead.phone
                if not matched_package and matched_lead.package:
                    matched_package = matched_lead.package
                if not matched_provider and matched_lead.service_provider:
                    matched_provider = matched_lead.service_provider
            except Lead.DoesNotExist:
                return Response({'error': f"Lead with id {lead_id} does not exist."}, status=404)

        # 2. Resolve Package if package_id is provided
        if package_id and str(package_id).strip().isdigit() and not matched_package:
            try:
                from apps.packages.models import Package
                matched_package = Package.objects.filter(id=int(package_id)).first()
            except Exception:
                pass

        # 3. Resolve Provider
        if hasattr(user, 'service_provider_profile'):
            matched_provider = user.service_provider_profile
            if not from_phone:
                from_phone = matched_provider.business_phone or (user.phone if user.phone else '')
        elif provider_id and str(provider_id).strip().isdigit():
            try:
                matched_provider = ServiceProviderProfile.objects.select_related('user').get(id=int(provider_id))
                if not from_phone:
                    from_phone = matched_provider.business_phone or (matched_provider.user.phone if matched_provider.user else '')
            except ServiceProviderProfile.DoesNotExist:
                return Response({'error': f"Provider with id {provider_id} does not exist."}, status=404)

        is_admin = user.is_staff or getattr(user, 'user_type', None) in ['admin', 'super_admin']
        
        # 4. If Pilgrim requested a callback
        if not is_admin and not hasattr(user, 'service_provider_profile'):
            if not to_phone:
                to_phone = getattr(user, 'phone', '') or ''
            if not from_phone and matched_provider:
                from_phone = matched_provider.business_phone or (matched_provider.user.phone if matched_provider.user else '')

        if not from_phone:
            return Response({'error': "Missing 'from_phone' (Agent/Provider phone called first)."}, status=400)
        if not to_phone:
            return Response({'error': "Missing 'to_phone' (Customer/Pilgrim phone called second)."}, status=400)

        # 5. Call Exotel Outbound Connect Service
        result = ExotelService.connect_two_numbers(
            from_phone=from_phone,
            to_phone=to_phone,
            caller_id=caller_id,
            provider=matched_provider,
            lead=matched_lead,
            package=matched_package,
            custom_field=custom_field,
            time_limit=time_limit,
            timeout=timeout
        )

        if result.get('success'):
            return Response({
                'status': 'success',
                'message': 'Outbound call initiated. Exotel is ringing the first party now.',
                'call_sid': result.get('call_sid'),
                'call_status': result.get('status'),
                'call_log_id': result.get('call_log_id'),
                'from': format_e164(from_phone),
                'to': format_e164(to_phone),
                'caller_id': ExotelService.sanitize_caller_id(caller_id),
                'details': result.get('details')
            }, status=200)
        else:
            status_code = result.get('status_code', 400)
            if not isinstance(status_code, int) or status_code < 400 or status_code > 599:
                status_code = 400
            return Response({
                'status': 'error',
                'error': result.get('error', 'Failed to initiate outbound call via Exotel.'),
                'details': result.get('details', {})
            }, status=status_code)



from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from .serializers import CallLogSerializer, ProviderCallDirectorySerializer
import uuid


class CallLogViewSet(viewsets.ModelViewSet):
    """
    API for Service Providers & Admins to view and manage incoming Pilgrim call history.
    Supports full CRUD operations, provider-level isolation, search, and directory views.
    """
    serializer_class = CallLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'direction', 'call_type', 'call_outcome', 'provider']
    search_fields = [
        'call_from', 'dialed_number', 'call_sid', 'caller_name', 'notes',
        'provider__business_name', 'provider__business_phone'
    ]
    ordering_fields = ['created_at', 'duration', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return CallLog.objects.none()

        # Super Admin / Staff sees all calls
        if user.is_staff or getattr(user, 'user_type', None) in ['admin', 'super_admin']:
            qs = CallLog.objects.select_related('provider', 'provider__user', 'lead', 'package').all()
            
            # Filter by specific provider ID if passed in query
            provider_id = self.request.query_params.get('provider_id')
            if provider_id and str(provider_id).strip().isdigit():
                qs = qs.filter(provider_id=int(provider_id))
            elif provider_id in ['null', 'none', 'unassigned']:
                qs = qs.filter(provider__isnull=True)
        # Service Provider sees only their calls
        elif hasattr(user, 'service_provider_profile'):
            qs = CallLog.objects.filter(
                provider=user.service_provider_profile
            ).select_related('provider', 'provider__user', 'lead', 'package')
        else:
            return CallLog.objects.none()

        # Category filter: 'received' | 'missed' | 'cut'
        category = self.request.query_params.get('category')
        if category == 'received':
            qs = qs.filter(status='completed')
        elif category == 'missed':
            qs = qs.filter(status__in=['no-answer', 'busy', 'failed', 'canceled', 'incomplete', 'free', 'timeout'])
        elif category == 'cut':
            qs = qs.filter(status='client-hangup')

        # Date range filtering
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        return qs

    def perform_create(self, serializer):
        call_sid = serializer.validated_data.get('call_sid')
        if not call_sid:
            call_sid = f"manual_{uuid.uuid4().hex[:16]}"
        serializer.save(call_sid=call_sid)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        is_admin = user.is_staff or getattr(user, 'user_type', None) in ['admin', 'super_admin']
        
        # Only admins can delete call logs
        if request.method == 'DELETE' and not is_admin:
            self.permission_denied(request, message="Only administrators can delete call logs.")

        # Providers can only view/update their own calls
        if not is_admin and hasattr(user, 'service_provider_profile'):
            if obj.provider_id != user.service_provider_profile.id:
                self.permission_denied(request, message="You do not have permission to access this call log.")

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Return KPI summary for dashboard: total, received, missed, cut calls"""
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Unauthorized'}, status=401)

        is_admin = user.is_staff or getattr(user, 'user_type', None) in ['admin', 'super_admin']
        provider_id = request.query_params.get('provider_id')

        if is_admin:
            base_qs = CallLog.objects.all()
            if provider_id and str(provider_id).strip().isdigit():
                base_qs = base_qs.filter(provider_id=int(provider_id))
            elif provider_id in ['null', 'none', 'unassigned']:
                base_qs = base_qs.filter(provider__isnull=True)
        elif hasattr(user, 'service_provider_profile'):
            base_qs = CallLog.objects.filter(provider=user.service_provider_profile)
        else:
            return Response({'total': 0, 'received': 0, 'missed': 0, 'cut': 0, 'total_duration': 0})

        total = base_qs.count()
        received = base_qs.filter(status='completed').count()
        missed = base_qs.filter(status__in=['no-answer', 'busy', 'failed', 'canceled', 'incomplete', 'free', 'timeout']).count()
        cut = base_qs.filter(status='client-hangup').count()
        total_duration = base_qs.aggregate(t=Coalesce(Sum('duration'), Value(0)))['t']

        mins, secs = divmod(total_duration, 60)
        hours, mins = divmod(mins, 60)
        formatted_talk_time = f"{hours}h {mins}m" if hours > 0 else f"{mins}m {secs}s"

        return Response({
            'total': total,
            'received': received,
            'missed': missed,
            'cut': cut,
            'total_duration': total_duration,
            'formatted_talk_time': formatted_talk_time,
        })

    @action(detail=False, methods=['get'])
    def providers_directory(self, request):
        """
        Admin endpoint to list all Service Providers alongside their call metrics.
        Shows Total Calls, Received Calls, Missed Calls, and Talk Time for each provider.
        """
        user = request.user
        is_admin = user.is_staff or getattr(user, 'user_type', None) in ['admin', 'super_admin']
        if not is_admin:
            return Response({'error': 'Admin permissions required'}, status=403)

        search = request.query_params.get('search', '').strip()
        city = request.query_params.get('city', '').strip()

        qs = ServiceProviderProfile.objects.select_related('user').annotate(
            total_calls=Count('call_logs'),
            received_calls=Count('call_logs', filter=Q(call_logs__status='completed')),
            missed_calls=Count('call_logs', filter=Q(call_logs__status__in=['no-answer', 'busy', 'failed', 'canceled', 'incomplete', 'free', 'timeout'])),
            cut_calls=Count('call_logs', filter=Q(call_logs__status='client-hangup')),
            total_talk_time=Coalesce(Sum('call_logs__duration'), Value(0))
        )

        if search:
            qs = qs.filter(
                Q(business_name__icontains=search) |
                Q(business_phone__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__email__icontains=search)
            )

        if city:
            qs = qs.filter(business_city__icontains=city)

        sort_by = request.query_params.get('ordering', '-total_calls')
        allowed_sorts = [
            'total_calls', '-total_calls',
            'received_calls', '-received_calls',
            'missed_calls', '-missed_calls',
            'business_name', '-business_name',
            'created_at', '-created_at'
        ]
        if sort_by in allowed_sorts:
            qs = qs.order_by(sort_by)
        else:
            qs = qs.order_by('-total_calls', '-id')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = ProviderCallDirectorySerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProviderCallDirectorySerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

