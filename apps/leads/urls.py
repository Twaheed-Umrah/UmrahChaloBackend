from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router and register viewsets
router = DefaultRouter()
router.register(r'leads', views.LeadViewSet, basename='leads')
router.register(r'distributions', views.LeadDistributionViewSet, basename='lead-distributions')
router.register(r'interactions', views.LeadInteractionViewSet, basename='lead-interactions')
router.register(r'notes', views.LeadNoteViewSet, basename='lead-notes')

app_name = 'leads'

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]

# API Endpoints Documentation:
"""
LEAD MANAGEMENT APIS:

1. LEAD ENDPOINTS:
   - GET /api/leads/                           # List all leads (filtered by user role)
   - POST /api/leads/                          # Create new lead (AUTO-DISTRIBUTES to providers)
   - GET /api/leads/{id}/                      # Retrieve specific lead
   - PUT /api/leads/{id}/                      # Update lead
   - PATCH /api/leads/{id}/                    # Partial update lead
   - DELETE /api/leads/{id}/                   # Delete lead

2. LEAD CUSTOM ACTIONS:
   - GET /api/leads/my_leads/                  # Get current user's leads
   - GET /api/leads/stats/                     # Get lead statistics
   - POST /api/leads/{id}/mark_contacted/      # Mark lead as contacted (Provider only)
   - POST /api/leads/{id}/mark_converted/      # Mark lead as converted (Provider only)
   - POST /api/leads/{id}/mark_rejected/       # Mark lead as rejected (Provider only)
   
3. SUPERADMIN LEAD ACTIONS:
   - POST /api/leads/manual_distribute/        # Manual lead distribution (Superadmin only)
   - POST /api/leads/{id}/redistribute/        # Redistribute lead to additional providers
   - GET /api/leads/distribution_summary/      # Get distribution statistics

4. LEAD DISTRIBUTION ENDPOINTS:
   - GET /api/distributions/                   # List distributions for current provider
   - GET /api/distributions/{id}/              # Get specific distribution
   - POST /api/distributions/{id}/mark_viewed/ # Mark distribution as viewed
   - POST /api/distributions/{id}/respond/     # Respond to lead with quote/message
   - GET /api/distributions/pending_responses/ # Get distributions pending response

5. LEAD INTERACTION ENDPOINTS:
   - GET /api/interactions/                    # List interactions for current provider
   - POST /api/interactions/                   # Create new interaction
   - GET /api/interactions/{id}/               # Get specific interaction
   - PUT /api/interactions/{id}/               # Update interaction
   - PATCH /api/interactions/{id}/             # Partial update interaction
   - DELETE /api/interactions/{id}/            # Delete interaction
   - GET /api/interactions/follow_ups/         # Get interactions requiring follow-up
   - GET /api/interactions/successful_interactions/ # Get successful interactions
   - GET /api/interactions/interaction_stats/  # Get interaction statistics

6. LEAD NOTES ENDPOINTS:
   - GET /api/notes/                           # List notes for current provider
   - POST /api/notes/                          # Create new note
   - GET /api/notes/{id}/                      # Get specific note
   - PUT /api/notes/{id}/                      # Update note
   - PATCH /api/notes/{id}/                    # Partial update note
   - DELETE /api/notes/{id}/                   # Delete note
   - GET /api/notes/by_lead/?lead_id={id}      # Get notes for specific lead
   - GET /api/notes/private_notes/             # Get private notes only

AUTOMATIC DISTRIBUTION FLOW:
1. User/Pilgrim creates lead via POST /api/leads/
2. System automatically determines target business_types based on:
   - Package/Service selected
   - Custom requirements and selected services
   - Keywords in special requirements
3. System finds verified, active providers matching business_types
4. Creates LeadDistribution records for top providers
5. Sends notifications (email/SMS/app) to providers
6. Providers receive leads via GET /api/distributions/

MANUAL DISTRIBUTION (Superadmin):
1. Superadmin uses POST /api/leads/manual_distribute/
2. Can specify business_types or specific provider_ids
3. System distributes to matching providers
4. Returns distribution summary

PROVIDER WORKFLOW:
1. GET /api/distributions/ - View received leads
2. POST /api/distributions/{id}/mark_viewed/ - Mark as viewed
3. POST /api/distributions/{id}/respond/ - Submit quote/response
4. POST /api/interactions/ - Log interactions with customer
5. POST /api/notes/ - Add private notes
6. POST /api/leads/{id}/mark_converted/ - Mark as converted

FILTERING & SEARCH:
- All endpoints support filtering, searching, and ordering
- Use query parameters like:
  - ?status=pending
  - ?lead_type=package
  - ?search=john
  - ?ordering=-created_at
"""