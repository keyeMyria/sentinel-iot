# Generated by Django 2.0.2 on 2018-06-23 05:37

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Action',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_uuid', models.CharField(max_length=36)),
                ('target_device', models.CharField(max_length=36)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='Condition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('previously_satisfied', models.BooleanField(default=False)),
            ],
            options={
                'permissions': (('view_condition', 'View Condition'),),
            },
        ),
        migrations.CreateModel(
            name='Datastore',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('last_updated', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'permissions': (('view_datastore', 'Can view the datastore'),),
            },
        ),
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('is_input', models.BooleanField(default=True)),
                ('mode', models.CharField(choices=[('IN', 'Input'), ('OUT', 'Output')], max_length=3)),
            ],
        ),
        migrations.CreateModel(
            name='Hub',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
            ],
            options={
                'permissions': (('view_hub', 'View Hub'),),
            },
        ),
        migrations.CreateModel(
            name='Leaf',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('model', models.CharField(max_length=100)),
                ('uuid', models.CharField(max_length=36)),
                ('api_version', models.CharField(default='0.1.0', max_length=10)),
                ('is_connected', models.BooleanField(default=True)),
                ('last_connected', models.DateTimeField()),
                ('last_updated', models.DateTimeField(default=django.utils.timezone.now)),
                ('hub', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leaves', to='hub.Hub')),
            ],
            options={
                'permissions': (('view_leaf', 'View Leaf'),),
            },
        ),
        migrations.CreateModel(
            name='Predicate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subscriber_uuid', models.CharField(blank=True, max_length=36, null=True)),
                ('target_uuid', models.CharField(max_length=36)),
                ('target_device', models.CharField(max_length=100)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='Value',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='BooleanValue',
            fields=[
                ('value_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Value')),
                ('value', models.BooleanField()),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.value',),
        ),
        migrations.CreateModel(
            name='ChangeAction',
            fields=[
                ('action_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Action')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.action',),
        ),
        migrations.CreateModel(
            name='ComparatorPredicate',
            fields=[
                ('predicate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Predicate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.predicate',),
        ),
        migrations.CreateModel(
            name='ConditionalSubscription',
            fields=[
                ('subscription_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Subscription')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.subscription',),
        ),
        migrations.CreateModel(
            name='Multivariate',
            fields=[
                ('predicate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Predicate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.predicate',),
        ),
        migrations.CreateModel(
            name='NOT',
            fields=[
                ('predicate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Predicate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.predicate',),
        ),
        migrations.CreateModel(
            name='NumberValue',
            fields=[
                ('value_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Value')),
                ('value', models.DecimalField(decimal_places=4, max_digits=15)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.value',),
        ),
        migrations.CreateModel(
            name='SetAction',
            fields=[
                ('action_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Action')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.action',),
        ),
        migrations.CreateModel(
            name='StringValue',
            fields=[
                ('value_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Value')),
                ('value', models.CharField(max_length=250)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.value',),
        ),
        migrations.CreateModel(
            name='UnitValue',
            fields=[
                ('value_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Value')),
                ('value', models.DecimalField(decimal_places=4, max_digits=15)),
                ('units', models.CharField(max_length=10)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.value',),
        ),
        migrations.AddField(
            model_name='value',
            name='polymorphic_ctype',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_hub.value_set+', to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='subscription',
            name='hub',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='hub.Hub'),
        ),
        migrations.AddField(
            model_name='subscription',
            name='polymorphic_ctype',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_hub.subscription_set+', to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='predicate',
            name='polymorphic_ctype',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_hub.predicate_set+', to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='device',
            name='_value',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='device', to='hub.Value'),
        ),
        migrations.AddField(
            model_name='device',
            name='leaf',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='devices', to='hub.Leaf'),
        ),
        migrations.AddField(
            model_name='datastore',
            name='_value',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='datastore', to='hub.Value'),
        ),
        migrations.AddField(
            model_name='datastore',
            name='hub',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='datastores', to='hub.Hub'),
        ),
        migrations.AddField(
            model_name='condition',
            name='hub',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conditions', to='hub.Hub'),
        ),
        migrations.AddField(
            model_name='condition',
            name='predicate',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='condition', to='hub.Predicate'),
        ),
        migrations.AddField(
            model_name='action',
            name='_value',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='hub.Value'),
        ),
        migrations.AddField(
            model_name='action',
            name='condition',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='hub.Condition'),
        ),
        migrations.AddField(
            model_name='action',
            name='polymorphic_ctype',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_hub.action_set+', to='contenttypes.ContentType'),
        ),
        migrations.CreateModel(
            name='AND',
            fields=[
                ('multivariate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Multivariate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.multivariate',),
        ),
        migrations.CreateModel(
            name='EqualPredicate',
            fields=[
                ('comparatorpredicate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.ComparatorPredicate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.comparatorpredicate',),
        ),
        migrations.CreateModel(
            name='GreaterThanPredicate',
            fields=[
                ('comparatorpredicate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.ComparatorPredicate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.comparatorpredicate',),
        ),
        migrations.CreateModel(
            name='LessThanPredicate',
            fields=[
                ('comparatorpredicate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.ComparatorPredicate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.comparatorpredicate',),
        ),
        migrations.CreateModel(
            name='OR',
            fields=[
                ('multivariate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Multivariate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.multivariate',),
        ),
        migrations.CreateModel(
            name='XOR',
            fields=[
                ('multivariate_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='hub.Multivariate')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('hub.multivariate',),
        ),
        migrations.AddField(
            model_name='predicate',
            name='operator',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='operands', to='hub.Multivariate'),
        ),
        migrations.AddField(
            model_name='not',
            name='predicate',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='not+', to='hub.Predicate'),
        ),
        migrations.AlterUniqueTogether(
            name='leaf',
            unique_together={('uuid', 'hub')},
        ),
        migrations.AlterUniqueTogether(
            name='device',
            unique_together={('name', 'leaf')},
        ),
        migrations.AlterUniqueTogether(
            name='datastore',
            unique_together={('name', 'hub')},
        ),
        migrations.AddField(
            model_name='conditionalsubscription',
            name='condition',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='hub.Condition'),
        ),
        migrations.AlterUniqueTogether(
            name='condition',
            unique_together={('name', 'hub')},
        ),
        migrations.AddField(
            model_name='comparatorpredicate',
            name='first_value',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='first', to='hub.Value'),
        ),
        migrations.AddField(
            model_name='comparatorpredicate',
            name='second_value',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='second', to='hub.Value'),
        ),
    ]
