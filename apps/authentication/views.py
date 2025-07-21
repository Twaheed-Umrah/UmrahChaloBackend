from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth import login, logout
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Q
from datetime import timedelta
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
    PhoneVerificationSerializer, UserManagementSerializer, BulkUserActionSerializer
)
from apps.core.utils import send_otp, generate_otp, get_client_ip, get_user_agent
from apps.core.pagination import CustomPagination
from apps.core.permissions import IsOwnerOrReadOnly, IsProviderOrReadOnly


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
                metadata={'user_type': user.user_type}
            )
        except Exception as e:
            # You can log this for debugging
            print(f"Failed to log activity: {e}")

        return Response({
            'message': 'User registered successfully. Please check your email for verification.',
            'user_id': str(user.id),
            'username': user.username,
            'email': user.email
        }, status=status.HTTP_201_CREATED)

class UserLoginView(APIView):
    """
    API endpoint for user login with email and password
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
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
            session_key=request.session.session_key or '',
            device_info=user_agent,
            ip_address=ip_address,
            is_active=True
        )
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='login',
            description='User logged in',
            ip_address=ip_address,
            metadata={'login_method': 'password'}
        )
        
        return Response({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': UserProfileSerializer(user).data
        }, status=status.HTTP_200_OK)


class OTPLoginView(APIView):
    """
    API endpoint to request OTP for login
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = OTPLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)
        
        # Generate and send OTP
        otp = generate_otp()
        OTPVerification.objects.create(
            user=user,
            otp=otp,
            purpose='login',
            expires_at=timezone.now() + timedelta(minutes=5)
        )
        
        send_otp(email, otp, 'login')
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='otp_request',
            description='OTP requested for login',
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'OTP sent successfully to your email.'
        }, status=status.HTTP_200_OK)


class OTPVerificationView(APIView):
    """
    API endpoint for OTP verification
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        otp_verification = serializer.validated_data['otp_verification']
        purpose = serializer.validated_data['purpose']
        
        # Mark OTP as used
        otp_verification.is_used = True
        otp_verification.save()
        
        response_data = {'message': 'OTP verified successfully'}
        
        # Handle different purposes
        if purpose == 'email_verification':
            user.is_verified = True
            user.save()
            response_data['message'] = 'Email verified successfully'
        
        elif purpose == 'login':
            # Generate JWT tokens for login
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            
            # Create user session
            UserSession.objects.create(
                user=user,
                session_key=request.session.session_key or '',
                device_info=get_user_agent(request),
                ip_address=get_client_ip(request),
                is_active=True
            )
            
            response_data.update({
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': UserProfileSerializer(user).data
            })
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='otp_verification',
            description=f'OTP verified for {purpose}',
            ip_address=get_client_ip(request),
            metadata={'purpose': purpose}
        )
        
        return Response(response_data, status=status.HTTP_200_OK)


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
            ip_address=get_client_ip(request)
        )
        
        return Response({
            'message': 'Profile updated successfully',
            'user': serializer.data
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    API endpoint for user logout
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            # Deactivate user session
            UserSession.objects.filter(
                user=request.user,
                is_active=True
            ).update(is_active=False)
            
            # Log activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='logout',
                description='User logged out',
                ip_address=get_client_ip(request)
            )
            
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)


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
        
        return Response({
            'message': 'Service provider registered successfully. Please check your email for verification.',
            'provider_id': provider.id,
            'user_id': provider.user.id,
            'email': provider.user.email
        }, status=status.HTTP_201_CREATED)


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
        
        # Order by featured first, then by rating
        return queryset.order_by('-is_featured', '-average_rating', '-created_at')


class ServiceProviderDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint for service provider detail
    """
    queryset = ServiceProviderProfile.objects.all()
    serializer_class = ServiceProviderProfileSerializer
    permission_classes = [IsProviderOrReadOnly]
    
    def perform_update(self, serializer):
        provider = serializer.save()
        
        # Log activity
        UserActivity.objects.create(
            user=provider.user,
            activity_type='profile_update',
            description='Service provider profile updated',
            ip_address=get_client_ip(self.request)
        )
    
    def perform_destroy(self, instance):
        # Soft delete by setting is_active to False
        instance.is_active = False
        instance.save()
        
        # Log activity
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
class UserManagementListView(generics.ListAPIView):
    """
    API endpoint for admin to list users
    """
    serializer_class = UserManagementSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        queryset = User.objects.all()
        
        # Filter by user type
        user_type = self.request.query_params.get('user_type')
        if user_type:
            queryset = queryset.filter(user_type=user_type)
        
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
    """
    API endpoint for admin to verify service providers
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request, provider_id):
        provider = get_object_or_404(ServiceProviderProfile, id=provider_id)
        action = request.data.get('action')  # 'approve' or 'reject'
        notes = request.data.get('notes', '')
        
        if action == 'approve':
            provider.verification_status = 'verified'
            provider.verified_by = request.user
            provider.verified_at = timezone.now()
            provider.verification_notes = notes
            provider.save()
            
            # Send approval notification
            # You can implement email notification here
            
            message = 'Provider approved successfully'
            
        elif action == 'reject':
            provider.verification_status = 'rejected'
            provider.verification_notes = notes
            provider.save()
            
            # Send rejection notification
            # You can implement email notification here
            
            message = 'Provider rejected successfully'
            
        else:
            return Response(
                {'error': 'Invalid action. Use "approve" or "reject"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            activity_type='provider_verification',
            description=f'Provider {action}d',
            ip_address=get_client_ip(request),
            metadata={'provider_id': provider_id, 'action': action}
        )
        
        return Response({
            'message': message
        }, status=status.HTTP_200_OK)


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
    API endpoint to resend OTP
    """
    email = request.data.get('email')
    purpose = request.data.get('purpose', 'email_verification')
    
    if not email:
        return Response({
            'error': 'Email is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({
            'error': 'User with this email does not exist'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Generate and send new OTP
    otp = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=5 if purpose == 'login' else 10)
    
    OTPVerification.objects.create(
        user=user,
        otp=otp,
        purpose=purpose,
        expires_at=expires_at
    )
    
    send_otp(email, otp, purpose)
    
    # Log activity
    # Log activity
    UserActivity.objects.create(
        user=user,
        activity_type='otp_resend',
        description=f'OTP resent for {purpose}',
        ip_address=get_client_ip(request),
        metadata={'purpose': purpose}
    )
    
    return Response({
        'message': 'OTP sent successfully'
    }, status=status.HTTP_200_OK)


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
            'total_pilgrims': PilgrimProfile.objects.count(),
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
@permission_classes([IsAdminUser])
def admin_dashboard_stats(request):
    """
    API endpoint for admin dashboard statistics
    """
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    
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
            'total': PilgrimProfile.objects.count(),
            'active': PilgrimProfile.objects.filter(user__is_active=True).count(),
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