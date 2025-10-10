# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("memory", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Embedding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vector", models.JSONField(help_text="Dense vector representing the entry content.")),
                ("model_name", models.CharField(max_length=255)),
                ("dimension", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "memory_entry",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="embedding",
                        to="memory.memoryentry",
                    ),
                ),
            ],
            options={
                "verbose_name": "Embedding",
                "verbose_name_plural": "Embeddings",
            },
        ),
        migrations.AddIndex(
            model_name="embedding",
            index=models.Index(fields=["model_name"], name="embeddings_model_name_8755f4_idx"),
        ),
    ]
