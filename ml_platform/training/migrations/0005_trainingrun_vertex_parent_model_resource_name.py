# Generated migration for adding vertex_parent_model_resource_name field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0004_add_schedule_config_to_training_run'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingrun',
            name='vertex_parent_model_resource_name',
            field=models.CharField(
                blank=True,
                help_text='Parent model resource name for Vertex AI versioning',
                max_length=500,
            ),
        ),
    ]
