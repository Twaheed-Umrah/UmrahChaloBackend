from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import login, logout
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.shortcuts import get_object_or_404
from django.db.models import Q
from datetime import timedelta
import uuid
from .models import (
    User, OTPVerification, LoginAttempt, UserSession,
    ServiceProviderProfile, SavedPackage, UserActivity
)
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, OTPLoginSerializer,
    OTPVerificationSerializer, PasswordResetSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer, UserProfileSerializer, RefreshTokenSerializer,
    ServiceProviderProfileSerializer, ServiceProviderRegistrationSerializer,
    ServiceProviderListSerializer, UserActivitySerializer, SavedPackageSerializer,
    LoginAttemptSerializer, UserSessionSerializer, EmailVerificationSerializer,
    PhoneVerificationSerializer, UserManagementSerializer, BulkUserActionSerializer,LocationUpdateSerializer
)
import logging
logger = logging.getLogger(__name__)
from apps.core.utils import send_otp, generate_otp, get_client_ip, get_user_agent
from .utils import send_email_otp,send_sms_otp
from apps.core.pagination import CustomPagination
from apps.core.permissions import IsSuperAdmin, IsProviderOrReadOnly
from apps.notifications.services import NotificationService

# Base Authentication Views
class UserRegistrationView(generics.CreateAPIView):
    """
    API endpoint for user registration
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Log user activity
        try:
            UserActivity.objects.create(
                user=user,
                activity_type='registration',
                description='User registered',
                ip_address=get_client_ip(request),
                metadata={
                    'user_type': user.user_type,
                    'has_location': user.has_location
                }
            )
        except Exception as e:
            print(f"Failed to log activity: {e}")
        try:
                NotificationService.send_welcome_notification(user)
                logger.info(f"Welcome notification sent synchronously to {user.email}")
        except Exception as sync_error:
                 logger.error(f"Failed to send welcome notification synchronously: {sync_error}")
                 
        response_data = {
            'message': 'User registered successfully. Please check your email for verification.',
            'user_id': str(user.id),
            'username': user.username,
            'email': user.email
        }
        
        if user.has_location:
            response_data['location'] = user.get_location_info()

        return Response(response_data, status=status.HTTP_201_CREATED)


class UserLoginView(APIView):
    """
    API endpoint for user login with email/phone and password
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        login_method = serializer.validated_data.get('login_method')  # email or phone

        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)

        # Log login attempt
        LoginAttempt.objects.create(
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True
        )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # Create user session
        UserSession.objects.create(
            user=user,
            session_key=str(uuid.uuid4()),
            device_info=user_agent,
            ip_address=ip_address,
            is_active=True
        )

        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='login',
            description=f'User logged in via {login_method}',
            ip_address=ip_address,
            metadata={'login_method': login_method}
        )

        response_data = {
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': UserProfileSerializer(user).data
        }

        # For pilgrims, check if location update is needed
        if user.user_type == 'pilgrim':
            response_data['location_update_required'] = True
            response_data['message'] += ' Please update your current location.'

        return Response(response_data, status=status.HTTP_200_OK)

class OTPLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get('email')
        phone = serializer.validated_data.get('phone')

        try:
            user = User.objects.get(email=email) if email else User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            purpose='login',
            expires_at=timezone.now() + timedelta(minutes=5)
        )

        if email:
            send_email_otp(email, otp, "login")
        else:
            send_sms_otp(phone, otp)

        return Response({"message": "OTP sent successfully"}, status=status.HTTP_200_OK)


class OTPVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        phone = serializer.validated_data.get("phone")
        otp = serializer.validated_data["otp"]
        purpose = serializer.validated_data["purpose"]

        try:
            user = User.objects.get(email=email) if email else User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        otp_obj = OTPVerification.objects.filter(user=user, otp=otp, purpose=purpose, is_used=False).last()

        if not otp_obj or otp_obj.is_expired():
            return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

        otp_obj.is_used = True
        otp_obj.save()

        # Generate JWT Tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Create Session
        UserSession.objects.create(
            user=user,
            session_key=str(uuid.uuid4()),
            device_info=request.META.get('HTTP_USER_AGENT', ''),
            ip_address=request.META.get('REMOTE_ADDR', '')
        )

        return Response({
            "message": "OTP verified successfully",
            "access_token": access_token,
            "refresh_token": str(refresh),
            'user': UserProfileSerializer(user).data
        }, status=status.HTTP_200_OK)
    
