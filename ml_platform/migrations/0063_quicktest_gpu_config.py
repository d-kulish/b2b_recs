from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0062_fix_bq_location_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='quicktest',
            name='gpu_config',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="GPU config for Trainer. Empty = CPU-only. Example: {'gpu_type': 'NVIDIA_TESLA_T4', 'gpu_count': 1, 'machine_type': 'n1-standard-4'}",
            ),
        ),
    ]
