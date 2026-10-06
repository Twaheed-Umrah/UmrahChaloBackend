import decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('airport_attendants', '0002_seed_airports'),
    ]

    operations = [
        migrations.AlterField(
            model_name='airport',
            name='price',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0.01'))],
            ),
        ),
    ]
