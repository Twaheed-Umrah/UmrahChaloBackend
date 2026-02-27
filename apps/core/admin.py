from django.contrib import admin
from .models import MasterPincode

@admin.register(MasterPincode)
class MasterPincodeAdmin(admin.ModelAdmin):
    list_display = ('pincode', 'area_name', 'city', 'state', 'latitude', 'longitude')
    list_filter = ('state', 'city')
    search_fields = ('pincode', 'area_name', 'city')
    ordering = ('pincode',)
    list_per_page = 50
