"""
Add category field to BillingSnapshot and backfill existing records.
"""
from django.db import migrations, models


CATEGORY_MAP = {
    'BigQuery': 'Data',
    'Cloud SQL': 'Data',
    'Cloud Dataflow': 'Data',
    'Cloud Storage': 'Data',
    'Vertex AI': 'Training',
}


def backfill_categories(apps, schema_editor):
    BillingSnapshot = apps.get_model('ml_platform', 'BillingSnapshot')
    for service_name, category in CATEGORY_MAP.items():
        BillingSnapshot.objects.filter(service_name=service_name).update(category=category)


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0060_update_machine_type_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingsnapshot',
            name='category',
            field=models.CharField(
                choices=[('Data', 'Data'), ('Training', 'Training'), ('Inference', 'Inference'), ('System', 'System')],
                db_index=True,
                default='System',
                help_text='Cost category (Data, Training, Inference, System)',
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_categories, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='billingsnapshot',
            unique_together={('date', 'category', 'service_name')},
        ),
    ]