class PasswordResetView(APIView):
    """
    API endpoint to request password reset
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)
        
        # Generate and send OTP
        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            purpose='password_reset',
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        
        send_otp(email, otp, 'password_reset')
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='password_reset_request',
            description='Password reset requested',
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'Password reset OTP sent to your email.'
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    API endpoint to confirm password reset
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        otp_verification = serializer.validated_data['otp_verification']
        new_password = serializer.validated_data['new_password']
        
        # Mark OTP as used
        otp_verification.is_used = True
        otp_verification.save()
        
        # Update password
        user.set_password(new_password)
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='password_reset',
            description='Password reset successfully',
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'Password reset successfully'
        }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    API endpoint to change password
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        new_password = serializer.validated_data['new_password']
        
        user.set_password(new_password)
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='password_change',
            description='Password changed successfully',
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API endpoint to get and update user profile
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # If email is being updated, require verification
        if 'email' in serializer.validated_data:
            new_email = serializer.validated_data['email']
            if new_email != instance.email:
                # Generate and send OTP for email verification
                otp = generate_otp()
                OTPVerification.objects.create(
                    user=instance,
                    otp=otp,
                    purpose='email_verification',
                    expires_at=timezone.now() + timedelta(minutes=10)
                )
                send_otp(new_email, otp, 'email_verification')
                
                return Response({
                    'message': 'Email update initiated. Please verify your new email address.',
                    'new_email': new_email
                }, status=status.HTTP_200_OK)
        
        self.perform_update(serializer)
        
        # Log activity
        UserActivity.objects.create(
            user=instance,
            activity_type='profile_update',
            description='Profile updated',
            ip_address=get_client_ip(request),
            metadata={'updated_fields': list(serializer.validated_data.keys())}
        )
        
        return Response({
            'message': 'Profile updated successfully',
            'user': serializer.data
        }, status=status.HTTP_200_OK)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone

class LocationUpdateView(APIView):
    """
    API endpoint to update user location.
    - Pilgrims can update location multiple times.
    - Providers can update location only once (at profile setup).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LocationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        # Restrict providers to one-time location update
        if user.user_type == 'provider' and user.has_location:
            return Response({
                'error': 'Providers can only set their location once during profile setup.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Update user location
        updated_user = serializer.update_user_location(user)

        # Log location update for pilgrims
        if user.user_type == 'pilgrim':
            UserActivity.objects.create(
                user=user,
                activity_type='location_update',
                description='Pilgrim location updated',
                ip_address=get_client_ip(request),
                metadata={
                    'user_type': user.user_type,
                    'location': {
                        'latitude': float(serializer.validated_data['latitude']),
                        'longitude': float(serializer.validated_data['longitude']),
                        'address': serializer.validated_data.get('address', '')
                    },
                    'timestamp': timezone.now().isoformat()
                }
            )

        return Response({
            'message': 'Location updated successfully.',
            'location': updated_user.get_location_info(),
            'user_type': user.user_type
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except TokenError:
            return Response({'message': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)

        UserSession.objects.filter(user=request.user, is_active=True).update(is_active=False)
        UserActivity.objects.create(
            user=request.user,
            activity_type='logout',
            description='User logged out',
            ip_address=get_client_ip(request)
        )

        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            response.data['message'] = 'Token refreshed successfully'
        return response


# Service Provider Views
class ServiceProviderRegistrationView(generics.CreateAPIView):
    """
    API endpoint for service provider registration
    """
    queryset = ServiceProviderProfile.objects.all()
    serializer_class = ServiceProviderRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.save()
        user = provider.user  # The related user object

        # Log service provider activity
        try:
            UserActivity.objects.create(
                user=user,
                activity_type='registration',
                description='Service provider registered',
                ip_address=get_client_ip(request),
                metadata={
                    'user_type': user.user_type,
                    'has_location': user.has_location
                }
            )
        except Exception as e:
            print(f"Failed to log activity: {e}")

        # Send welcome notification
        try:
                NotificationService.send_welcome_notification(user)
                logger.info(f"Welcome notification sent synchronously to {user.email}")
        except Exception as sync_error:
                 logger.error(f"Failed to send welcome notification synchronously: {sync_error}")

        # Prepare response
        response_data = {
            'message': 'Service provider registered successfully. Please check your email for verification.',
            'provider_id': provider.id,
            'user_id': str(user.id),
            'email': user.email
        }

        if user.has_location:
            response_data['location'] = user.get_location_info()

        return Response(response_data, status=status.HTTP_201_CREATED)


class ServiceProviderListView(generics.ListAPIView):
    """
    API endpoint to list service providers
    """
    serializer_class = ServiceProviderListSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        queryset = ServiceProviderProfile.objects.filter(is_active=True)
        
        # Filter by verification status
        verification_status = self.request.query_params.get('verification_status')
        if verification_status:
            queryset = queryset.filter(verification_status=verification_status)
        
        # Filter by business type
        business_type = self.request.query_params.get('business_type')
        if business_type:
            queryset = queryset.filter(business_type=business_type)
        
        # Filter by city
        city = self.request.query_params.get('city')
        if city:
            queryset = queryset.filter(business_city__icontains=city)
        
        # Filter by state
        state = self.request.query_params.get('state')
        if state:
            queryset = queryset.filter(business_state__icontains=state)
        
        # Search by business name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(business_name__icontains=search) |
                Q(business_description__icontains=search)
            )
        
        # Filter by location proximity (if latitude and longitude provided)
        lat = self.request.query_params.get('latitude')
        lng = self.request.query_params.get('longitude')
        radius = self.request.query_params.get('radius', 50)  # Default 50km radius
        
        if lat and lng:
            # Filter providers within specified radius
            # Note: This is a simple implementation, consider using PostGIS for production
            try:
                lat = float(lat)
                lng = float(lng)
                radius = float(radius)
                
                # Simple bounding box filter (for basic proximity)
                # For more accurate distance calculation, use PostGIS or geopy
                lat_range = radius / 111.0  # Rough conversion of km to degrees
                lng_range = radius / (111.0 * abs(lat))
                
                queryset = queryset.filter(
                    user__latitude__gte=lat - lat_range,
                    user__latitude__lte=lat + lat_range,
                    user__longitude__gte=lng - lng_range,
                    user__longitude__lte=lng + lng_range
                ).exclude(
                    user__latitude__isnull=True,
                    user__longitude__isnull=True
                )
            except (ValueError, TypeError):
                pass  # Ignore invalid coordinates
        
        # Order by featured first, then by rating
        return queryset.order_by('-is_featured', '-average_rating', '-created_at')


class ServiceProviderDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint for retrieving, updating, and deleting the current service provider's profile
    """
    serializer_class = ServiceProviderProfileSerializer
    permission_classes = [IsAuthenticated, IsProviderOrReadOnly]

    def get_object(self):
        """
        Return the ServiceProviderProfile for the currently logged-in user
        """
        return self.request.user.service_provider_profile  # Adjust based on your user model

    def perform_update(self, serializer):
        provider = serializer.save()
        
        UserActivity.objects.create(
            user=provider.user,
            activity_type='profile_update',
            description='Service provider profile updated',
            ip_address=get_client_ip(self.request)
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()
        
        UserActivity.objects.create(
            user=instance.user,
            activity_type='profile_deactivation',
            description='Service provider profile deactivated',
            ip_address=get_client_ip(self.request)
        )
# Activity and Tracking Views
class UserActivityListView(generics.ListAPIView):
    """
    API endpoint to list user activities
    """
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        if self.request.user.is_staff:
            # Admin can see all activities
            queryset = UserActivity.objects.all()
            
            # Filter by user
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)
        else:
            # Regular users can only see their own activities
            queryset = UserActivity.objects.filter(user=self.request.user)
        
        # Filter by activity type
        activity_type = self.request.query_params.get('activity_type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        
        return queryset.order_by('-created_at')


class SavedPackageListCreateView(generics.ListCreateAPIView):
    """
    API endpoint to list and create saved packages
    """
    serializer_class = SavedPackageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        return SavedPackage.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        
        # Log activity
        UserActivity.objects.create(
            user=self.request.user,
            activity_type='package_saved',
            description='Package saved',
            ip_address=get_client_ip(self.request),
            metadata={'package_id': serializer.instance.package.id}
        )


class SavedPackageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint for saved package detail
    """
    serializer_class = SavedPackageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SavedPackage.objects.filter(user=self.request.user)
    
    def perform_destroy(self, instance):
        package_id = instance.package.id
        instance.delete()
        
        # Log activity
        UserActivity.objects.create(
            user=self.request.user,
            activity_type='package_unsaved',
            description='Package removed from saved',
            ip_address=get_client_ip(self.request),
            metadata={'package_id': package_id}
        )


class EmailVerificationView(APIView):
    """
    API endpoint for email verification
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # The validation is handled in the serializer
        user = serializer.validated_data['user']
        user.is_verified = True
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='email_verification',
            description='Email verified successfully',
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'Email verified successfully'
        }, status=status.HTTP_200_OK)


class PhoneVerificationView(APIView):
    """
    API endpoint for phone verification
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PhoneVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # The validation is handled in the serializer
        user = serializer.validated_data['user']
        # Add phone verification logic here
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='phone_verification',
            description='Phone verified successfully',
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'Phone verified successfully'
        }, status=status.HTTP_200_OK)


class UserSessionListView(generics.ListAPIView):
    """
    API endpoint to list user sessions
    """
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user).order_by('-created_at')


class LoginAttemptListView(generics.ListAPIView):
    """
    API endpoint to list login attempts
    """
    serializer_class = LoginAttemptSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return LoginAttempt.objects.all().order_by('-created_at')
        else:
            return LoginAttempt.objects.filter(email=self.request.user.email).order_by('-created_at')


# Admin Views
class ServiceProviderManagementListView(generics.ListAPIView):
    """
    API endpoint for super admin to list all service providers with filtering and search
    """
    serializer_class = ServiceProviderListSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    
    # Define filterable fields
    filterset_fields = {
        'verification_status': ['exact'],
        'business_type': ['exact'],
        'business_state': ['exact'],
        'business_city': ['icontains'],
        'is_active': ['exact'],
        'is_featured': ['exact'],
        'average_rating': ['gte', 'lte'],
        'total_packages': ['gte', 'lte'],
        'created_at': ['date__gte', 'date__lte'],
    }
    
    # Define searchable fields
    search_fields = [
        'business_name',
        'business_email', 
        'user__email',
        'user__username',
        'business_phone',
        'business_city',
        'business_state'
    ]
    
    # Define ordering fields
    ordering_fields = [
        'created_at',
        'business_name',
        'average_rating',
        'total_packages',
        'total_reviews',
        'verification_status'
    ]
    ordering = ['-created_at']  # Default ordering
    
    def get_queryset(self):
        """
        Get all service provider profiles with related user data
        """
        queryset = ServiceProviderProfile.objects.select_related('user').filter(user__user_type="provider")
        
        # Custom filters that aren't handled by django-filter
        
        # Filter by user verification status
        user_is_verified = self.request.query_params.get('user_is_verified')
        if user_is_verified is not None:
            queryset = queryset.filter(user__is_verified=user_is_verified.lower() == 'true')
        
        # Filter by user active status  
        user_is_active = self.request.query_params.get('user_is_active')
        if user_is_active is not None:
            queryset = queryset.filter(user__is_active=user_is_active.lower() == 'true')
            
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
            
        # Filter by rating range
        min_rating = self.request.query_params.get('min_rating')
        max_rating = self.request.query_params.get('max_rating')
        
        if min_rating:
            queryset = queryset.filter(average_rating__gte=min_rating)
        if max_rating:
            queryset = queryset.filter(average_rating__lte=max_rating)
            
        return queryset
    
    def list(self, request, *args, **kwargs):
        """
        Override list method to add custom response data
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Add summary statistics
        total_providers = queryset.count()
        active_providers = queryset.filter(is_active=True).count()
        verified_providers = queryset.filter(verification_status='verified').count()
        featured_providers = queryset.filter(is_featured=True).count()
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            
            # Add summary to paginated response
            response.data['summary'] = {
                'total_providers': total_providers,
                'active_providers': active_providers,
                'verified_providers': verified_providers,
                'featured_providers': featured_providers,
            }
            return response
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'summary': {
                'total_providers': total_providers,
                'active_providers': active_providers,
                'verified_providers': verified_providers,
                'featured_providers': featured_providers,
            }
        })


class ServiceProviderManagementDetailView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for super admin to retrieve and update service provider details
    """
    serializer_class = ServiceProviderProfileSerializer
    permission_classes = [IsSuperAdmin]
    lookup_field = 'id'
    
    def get_queryset(self):
        """
        Get service provider profile with related data
        """
        return ServiceProviderProfile.objects.select_related(
            'user', 'verified_by'
        ).prefetch_related(
            'user__otp_verifications',
            'packages',
            'reviews'
        ).all()
    
    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve to add additional provider statistics
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        # Add additional statistics
        additional_data = {
            'statistics': {
                'total_packages': instance.total_packages,
                'total_leads': instance.total_leads,
                'total_bookings': instance.total_bookings,
                'average_rating': float(instance.average_rating) if instance.average_rating else 0,
                'total_reviews': instance.total_reviews,
                'account_age_days': (timezone.now().date() - instance.created_at.date()).days,
                'last_login': instance.user.last_login,
                'is_email_verified': instance.user.is_verified,
                'profile_completion': self.calculate_profile_completion(instance)
            },
            'verification_info': {
                'status': instance.verification_status,
                'verified_by': instance.verified_by.username if instance.verified_by else None,
                'verified_at': instance.verified_at,
                'verification_notes': instance.verification_notes
            }
        }
        
        response_data = serializer.data
        response_data.update(additional_data)
        
        return Response(response_data)
    
    def calculate_profile_completion(self, instance):
        """
        Calculate profile completion percentage
        """
        required_fields = [
            'business_name', 'business_type', 'business_description',
            'business_email', 'business_phone', 'business_address',
            'business_city', 'business_state', 'business_country'
        ]
        
        completed_fields = 0
        for field in required_fields:
            if getattr(instance, field):
                completed_fields += 1
        
        # Add document fields
        document_fields = [
            'business_logo', 'government_id_document', 
            'gst_certificate', 'trade_license_document'
        ]
        
        for field in document_fields:
            if getattr(instance, field):
                completed_fields += 1
        
        total_fields = len(required_fields) + len(document_fields)
        return round((completed_fields / total_fields) * 100, 2)
    
    def update(self, request, *args, **kwargs):
        """
        Override update to handle admin-specific updates
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Handle verification status updates
        if 'verification_status' in request.data:
            verification_status = request.data.get('verification_status')
            verification_notes = request.data.get('verification_notes', '')

            if verification_status in ['verified', 'rejected']:
                instance.verification_status = verification_status
                instance.verification_notes = verification_notes
                instance.verified_by = request.user
                instance.verified_at = timezone.now()
                instance.save()

            # Update related User is_verified
                if verification_status == 'verified':
                    instance.user.is_verified = True
                else:
                    instance.user.is_verified = False
                instance.user.save(update_fields=['is_verified'])

        # Handle feature status updates
        if 'is_featured' in request.data:
            instance.is_featured = request.data.get('is_featured')
            instance.save()

        # Handle active status updates
        if 'is_active' in request.data:
            instance.is_active = request.data.get('is_active')
            instance.save()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)


class ServiceProviderStatsView(generics.GenericAPIView):
    """
    API endpoint for super admin to get service provider statistics
    """
    permission_classes = [IsSuperAdmin]
    
    def get(self, request):
        from django.db.models import Count, Avg
        from django.utils import timezone
        from datetime import timedelta
        
        base_qs = ServiceProviderProfile.objects.select_related('user').filter(
            user__user_type="provider"
        )
        
        # Basic counts
        total_providers = base_qs.count()
        active_providers = base_qs.filter(is_active=True).count()
        
        # Verification status breakdown
        verification_stats = base_qs.values('verification_status').annotate(
            count=Count('id')
        )
        
        # Business type breakdown
        business_type_stats = base_qs.values('business_type').annotate(
            count=Count('id')
        )
        
        # Location breakdown (top 10 states)
        location_stats = base_qs.values('business_state').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Recent registrations (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_registrations = base_qs.filter(
            created_at__gte=thirty_days_ago
        ).count()
        
        # Average ratings
        avg_rating = base_qs.aggregate(
            avg_rating=Avg('average_rating')
        )['avg_rating'] or 0
        
        # Top performers
        top_rated = base_qs.filter(
            average_rating__gt=0
        ).order_by('-average_rating')[:5].values(
            'id', 'business_name', 'average_rating', 'total_reviews'
        )
        
        most_packages = base_qs.filter(
            total_packages__gt=0
        ).order_by('-total_packages')[:5].values(
            'id', 'business_name', 'total_packages'
        )
        
        return Response({
            'overview': {
                'total_providers': total_providers,
                'active_providers': active_providers,
                'inactive_providers': total_providers - active_providers,
                'recent_registrations': recent_registrations,
                'average_rating': round(float(avg_rating), 2)
            },
            'verification_breakdown': list(verification_stats),
            'business_type_breakdown': list(business_type_stats),
            'location_breakdown': list(location_stats),
            'top_performers': {
                'top_rated': list(top_rated),
                'most_packages': list(most_packages)
            }
        })


class PilgrimManagementListView(generics.ListAPIView):
    """
    API endpoint for admin to list pilgrim users
    """
    serializer_class = UserManagementSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        # Base queryset filtered for pilgrims only
        queryset = User.objects.filter(user_type='pilgrim')
        
        # Filter by verification status
        is_verified = self.request.query_params.get('is_verified')
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified.lower() == 'true')
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Search by email or username
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) |
                Q(username__icontains=search)
            )
        
        return queryset.order_by('-created_at')

class PilgrimManagementDetailView(generics.RetrieveAPIView):
    """
    API endpoint for admin to retrieve a single pilgrim user by ID
    """
    queryset = User.objects.filter(user_type='pilgrim')
    serializer_class = UserManagementSerializer
    permission_classes = [IsSuperAdmin]
    lookup_field = 'id'

class BulkUserActionView(APIView):
    """
    API endpoint for bulk user actions
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        serializer = BulkUserActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_ids = serializer.validated_data['user_ids']
        action = serializer.validated_data['action']
        
        users = User.objects.filter(id__in=user_ids)
        
        if action == 'activate':
            users.update(is_active=True)
            message = f'{users.count()} users activated successfully'
        elif action == 'deactivate':
            users.update(is_active=False)
            message = f'{users.count()} users deactivated successfully'
        elif action == 'verify':
            users.update(is_verified=True)
            message = f'{users.count()} users verified successfully'
        elif action == 'unverify':
            users.update(is_verified=False)
            message = f'{users.count()} users unverified successfully'
        
        # Log activity for admin
        UserActivity.objects.create(
            user=request.user,
            activity_type='bulk_action',
            description=f'Bulk {action} performed on {users.count()} users',
            ip_address=get_client_ip(request),
            metadata={'action': action, 'user_count': users.count()}
        )
        
        return Response({
            'message': message
        }, status=status.HTTP_200_OK)


class ProviderVerificationView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request, provider_id):
        provider = get_object_or_404(ServiceProviderProfile, id=provider_id)
        action = request.data.get('action')
        notes = request.data.get('notes', '')

        if action not in ['approve', 'reject']:
            return Response({'error': 'Invalid action. Use "approve" or "reject"'}, status=400)

        # Update provider
        provider.verification_status = 'verified' if action == 'approve' else 'rejected'
        provider.verification_notes = notes
        if action == 'approve':
            provider.verified_by = request.user
            provider.verified_at = timezone.now()
            # Update user verified status
            User.objects.filter(id=provider.user_id).update(is_verified=True)
        else:
            User.objects.filter(id=provider.user_id).update(is_verified=False)
        provider.save()

        # Send notification
        NotificationService.send_verification_complete_notification(provider)

        # Log activity safely
        UserActivity.objects.create(
            user=request.user,
            activity_type='inquiry_sent',
            description=f'Provider {action}d',
            ip_address=get_client_ip(request)[:45],
            metadata={'provider_id': provider_id, 'action': action}
        )

        return Response({'message': f'Provider {action}d successfully'}, status=200)


