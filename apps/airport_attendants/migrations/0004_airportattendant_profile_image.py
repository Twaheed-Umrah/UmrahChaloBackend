import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('airport_attendants', '0003_alter_airport_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='airportattendant',
            name='profile_image',
            field=models.ImageField(
                blank=True,
                upload_to='airport_attendants/profiles/',
                validators=[django.core.validators.FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
            ),
        ),
    ]
