"""
Add model_endpoint FK to ModelConfig.

Three-step migration:
1. Add nullable FK
2. Data migration: assign existing ModelConfigs to the first ModelEndpoint
3. Make FK non-nullable + add unique_together constraint
"""

from django.db import migrations, models
import django.db.models.deletion


def assign_model_configs_to_endpoint(apps, schema_editor):
    """Assign all existing ModelConfigs to the first ModelEndpoint."""
    ModelEndpoint = apps.get_model('ml_platform', 'ModelEndpoint')
    ModelConfig = apps.get_model('ml_platform', 'ModelConfig')

    endpoint = ModelEndpoint.objects.first()
    if endpoint and ModelConfig.objects.filter(model_endpoint__isnull=True).exists():
        ModelConfig.objects.filter(model_endpoint__isnull=True).update(
            model_endpoint=endpoint
        )


def reverse_assign(apps, schema_editor):
    """No-op reverse: just leave the FK values in place (field will be removed)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0055_resourcemetrics_etl_jobs_completed_and_more'),
    ]

    operations = [
        # Step 1: Add nullable FK
        migrations.AddField(
            model_name='modelconfig',
            name='model_endpoint',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='model_configs',
                to='ml_platform.modelendpoint',
                help_text='The project this model config belongs to',
            ),
        ),

        # Step 2: Data migration
        migrations.RunPython(assign_model_configs_to_endpoint, reverse_assign),

        # Step 3: Make non-nullable
        migrations.AlterField(
            model_name='modelconfig',
            name='model_endpoint',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='model_configs',
                to='ml_platform.modelendpoint',
                help_text='The project this model config belongs to',
            ),
        ),

        # Step 4: Add unique_together constraint
        migrations.AlterUniqueTogether(
            name='modelconfig',
            unique_together={('model_endpoint', 'name')},
        ),
    ]
