# Generated manually for Ranking model QuickTest support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0031_add_loss_function_to_modelconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='quicktest',
            name='rating_column',
            field=models.CharField(
                blank=True,
                help_text='Column name containing ratings/scores (required for ranking models)',
                max_length=255,
                null=True,
            ),
        ),
    ]
