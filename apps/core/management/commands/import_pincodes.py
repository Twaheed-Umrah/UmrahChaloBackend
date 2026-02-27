import csv
import os
from django.core.management.base import BaseCommand
from apps.core.models import MasterPincode

class Command(BaseCommand):
    help = 'Import master pincode data from a CSV file or use seed data'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        csv_file = options.get('file')
        
        if csv_file:
            self.import_from_csv(csv_file)
        else:
            self.import_seed_data()

    def import_seed_data(self):
        self.stdout.write('Importing seed pincode data...')
        # Sample data for major Indian cities
        seed_data = [
            # Mumbai
            {"pincode": "400001", "area_name": "Fort", "city": "Mumbai", "state": "Maharashtra", "lat": 18.9322, "lng": 72.8335},
            {"pincode": "400002", "area_name": "Kalbadevi", "city": "Mumbai", "state": "Maharashtra", "lat": 18.9485, "lng": 72.8290},
            {"pincode": "400050", "area_name": "Bandra West", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0596, "lng": 72.8295},
            {"pincode": "400051", "area_name": "Bandra East", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0544, "lng": 72.8402},
            {"pincode": "400053", "area_name": "Andheri West", "city": "Mumbai", "state": "Maharashtra", "lat": 19.1200, "lng": 72.8242},
            # Delhi
            {"pincode": "110001", "area_name": "Connaught Place", "city": "New Delhi", "state": "Delhi", "lat": 28.6304, "lng": 77.2177},
            {"pincode": "110002", "area_name": "Daryaganj", "city": "New Delhi", "state": "Delhi", "lat": 28.6475, "lng": 77.2358},
            {"pincode": "110011", "area_name": "Sectt North", "city": "New Delhi", "state": "Delhi", "lat": 28.6094, "lng": 77.2114},
            # Bangalore
            {"pincode": "560001", "area_name": "City Life", "city": "Bangalore", "state": "Karnataka", "lat": 12.9716, "lng": 77.5946},
            {"pincode": "560034", "area_name": "Koramangala", "city": "Bangalore", "state": "Karnataka", "lat": 12.9352, "lng": 77.6245},
            {"pincode": "560037", "area_name": "Marathahalli", "city": "Bangalore", "state": "Karnataka", "lat": 12.9591, "lng": 77.7001},
            # Hyderabad
            {"pincode": "500001", "area_name": "Hyderabad G.P.O.", "city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lng": 78.4867},
            {"pincode": "500032", "area_name": "Gachibowli", "city": "Hyderabad", "state": "Telangana", "lat": 17.4401, "lng": 78.3489},
            # Chennai
            {"pincode": "600001", "area_name": "Chennai G.P.O.", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lng": 80.2707},
            {"pincode": "600017", "area_name": "T. Nagar", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0418, "lng": 80.2341},
            # Kolkata
            {"pincode": "700001", "area_name": "Kolkata G.P.O.", "city": "Kolkata", "state": "West Bengal", "lat": 22.5626, "lng": 88.3630},
            # Lucknow
            {"pincode": "226001", "area_name": "Lucknow G.P.O.", "city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "lng": 80.9462},
            {"pincode": "226010", "area_name": "Gomti Nagar", "city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8496, "lng": 81.0072},
            # Srinagar
            {"pincode": "190001", "area_name": "Srinagar G.P.O.", "city": "Srinagar", "state": "Jammu & Kashmir", "lat": 34.0837, "lng": 74.7973},
        ]

        created_count = 0
        for data in seed_data:
            obj, created = MasterPincode.objects.get_or_create(
                pincode=data['pincode'],
                area_name=data['area_name'],
                defaults={
                    'city': data['city'],
                    'state': data['state'],
                    'latitude': data['lat'],
                    'longitude': data['lng']
                }
            )
            if created:
                created_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully imported {created_count} new pincodes.'))

    def import_from_csv(self, file_path):
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        self.stdout.write(f'Importing pincodes from {file_path}...')
        count = 0
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Expecting columns: pincode, area_name, city, state, latitude, longitude
                try:
                    MasterPincode.objects.get_or_create(
                        pincode=row['pincode'],
                        area_name=row['area_name'],
                        defaults={
                            'city': row.get('city', ''),
                            'state': row.get('state', ''),
                            'latitude': row.get('latitude') or None,
                            'longitude': row.get('longitude') or None
                        }
                    )
                    count += 1
                    if count % 1000 == 0:
                        self.stdout.write(f'Imported {count} pincodes...')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Error importing row {row}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} pincodes from CSV.'))
