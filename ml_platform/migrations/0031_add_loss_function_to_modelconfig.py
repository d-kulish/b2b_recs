# Generated manually for Ranking model config support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0030_remove_trainer_code_add_model_config_to_quicktest'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelconfig',
            name='loss_function',
            field=models.CharField(
                choices=[
                    ('mse', 'Mean Squared Error'),
                    ('binary_crossentropy', 'Binary Crossentropy'),
                    ('huber', 'Huber'),
                ],
                default='mse',
                help_text='Loss function for ranking models (MSE for continuous ratings, BCE for binary)',
                max_length=30,
            ),
        ),
    ]
