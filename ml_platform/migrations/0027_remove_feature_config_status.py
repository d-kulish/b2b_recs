# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0026_add_bq_location_to_dataset'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='featureconfig',
            name='status',
        ),
    ]
