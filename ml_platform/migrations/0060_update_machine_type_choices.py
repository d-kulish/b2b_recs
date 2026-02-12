# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0059_billing_models'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quicktest',
            name='machine_type',
            field=models.CharField(
                choices=[
                    ('e2-standard-4', 'Small (e2-standard-4: 4 vCPU, 16 GB)'),
                    ('e2-standard-8', 'Medium (e2-standard-8: 8 vCPU, 32 GB)'),
                    ('e2-standard-16', 'Large (e2-standard-16: 16 vCPU, 64 GB)'),
                ],
                default='e2-standard-4',
                help_text='Compute machine type for Dataflow workers (BigQueryExampleGen, StatisticsGen, Transform)',
                max_length=50,
            ),
        ),
    ]
