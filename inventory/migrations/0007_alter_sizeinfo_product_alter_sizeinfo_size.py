# Generated by Django 5.2.1 on 2025-08-02 11:11

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_alter_sizeinfo_size'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sizeinfo',
            name='product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='size', to='inventory.product', verbose_name='Продукт'),
        ),
        migrations.AlterField(
            model_name='sizeinfo',
            name='size',
            field=models.CharField(max_length=50, verbose_name='Размер'),
        ),
    ]
