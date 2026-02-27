from rest_framework import serializers
from .models import MasterPincode

class MasterPincodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterPincode
        fields = ['pincode', 'area_name', 'city', 'state', 'latitude', 'longitude']
