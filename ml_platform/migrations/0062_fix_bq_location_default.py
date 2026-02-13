"""
Remove hardcoded 'US' default from Dataset.bq_location and backfill
existing records to use the deployment's GCP_LOCATION setting.
"""
import os

from django.db import migrations, models


def backfill_bq_location(apps, schema_editor):
    """Replace 'US' with the actual GCP_LOCATION for all existing datasets."""
    from django.conf import settings
    location = getattr(settings, 'GCP_LOCATION', os.environ.get('GCP_LOCATION', ''))
    if not location:
        return
    Dataset = apps.get_model('ml_platform', 'Dataset')
    Dataset.objects.filter(bq_location='US').update(bq_location=location)


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0061_billingsnapshot_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataset',
            name='bq_location',
            field=models.CharField(
                blank=True,
                default='',
                help_text="BigQuery region where the dataset exists (e.g., 'US', 'EU', 'europe-central2')",
                max_length=50,
            ),
        ),
        migrations.RunPython(backfill_bq_location, migrations.RunPython.noop),
    ]