# API Helper Views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_stats(request):
    """
    API endpoint to get user statistics
    """
    user = request.user
    stats = {
        'total_logins': LoginAttempt.objects.filter(email=user.email, success=True).count(),
        'last_login': user.last_login,
        'account_created': user.created_at,
        'is_verified': user.is_verified,
        'user_type': user.user_type
    }
    
    # Add role-specific stats
    if user.user_type == 'provider':
        try:
            provider = user.serviceproviderprofile
            stats.update({
                'total_packages': provider.total_packages,
                'total_leads': provider.total_leads,
                'total_bookings': provider.total_bookings,
                'average_rating': float(provider.average_rating),
                'total_reviews': provider.total_reviews,
                'verification_status': provider.verification_status,
                'is_featured': provider.is_featured,
            })
        except ServiceProviderProfile.DoesNotExist:
            pass
    
    elif user.user_type == 'pilgrim':
        try:
            profile = user.pilgrimprofile
            stats.update({
                'total_bookings': profile.total_bookings,
                'total_inquiries': profile.total_inquiries,
                'saved_packages': SavedPackage.objects.filter(user=user).count(),
            })
        except:
            pass
    
    return Response(stats, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_otp(request):
    """
    API endpoint to resend OTP (for email or phone)
    """
    email = request.data.get('email')
    phone = request.data.get('phone')
    purpose = request.data.get('purpose', 'login')

    if not email and not phone:
        return Response(
            {'error': 'Either email or phone is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email) if email else User.objects.get(phone=phone)
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Generate OTP
    otp = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=5 if purpose == 'login' else 10)

    # Save OTP in DB
    OTPVerification.objects.create(
        user=user,
        otp=otp,
        purpose=purpose,
        expires_at=expires_at
    )

    # Send OTP
    if email:
        send_email_otp(email, otp, purpose)
    else:
        send_sms_otp(phone, otp)

    return Response(
        {'message': 'OTP resent successfully'},
        status=status.HTTP_200_OK
    )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """
    API endpoint to get dashboard statistics
    """
    user = request.user
    
    if user.user_type == 'provider':
        try:
            provider = user.serviceproviderprofile
            stats = {
                'total_packages': provider.total_packages,
                'active_packages': provider.active_packages,
                'total_leads': provider.total_leads,
                'total_bookings': provider.total_bookings,
                'pending_bookings': provider.pending_bookings,
                'completed_bookings': provider.completed_bookings,
                'average_rating': float(provider.average_rating),
                'total_reviews': provider.total_reviews,
                'monthly_revenue': provider.monthly_revenue,
                'yearly_revenue': provider.yearly_revenue,
                'verification_status': provider.verification_status,
                'is_featured': provider.is_featured,
            }
        except ServiceProviderProfile.DoesNotExist:
            stats = {'error': 'Provider profile not found'}
    
    elif user.user_type == 'pilgrim':
        try:
            profile = user.pilgrimprofile
            stats = {
                'total_bookings': profile.total_bookings,
                'active_bookings': profile.active_bookings,
                'completed_bookings': profile.completed_bookings,
                'total_inquiries': profile.total_inquiries,
                'saved_packages': SavedPackage.objects.filter(user=user).count(),
                'total_reviews': profile.total_reviews,
                'favorite_destinations': profile.favorite_destinations,
            }
        except :
            stats = {'error': 'Pilgrim profile not found'}
    
    elif user.is_staff:
        stats = {
            'total_users': User.objects.count(),
            'total_providers': ServiceProviderProfile.objects.count(),
            'verified_providers': ServiceProviderProfile.objects.filter(verification_status='verified').count(),
            'pending_verifications': ServiceProviderProfile.objects.filter(verification_status='pending').count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'verified_users': User.objects.filter(is_verified=True).count(),
            'recent_registrations': User.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=30)
            ).count(),
        }
    
    else:
        stats = {'error': 'Invalid user type'}
    
    return Response(stats, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deactivate_account(request):
    """
    API endpoint to deactivate user account
    """
    user = request.user
    reason = request.data.get('reason', 'User requested')
    
    # Mark user as inactive
    user.is_active = False
    user.save()
    
    # Deactivate all sessions
    UserSession.objects.filter(user=user, is_active=True).update(is_active=False)
    
    # If service provider, deactivate profile
    if user.user_type == 'provider':
        try:
            provider = user.serviceproviderprofile
            provider.is_active = False
            provider.save()
        except ServiceProviderProfile.DoesNotExist:
            pass
    
    # Log activity
    UserActivity.objects.create(
        user=user,
        activity_type='account_deactivation',
        description=f'Account deactivated: {reason}',
        ip_address=get_client_ip(request),
        metadata={'reason': reason}
    )
    
    return Response({
        'message': 'Account deactivated successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reactivate_account(request):
    """
    API endpoint to reactivate user account
    """
    user = request.user
    
    # Mark user as active
    user.is_active = True
    user.save()
    
    # If service provider, reactivate profile
    if user.user_type == 'provider':
        try:
            provider = user.serviceproviderprofile
            provider.is_active = True
            provider.save()
        except ServiceProviderProfile.DoesNotExist:
            pass
    
    # Log activity
    UserActivity.objects.create(
        user=user,
        activity_type='account_reactivation',
        description='Account reactivated',
        ip_address=get_client_ip(request)
    )
    
    return Response({
        'message': 'Account reactivated successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_settings(request):
    """
    API endpoint to get user notification settings
    """
    user = request.user
    
    # Get or create notification settings
    # This would typically be in a separate NotificationSettings model
    settings = {
        'email_notifications': True,
        'sms_notifications': True,
        'push_notifications': True,
        'booking_updates': True,
        'promotional_emails': True,
        'security_alerts': True,
    }
    
    return Response(settings, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_notification_settings(request):
    """
    API endpoint to update user notification settings
    """
    user = request.user
    
    # Update notification settings
    # This would typically update a NotificationSettings model
    settings = request.data
    
    # Log activity
    UserActivity.objects.create(
        user=user,
        activity_type='settings_update',
        description='Notification settings updated',
        ip_address=get_client_ip(request),
        metadata={'settings': settings}
    )
    
    return Response({
        'message': 'Notification settings updated successfully',
        'settings': settings
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def admin_dashboard_stats(request):
    """
    API endpoint for admin dashboard statistics
    """
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta
    
    # Date ranges
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)
    
    stats = {
        'users': {
            'total': User.objects.count(),
            'active': User.objects.filter(is_active=True).count(),
            'verified': User.objects.filter(is_verified=True).count(),
            'new_today': User.objects.filter(created_at__date=today).count(),
            'new_this_week': User.objects.filter(created_at__date__gte=last_week).count(),
            'new_this_month': User.objects.filter(created_at__date__gte=last_month).count(),
        },
        'providers': {
            'total': ServiceProviderProfile.objects.count(),
            'active': ServiceProviderProfile.objects.filter(is_active=True).count(),
            'verified': ServiceProviderProfile.objects.filter(verification_status='verified').count(),
            'pending': ServiceProviderProfile.objects.filter(verification_status='pending').count(),
            'featured': ServiceProviderProfile.objects.filter(is_featured=True).count(),
        },
        'pilgrims': {
            'total': User.objects.filter(user_type='pilgrim').count() if hasattr(User, 'user_type') else User.objects.count(),
            'active': User.objects.filter(user_type='pilgrim', is_active=True).count() if hasattr(User, 'user_type') else User.objects.filter(is_active=True).count(),
        },
        'activities': {
            'total': UserActivity.objects.count(),
            'today': UserActivity.objects.filter(created_at__date=today).count(),
            'yesterday': UserActivity.objects.filter(created_at__date=yesterday).count(),
            'this_week': UserActivity.objects.filter(created_at__date__gte=last_week).count(),
        },
        'login_attempts': {
            'total': LoginAttempt.objects.count(),
            'successful': LoginAttempt.objects.filter(success=True).count(),
            'failed': LoginAttempt.objects.filter(success=False).count(),
            'today': LoginAttempt.objects.filter(created_at__date=today).count(),
        },
        'otp_verifications': {
            'total': OTPVerification.objects.count(),
            'used': OTPVerification.objects.filter(is_used=True).count(),
            'expired': OTPVerification.objects.filter(
                expires_at__lt=timezone.now(),
                is_used=False
            ).count(),
        }
    }
    
    return Response(stats, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_preferences(request):
    """
    API endpoint to get user preferences
    """
    user = request.user
    
    # Default preferences - would typically be stored in a UserPreferences model
    preferences = {
        'language': 'en',
        'currency': 'INR',
        'timezone': 'Asia/Kolkata',
        'date_format': 'DD/MM/YYYY',
        'theme': 'light',
        'dashboard_layout': 'grid',
        'items_per_page': 10,
    }
    
    return Response(preferences, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_preferences(request):
    """
    API endpoint to update user preferences
    """
    user = request.user
    preferences = request.data
    
    # Update preferences - would typically update a UserPreferences model
    
    # Log activity
    UserActivity.objects.create(
        user=user,
        activity_type='preferences_update',
        description='User preferences updated',
        ip_address=get_client_ip(request),
        metadata={'preferences': preferences}
    )
    
    return Response({
        'message': 'Preferences updated successfully',
        'preferences': preferences
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_user_data(request):
    """
    API endpoint to export user data (GDPR compliance)
    """
    user = request.user
    
    # This would typically generate a comprehensive export
    # of all user data for GDPR compliance
    
    # Log activity
    UserActivity.objects.create(
        user=user,
        activity_type='data_export',
        description='User data export requested',
        ip_address=get_client_ip(request)
    )
    
    return Response({
        'message': 'Data export request submitted. You will receive an email when ready.'
    }, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_user_account(request):
    """
    API endpoint to delete user account (GDPR compliance)
    """
    user = request.user
    password = request.data.get('password')
    
    # Verify password
    if not user.check_password(password):
        return Response({
            'error': 'Invalid password'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Log activity before deletion
    UserActivity.objects.create(
        user=user,
        activity_type='account_deletion',
        description='User account deleted',
        ip_address=get_client_ip(request)
    )
    
    # Perform soft delete or anonymize data
    user.is_active = False
    user.email = f"deleted_{user.id}@example.com"
    user.username = f"deleted_{user.id}"
    user.save()
    
    return Response({
        'message': 'Account deleted successfully'
    }, status=status.HTTP_200_OK)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_nearby_providers(request):
    try:
        user_lat = float(request.GET.get('latitude'))
        user_lng = float(request.GET.get('longitude'))
        radius = float(request.GET.get('radius', 10))
    except (TypeError, ValueError):
        return Response({
            'error': 'Latitude, longitude, and radius are required and must be valid numbers.'
        }, status=status.HTTP_400_BAD_REQUEST)

    lat_range = radius / 111.0
    lng_range = radius / (111.0 * abs(user_lat))

    queryset = ServiceProviderProfile.objects.filter(
        is_active=True,
        verification_status='verified',
        user__latitude__gte=user_lat - lat_range,
        user__latitude__lte=user_lat + lat_range,
        user__longitude__gte=user_lng - lng_range,
        user__longitude__lte=user_lng + lng_range
    ).exclude(
        user__latitude__isnull=True,
        user__longitude__isnull=True
    )

    business_type = request.GET.get('business_type')
    if business_type:
        queryset = queryset.filter(business_type=business_type)

    queryset = queryset.order_by('-is_featured', '-average_rating')
    serializer = ServiceProviderListSerializer(queryset, many=True)

    return Response({
        'message': f'Found {queryset.count()} providers within {radius}km',
        'user_location': {"latitude": user_lat, "longitude": user_lng},
        'providers': serializer.data
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_location_history(request):
    """
    Get user's location update history (mainly for pilgrims)
    """
    user = request.user
    
    # Get location update activities
    activities = UserActivity.objects.filter(
        user=user,
        activity_type__in=['location_update', 'app_open_location_update']
    ).order_by('-created_at')[:50]  # Last 50 location updates
    
    location_history = []
    for activity in activities:
        history_item = {
            'timestamp': activity.created_at,
            'activity_type': activity.activity_type,
            'description': activity.description,
        }
        
        if activity.metadata and 'location' in activity.metadata:
            history_item['location'] = activity.metadata['location']
        
        location_history.append(history_item)
    
    return Response({
        'user_type': user.user_type,
        'current_location': user.get_location_info(),
        'location_history': location_history,
        'total_updates': activities.count()
    }, status=status.HTTP_200_OK)
