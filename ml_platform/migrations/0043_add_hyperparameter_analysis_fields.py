# Generated manually for hyperparameter analysis fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', '0042_add_training_history_cache'),
    ]

    operations = [
        # From ModelConfig - Training params
        migrations.AddField(
            model_name='quicktest',
            name='optimizer',
            field=models.CharField(blank=True, help_text='Optimizer algorithm (denormalized from ModelConfig)', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='output_embedding_dim',
            field=models.IntegerField(blank=True, help_text='Dimension of final tower embeddings (denormalized from ModelConfig)', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='retrieval_algorithm',
            field=models.CharField(blank=True, help_text='Algorithm for top-K retrieval (denormalized from ModelConfig)', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='top_k',
            field=models.IntegerField(blank=True, help_text='Number of top candidates to retrieve (denormalized from ModelConfig)', null=True),
        ),
        # From ModelConfig - Architecture (derived)
        migrations.AddField(
            model_name='quicktest',
            name='buyer_tower_structure',
            field=models.CharField(blank=True, help_text="Buyer tower structure e.g. '128→64→32' (derived from ModelConfig)", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_tower_structure',
            field=models.CharField(blank=True, help_text="Product tower structure e.g. '128→64→32' (derived from ModelConfig)", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='buyer_activation',
            field=models.CharField(blank=True, help_text='Primary activation function in buyer tower', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_activation',
            field=models.CharField(blank=True, help_text='Primary activation function in product tower', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='buyer_l2_category',
            field=models.CharField(blank=True, choices=[('none', 'None (0)'), ('light', 'Light (0.0001-0.001)'), ('medium', 'Medium (0.001-0.01)'), ('heavy', 'Heavy (>0.01)')], help_text='L2 regularization category for buyer tower', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_l2_category',
            field=models.CharField(blank=True, choices=[('none', 'None (0)'), ('light', 'Light (0.0001-0.001)'), ('medium', 'Medium (0.001-0.01)'), ('heavy', 'Heavy (>0.01)')], help_text='L2 regularization category for product tower', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='buyer_total_params',
            field=models.IntegerField(blank=True, help_text='Estimated trainable params in buyer tower', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_total_params',
            field=models.IntegerField(blank=True, help_text='Estimated trainable params in product tower', null=True),
        ),
        # From FeatureConfig
        migrations.AddField(
            model_name='quicktest',
            name='buyer_tensor_dim',
            field=models.IntegerField(blank=True, help_text='Total tensor dimensions for BuyerModel (denormalized from FeatureConfig)', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_tensor_dim',
            field=models.IntegerField(blank=True, help_text='Total tensor dimensions for ProductModel (denormalized from FeatureConfig)', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='buyer_feature_count',
            field=models.IntegerField(blank=True, help_text='Number of columns in buyer tower', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_feature_count',
            field=models.IntegerField(blank=True, help_text='Number of columns in product tower', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='buyer_cross_count',
            field=models.IntegerField(blank=True, help_text='Number of cross features in buyer tower', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='product_cross_count',
            field=models.IntegerField(blank=True, help_text='Number of cross features in product tower', null=True),
        ),
        # From Dataset (via FeatureConfig)
        migrations.AddField(
            model_name='quicktest',
            name='dataset_row_count',
            field=models.IntegerField(blank=True, help_text='Estimated row count of dataset', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='dataset_date_range_days',
            field=models.IntegerField(blank=True, help_text='Number of days in dataset date range', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='dataset_unique_users',
            field=models.IntegerField(blank=True, help_text='Estimated unique users in dataset', null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='dataset_unique_products',
            field=models.IntegerField(blank=True, help_text='Estimated unique products in dataset', null=True),
        ),
    ]
