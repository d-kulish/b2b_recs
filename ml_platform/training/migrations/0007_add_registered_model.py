# Generated manually for RegisteredModel entity

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_registered_models_from_training_runs(apps, schema_editor):
    """
    Create RegisteredModel entries from existing TrainingRuns that have been
    registered to Vertex AI Model Registry.

    Groups TrainingRuns by vertex_model_name and creates one RegisteredModel per group.
    Links all TrainingRuns in the group to the same RegisteredModel.
    """
    RegisteredModel = apps.get_model('training', 'RegisteredModel')
    TrainingRun = apps.get_model('training', 'TrainingRun')

    # Get all training runs that have been registered to Vertex AI
    registered_runs = TrainingRun.objects.filter(
        vertex_model_resource_name__isnull=False
    ).exclude(
        vertex_model_resource_name=''
    ).order_by('registered_at')

    # Group by (ml_model_id, vertex_model_name)
    model_groups = {}
    for run in registered_runs:
        # Use the name field if vertex_model_name is empty
        model_name = run.vertex_model_name or run.name
        if not model_name:
            continue

        key = (run.ml_model_id, model_name)
        if key not in model_groups:
            model_groups[key] = []
        model_groups[key].append(run)

    # Create RegisteredModel for each group
    for (ml_model_id, model_name), runs in model_groups.items():
        # Find the first and latest runs
        first_run = runs[0]
        latest_run = runs[-1]

        # Count deployed versions
        deployed_run = None
        for run in runs:
            if run.is_deployed:
                deployed_run = run
                break

        registered_model = RegisteredModel.objects.create(
            ml_model_id=ml_model_id,
            model_name=model_name,
            model_type=first_run.model_type,
            description=first_run.description or '',
            vertex_model_resource_name=latest_run.vertex_model_resource_name,
            first_registered_at=first_run.registered_at,
            latest_version_id=latest_run.id,
            latest_version_number=latest_run.vertex_model_version or '',
            total_versions=len(runs),
            is_deployed=deployed_run is not None,
            deployed_version_id=deployed_run.id if deployed_run else None,
            is_active=True,
            created_by_id=first_run.created_by_id,
        )

        # Link all runs to this RegisteredModel
        for run in runs:
            run.registered_model = registered_model
            run.save(update_fields=['registered_model'])


def link_schedules_to_registered_models(apps, schema_editor):
    """
    Link existing TrainingSchedules to RegisteredModels.

    If a schedule has created training runs, use the RegisteredModel from those runs.
    Otherwise, create a new RegisteredModel based on the schedule name.
    """
    RegisteredModel = apps.get_model('training', 'RegisteredModel')
    TrainingSchedule = apps.get_model('training', 'TrainingSchedule')
    TrainingRun = apps.get_model('training', 'TrainingRun')

    for schedule in TrainingSchedule.objects.all():
        # Check if any training runs from this schedule have a registered_model
        runs_with_model = TrainingRun.objects.filter(
            schedule=schedule,
            registered_model__isnull=False
        ).first()

        if runs_with_model and runs_with_model.registered_model:
            # Use existing RegisteredModel
            schedule.registered_model = runs_with_model.registered_model
            schedule.save(update_fields=['registered_model'])
        else:
            # Create a new RegisteredModel from schedule
            # Use schedule name as model name
            model_name = schedule.name

            # Check if a RegisteredModel with this name already exists
            existing = RegisteredModel.objects.filter(
                ml_model_id=schedule.ml_model_id,
                model_name=model_name
            ).first()

            if existing:
                schedule.registered_model = existing
            else:
                # Create new RegisteredModel
                registered_model = RegisteredModel.objects.create(
                    ml_model_id=schedule.ml_model_id,
                    model_name=model_name,
                    model_type='retrieval',  # Default type
                    description=schedule.description or '',
                    is_active=True,
                    created_by_id=schedule.created_by_id,
                )
                schedule.registered_model = registered_model

            schedule.save(update_fields=['registered_model'])


def reverse_data_migration(apps, schema_editor):
    """Reverse the data migration by unlinking schedules and runs."""
    TrainingSchedule = apps.get_model('training', 'TrainingSchedule')
    TrainingRun = apps.get_model('training', 'TrainingRun')

    TrainingSchedule.objects.update(registered_model=None)
    TrainingRun.objects.update(registered_model=None)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('training', '0006_add_hourly_monthly_schedule_types'),
    ]

    operations = [
        # Step 1: Create RegisteredModel table
        migrations.CreateModel(
            name='RegisteredModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('model_name', models.CharField(help_text='Model name (becomes vertex_model_name when registered)', max_length=255)),
                ('model_type', models.CharField(choices=[('retrieval', 'Retrieval'), ('ranking', 'Ranking'), ('multitask', 'Multitask')], default='retrieval', help_text='Type of model (retrieval, ranking, multitask)', max_length=20)),
                ('description', models.TextField(blank=True, help_text='Optional description of the model')),
                ('vertex_model_resource_name', models.CharField(blank=True, help_text='Full Vertex AI Model resource name (after first registration)', max_length=500)),
                ('first_registered_at', models.DateTimeField(blank=True, help_text='When the first version was registered to Vertex AI', null=True)),
                ('latest_version_id', models.IntegerField(blank=True, help_text='ID of the latest TrainingRun version', null=True)),
                ('latest_version_number', models.CharField(blank=True, help_text='Version string of the latest version', max_length=100)),
                ('total_versions', models.IntegerField(default=0, help_text='Total number of registered versions')),
                ('is_deployed', models.BooleanField(default=False, help_text='Whether any version of this model is currently deployed')),
                ('deployed_version_id', models.IntegerField(blank=True, help_text='ID of the currently deployed TrainingRun version', null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this model is active (not archived)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, help_text='User who created this model entry', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_registered_models', to=settings.AUTH_USER_MODEL)),
                ('ml_model', models.ForeignKey(help_text='Parent model endpoint this registered model belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='registered_models', to='ml_platform.modelendpoint')),
            ],
            options={
                'verbose_name': 'Registered Model',
                'verbose_name_plural': 'Registered Models',
                'ordering': ['-created_at'],
            },
        ),

        # Step 2: Add unique constraint
        migrations.AddConstraint(
            model_name='registeredmodel',
            constraint=models.UniqueConstraint(fields=['ml_model', 'model_name'], name='unique_ml_model_model_name'),
        ),

        # Step 3: Add registered_model FK to TrainingRun
        migrations.AddField(
            model_name='trainingrun',
            name='registered_model',
            field=models.ForeignKey(blank=True, help_text='Registered model this run is a version of', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='versions', to='training.registeredmodel'),
        ),

        # Step 4: Add registered_model OneToOne to TrainingSchedule
        migrations.AddField(
            model_name='trainingschedule',
            name='registered_model',
            field=models.OneToOneField(blank=True, help_text='Registered model this schedule creates versions for', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='schedule', to='training.registeredmodel'),
        ),

        # Step 5: Data migration - create RegisteredModels from existing TrainingRuns
        migrations.RunPython(
            create_registered_models_from_training_runs,
            reverse_code=reverse_data_migration,
        ),

        # Step 6: Data migration - link schedules to RegisteredModels
        migrations.RunPython(
            link_schedules_to_registered_models,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
