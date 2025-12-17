# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0035_add_rolling_window_to_quicktest'),
    ]

    operations = [
        migrations.AddField(
            model_name='quicktest',
            name='machine_type',
            field=models.CharField(
                choices=[
                    ('n1-standard-4', 'Small (n1-standard-4: 4 vCPU, 15 GB)'),
                    ('n1-standard-8', 'Medium (n1-standard-8: 8 vCPU, 30 GB)'),
                    ('n1-standard-16', 'Large (n1-standard-16: 16 vCPU, 60 GB)'),
                ],
                default='n1-standard-4',
                help_text='Compute machine type for Trainer and Dataflow workers',
                max_length=50,
            ),
        ),
    ]
