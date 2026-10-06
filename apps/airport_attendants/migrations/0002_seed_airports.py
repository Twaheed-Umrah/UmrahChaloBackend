from decimal import Decimal

from django.db import migrations


AIRPORTS = [
    ('Delhi', 'DEL', True),
    ('Mumbai', 'BOM', True),
    ('Bengaluru', 'BLR', False),
    ('Hyderabad', 'HYD', False),
    ('Kochi', 'COK', False),
    ('Kozhikode', 'CCJ', False),
    ('Ahmedabad', 'AMD', False),
    ('Lucknow', 'LKO', True),
    ('Mangaluru', 'IXE', False),
    ('Kannur', 'CNN', False),
]


def seed_airports(apps, schema_editor):
    Airport = apps.get_model('airport_attendants', 'Airport')
    database = schema_editor.connection.alias

    for name, code, active in AIRPORTS:
        Airport.objects.using(database).get_or_create(
            name=name,
            defaults={
                'code': code,
                'price': Decimal('500.00'),
                'is_active': active,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('airport_attendants', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_airports, migrations.RunPython.noop),
    ]
