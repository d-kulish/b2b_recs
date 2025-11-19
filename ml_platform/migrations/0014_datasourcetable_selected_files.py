# Generated manually for adding selected_files field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0013_datasourcetable_file_format_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasourcetable',
            name='selected_files',
            field=models.JSONField(blank=True, default=list, help_text='List of specific file paths selected by user to include in ETL (empty = use pattern only)'),
        ),
    ]
