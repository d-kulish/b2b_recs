"""
Migration to remove deployment status fields.

Deployment status is now dynamically queried from Vertex AI endpoint,
so these database fields are no longer needed.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0008_add_vertex_pipeline_job_id_to_trainingrun'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trainingrun',
            name='is_deployed',
        ),
        migrations.RemoveField(
            model_name='trainingrun',
            name='deployed_at',
        ),
        migrations.RemoveField(
            model_name='trainingrun',
            name='endpoint_resource_name',
        ),
        migrations.RemoveField(
            model_name='registeredmodel',
            name='is_deployed',
        ),
        migrations.RemoveField(
            model_name='registeredmodel',
            name='deployed_version_id',
        ),
    ]
