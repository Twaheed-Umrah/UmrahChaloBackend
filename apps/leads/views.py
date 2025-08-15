from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q, Count, F, Case, When, Value, IntegerField
from django.utils import timezone
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from apps.core.permissions import IsOwnerOrReadOnly, IsProviderOrReadOnly
from apps.core.pagination import LargeResultsSetPagination
from .models import Lead, LeadDistribution, LeadInteraction, LeadNote
from .serializers import (
    LeadSerializer, LeadCreateSerializer, LeadDistributionSerializer,
    LeadDistributionResponseSerializer, LeadInteractionSerializer,
    LeadNoteSerializer, LeadStatsSerializer, LeadSummarySerializer,
    LeadManualDistributionSerializer
)
from .tasks import distribute_lead_to_providers
from .filters import LeadFilter, LeadDistributionFilter


class LeadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Lead model with automatic distribution
    """
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = LeadFilter
    search_fields = ['full_name', 'email', 'phone', 'departure_city']
    ordering_fields = ['created_at', 'preferred_date', 'status', 'priority']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Filter queryset based on user role
        """
        user = self.request.user
        
        if user.user_type in ['super_admin', 'admin']:
            return Lead.objects.select_related(
                'user', 'package', 'service'
            ).prefetch_related('distributions')
        
        # Service providers can only see distributed leads
        if hasattr(user, 'service_provider_profile'):
            return Lead.objects.filter(
                distributions__provider=user.service_provider_profile
            ).select_related(
                'user', 'package', 'service'
            ).prefetch_related('distributions').distinct()
        
        # Regular users can only see their own leads
        return Lead.objects.filter(user=user).select_related(
            'package', 'service'
        ).prefetch_related('distributions')
    
    def get_serializer_class(self):
        """
        Return appropriate serializer based on action
        """
        if self.action == 'create':
            return LeadCreateSerializer
        elif self.action == 'list':
            return LeadSummarySerializer
        elif self.action == 'manual_distribute':
            return LeadManualDistributionSerializer
        return LeadSerializer
    
    def perform_create(self, serializer):
        """
        Create lead and automatically distribute it to relevant providers
        This is called when a pilgrim/user creates a lead
        """
        with transaction.atomic():
            # The serializer's create method already handles auto-distribution
            lead = serializer.save()
            
            # Optionally trigger async distribution if you want to use Celery
            # distribute_lead_to_providers.delay(lead.id)
            
            return lead
    
    @action(detail=True, methods=['post'])
    def mark_contacted(self, request, pk=None):
        """
        Mark lead as contacted by provider
        """
        lead = self.get_object()
        
        # Only provider who received the lead can mark it as contacted
        if hasattr(request.user, 'service_provider_profile'):
            distribution = LeadDistribution.objects.filter(
                lead=lead,
                provider=request.user.service_provider_profile
            ).first()
            
            if distribution:
                distribution.mark_as_viewed()
                lead.status = 'contacted'
                lead.save()
                
                return Response({
                    'message': 'Lead marked as contacted',
                    'lead_id': lead.id,
                    'status': lead.status
                })
        
        return Response(
            {'error': 'Not authorized to mark this lead as contacted'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    @action(detail=True, methods=['post'])
    def mark_converted(self, request, pk=None):
        """
        Mark lead as converted by provider
        """
        lead = self.get_object()
        
        # Only provider who received the lead can mark it as converted
        if hasattr(request.user, 'service_provider_profile'):
            distribution = LeadDistribution.objects.filter(
                lead=lead,
                provider=request.user.service_provider_profile
            ).first()
            
            if distribution:
                lead.status = 'converted'
                lead.save()
                
                # Update distribution status
                distribution.status = 'responded'
                distribution.responded_at = timezone.now()
                distribution.save()
                
                return Response({
                    'message': 'Lead marked as converted',
                    'lead_id': lead.id,
                    'status': lead.status
                })
        
        return Response(
            {'error': 'Not authorized to mark this lead as converted'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    @action(detail=True, methods=['post'])
    def mark_rejected(self, request, pk=None):
        """
        Mark lead as rejected by provider
        """
        lead = self.get_object()
        
        # Only provider who received the lead can mark it as rejected
        if hasattr(request.user, 'service_provider_profile'):
            distribution = LeadDistribution.objects.filter(
                lead=lead,
                provider=request.user.service_provider_profile
            ).first()
            
            if distribution:
                lead.status = 'rejected'
                lead.save()
                
                # Update distribution status
                distribution.status = 'ignored'
                distribution.save()
                
                return Response({
                    'message': 'Lead marked as rejected',
                    'lead_id': lead.id,
                    'status': lead.status
                })
        
        return Response(
            {'error': 'Not authorized to mark this lead as rejected'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    @action(detail=False, methods=['get'])
    def my_leads(self, request):
        """
        Get leads for current user
        """
        leads = Lead.objects.filter(user=request.user).select_related(
            'package', 'service'
        ).prefetch_related('distributions__provider')
        
        page = self.paginate_queryset(leads)
        if page is not None:
            serializer = LeadSummarySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = LeadSummarySerializer(leads, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def manual_distribute(self, request):
        """
        Manual lead distribution by superadmin
        Automatically distributes to providers based on business_type
        """
        serializer = LeadManualDistributionSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                result = serializer.distribute_lead()
                
                return Response({
                    'success': True,
                    'message': result['message'],
                    'lead_id': result['lead'].id,
                    'distributed_to': len(result['distributions']),
                    'providers': [
                        {
                            'id': dist.provider.id,
                            'name': dist.provider.company_name or dist.provider.user.get_full_name(),
                            'business_type': dist.provider.business_type
                        }
                        for dist in result['distributions']
                    ]
                })
            except Exception as e:
                return Response(
                    {'error': f'Distribution failed: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def redistribute(self, request, pk=None):
        """
        Redistribute a lead to additional providers
        """
        lead = self.get_object()
        
        # Use LeadCreateSerializer to get business types and distribute
        serializer = LeadCreateSerializer()
        target_business_types = serializer.get_target_business_types(lead)
        
        with transaction.atomic():
            distributions = serializer.distribute_lead(lead)
            
            return Response({
                'success': True,
                'message': f'Lead redistributed to {len(distributions)} additional providers',
                'lead_id': lead.id,
                'target_business_types': target_business_types,
                'new_distributions': len(distributions)
            })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get lead statistics based on user role
        """
        user = request.user
        
        if hasattr(user, 'service_provider_profile'):
            # Provider stats - leads distributed to this provider
            provider_leads = Lead.objects.filter(
                distributions__provider=user.service_provider_profile
            ).distinct()
            
            total_leads = provider_leads.count()
            pending_leads = provider_leads.filter(status='pending').count()
            contacted_leads = provider_leads.filter(status='contacted').count()
            converted_leads = provider_leads.filter(status='converted').count()
            rejected_leads = provider_leads.filter(status='rejected').count()
            expired_leads = provider_leads.filter(status='expired').count()
            
            # Calculate rates
            conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
            response_rate = ((contacted_leads + converted_leads) / total_leads * 100) if total_leads > 0 else 0
            
            # Time-based stats
            today = timezone.now().date()
            week_ago = today - timezone.timedelta(days=7)
            month_ago = today - timezone.timedelta(days=30)
            
            today_leads = provider_leads.filter(created_at__date=today).count()
            this_week_leads = provider_leads.filter(created_at__date__gte=week_ago).count()
            this_month_leads = provider_leads.filter(created_at__date__gte=month_ago).count()
            
        else:
            # User stats - leads created by this user
            user_leads = Lead.objects.filter(user=user)
            
            total_leads = user_leads.count()
            pending_leads = user_leads.filter(status='pending').count()
            contacted_leads = user_leads.filter(status='contacted').count()
            converted_leads = user_leads.filter(status='converted').count()
            rejected_leads = user_leads.filter(status='rejected').count()
            expired_leads = user_leads.filter(status='expired').count()
            
            conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
            response_rate = ((contacted_leads + converted_leads) / total_leads * 100) if total_leads > 0 else 0
            
            today = timezone.now().date()
            week_ago = today - timezone.timedelta(days=7)
            month_ago = today - timezone.timedelta(days=30)
            
            today_leads = user_leads.filter(created_at__date=today).count()
            this_week_leads = user_leads.filter(created_at__date__gte=week_ago).count()
            this_month_leads = user_leads.filter(created_at__date__gte=month_ago).count()
        
        stats_data = {
            'total_leads': total_leads,
            'pending_leads': pending_leads,
            'contacted_leads': contacted_leads,
            'converted_leads': converted_leads,
            'rejected_leads': rejected_leads,
            'expired_leads': expired_leads,
            'conversion_rate': round(conversion_rate, 2),
            'response_rate': round(response_rate, 2),
            'today_leads': today_leads,
            'this_week_leads': this_week_leads,
            'this_month_leads': this_month_leads,
        }
        
        serializer = LeadStatsSerializer(stats_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def distribution_summary(self, request):
        """
        Get distribution summary for admin
        """
        total_leads = Lead.objects.count()
        distributed_leads = Lead.objects.filter(is_distributed=True).count()
        pending_distribution = Lead.objects.filter(is_distributed=False).count()
        
        # Leads by business type
        from apps.authentication.models import ServiceProviderProfile
        business_type_stats = []
        
        for business_type, display_name in ServiceProviderProfile.BUSINESS_TYPES:
            lead_count = LeadDistribution.objects.filter(
                provider__business_type=business_type
            ).values('lead').distinct().count()
            
            business_type_stats.append({
                'business_type': business_type,
                'display_name': display_name,
                'lead_count': lead_count
            })
        
        return Response({
            'total_leads': total_leads,
            'distributed_leads': distributed_leads,
            'pending_distribution': pending_distribution,
            'distribution_rate': round((distributed_leads / total_leads * 100), 2) if total_leads > 0 else 0,
            'business_type_stats': business_type_stats
        })


class LeadDistributionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for LeadDistribution model (read-only for providers)
    """
    queryset = LeadDistribution.objects.all()
    serializer_class = LeadDistributionSerializer
    permission_classes = [IsAuthenticated, IsProviderOrReadOnly]
    pagination_class = LargeResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = LeadDistributionFilter
    search_fields = ['lead__full_name', 'lead__email', 'lead__phone']
    ordering_fields = ['sent_at', 'viewed_at', 'responded_at', 'status']
    ordering = ['-sent_at']
    
    def get_queryset(self):
        """
        Filter queryset for current provider
        """
        if hasattr(self.request.user, 'service_provider_profile'):
            return LeadDistribution.objects.filter(
                provider=self.request.user.service_provider_profile
            ).select_related('lead', 'provider')
        return LeadDistribution.objects.none()
    
    @action(detail=True, methods=['post'])
    def mark_viewed(self, request, pk=None):
        """
        Mark lead distribution as viewed
        """
        distribution = self.get_object()
        distribution.mark_as_viewed()
        return Response({
            'message': 'Lead marked as viewed',
            'viewed_at': distribution.viewed_at,
            'status': distribution.status
        })
    
    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """
        Provider response to lead
        """
        distribution = self.get_object()
        serializer = LeadDistributionResponseSerializer(
            distribution, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Response submitted successfully',
                'distribution': LeadDistributionSerializer(distribution).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending_responses(self, request):
        """
        Get distributions pending response
        """
        pending = self.get_queryset().filter(
            status='sent',
            viewed_at__isnull=False
        )
        
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)


class LeadInteractionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for LeadInteraction model
    """
    queryset = LeadInteraction.objects.all()
    serializer_class = LeadInteractionSerializer
    permission_classes = [IsAuthenticated, IsProviderOrReadOnly]
    pagination_class = LargeResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['lead__full_name', 'notes', 'outcome_notes']
    ordering_fields = ['interaction_date', 'follow_up_date', 'is_successful']
    ordering = ['-interaction_date']
    
    def get_queryset(self):
        """
        Filter queryset for current provider
        """
        if hasattr(self.request.user, 'service_provider_profile'):
            return LeadInteraction.objects.filter(
                provider=self.request.user.service_provider_profile
            ).select_related('lead', 'provider')
        return LeadInteraction.objects.none()
    
    @action(detail=False, methods=['get'])
    def follow_ups(self, request):
        """
        Get interactions requiring follow-up
        """
        follow_ups = self.get_queryset().filter(
            follow_up_date__isnull=False,
            follow_up_date__lte=timezone.now()
        )
        
        serializer = self.get_serializer(follow_ups, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def successful_interactions(self, request):
        """
        Get successful interactions
        """
        successful = self.get_queryset().filter(is_successful=True)
        serializer = self.get_serializer(successful, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def interaction_stats(self, request):
        """
        Get interaction statistics for provider
        """
        queryset = self.get_queryset()
        
        total_interactions = queryset.count()
        successful_interactions = queryset.filter(is_successful=True).count()
        pending_follow_ups = queryset.filter(
            follow_up_date__lte=timezone.now(),
            follow_up_date__isnull=False
        ).count()
        
        success_rate = (successful_interactions / total_interactions * 100) if total_interactions > 0 else 0
        
        # Interaction types breakdown
        interaction_types = queryset.values('interaction_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response({
            'total_interactions': total_interactions,
            'successful_interactions': successful_interactions,
            'pending_follow_ups': pending_follow_ups,
            'success_rate': round(success_rate, 2),
            'interaction_types': list(interaction_types)
        })


class LeadNoteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for LeadNote model
    """
    queryset = LeadNote.objects.all()
    serializer_class = LeadNoteSerializer
    permission_classes = [IsAuthenticated, IsProviderOrReadOnly]
    pagination_class = LargeResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['note', 'lead__full_name']
    ordering_fields = ['created_at', 'is_private']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Filter queryset for current provider
        """
        if hasattr(self.request.user, 'service_provider_profile'):
            return LeadNote.objects.filter(
                provider=self.request.user.service_provider_profile
            ).select_related('lead', 'provider')
        return LeadNote.objects.none()
    
    @action(detail=False, methods=['get'])
    def by_lead(self, request):
        """
        Get notes by lead ID
        """
        lead_id = request.query_params.get('lead_id')
        if not lead_id:
            return Response(
                {'error': 'lead_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        notes = self.get_queryset().filter(lead_id=lead_id)
        serializer = self.get_serializer(notes, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def private_notes(self, request):
        """
        Get private notes only
        """
        private_notes = self.get_queryset().filter(is_private=True)
        serializer = self.get_serializer(private_notes, many=True)
        return Response(serializer.data)