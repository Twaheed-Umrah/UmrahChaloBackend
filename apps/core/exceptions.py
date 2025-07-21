from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.http import Http404
import logging

logger = logging.getLogger(__name__)

class CustomAPIException(Exception):
    """
    Custom API exception base class
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'A server error occurred.'
    default_code = 'error'

    def __init__(self, detail=None, code=None, status_code=None):
        if detail is None:
            detail = self.default_detail
        if code is None:
            code = self.default_code
        if status_code is not None:
            self.status_code = status_code
        
        self.detail = detail
        self.code = code

class ValidationError(CustomAPIException):
    """
    Custom validation error
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid input.'
    default_code = 'validation_error'

class AuthenticationError(CustomAPIException):
    """
    Custom authentication error
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Authentication credentials were not provided.'
    default_code = 'authentication_error'

class PermissionError(CustomAPIException):
    """
    Custom permission error
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'You do not have permission to perform this action.'
    default_code = 'permission_error'

class NotFoundError(CustomAPIException):
    """
    Custom not found error
    """
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'The requested resource was not found.'
    default_code = 'not_found_error'

class ConflictError(CustomAPIException):
    """
    Custom conflict error
    """
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'The request could not be processed due to a conflict.'
    default_code = 'conflict_error'

class RateLimitError(CustomAPIException):
    """
    Custom rate limit error
    """
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = 'Rate limit exceeded. Please try again later.'
    default_code = 'rate_limit_error'

class ServiceUnavailableError(CustomAPIException):
    """
    Custom service unavailable error
    """
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Service temporarily unavailable. Please try again later.'
    default_code = 'service_unavailable_error'

def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides consistent error responses
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # Log the exception
    logger.error(f"Exception occurred: {exc}", exc_info=True)
    
    # Handle custom exceptions
    if isinstance(exc, CustomAPIException):
        return Response({
            'error': True,
            'code': exc.code,
            'message': exc.detail,
            'status_code': exc.status_code
        }, status=exc.status_code)
    
    # Handle Django validation errors
    if isinstance(exc, ValidationError):
        return Response({
            'error': True,
            'code': 'validation_error',
            'message': 'Validation error occurred',
            'details': exc.message_dict if hasattr(exc, 'message_dict') else str(exc),
            'status_code': status.HTTP_400_BAD_REQUEST
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Handle 404 errors
    if isinstance(exc, Http404):
        return Response({
            'error': True,
            'code': 'not_found',
            'message': 'The requested resource was not found.',
            'status_code': status.HTTP_404_NOT_FOUND
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Handle DRF exceptions
    if response is not None:
        custom_response_data = {
            'error': True,
            'code': getattr(exc, 'default_code', 'error'),
            'message': 'An error occurred',
            'status_code': response.status_code
        }
        
        # Handle field-specific errors
        if hasattr(response, 'data'):
            if isinstance(response.data, dict):
                if 'detail' in response.data:
                    custom_response_data['message'] = response.data['detail']
                elif 'non_field_errors' in response.data:
                    custom_response_data['message'] = response.data['non_field_errors'][0]
                else:
                    custom_response_data['details'] = response.data
                    # Get first error message
                    for field, errors in response.data.items():
                        if isinstance(errors, list) and errors:
                            custom_response_data['message'] = f"{field}: {errors[0]}"
                            break
            elif isinstance(response.data, list):
                custom_response_data['message'] = response.data[0] if response.data else 'An error occurred'
        
        response.data = custom_response_data
    
    return response