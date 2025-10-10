from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("memory", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntryChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(help_text="Ordering of the chunk inside the entry.")),
                ("content", models.TextField()),
                (
                    "embedding",
                    models.JSONField(blank=True, help_text="Vector representation of the chunk.", null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "memory_entry",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="chunks",
                        to="memory.memoryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["memory_entry", "position"],
                "unique_together": {("memory_entry", "position")},
            },
        ),
    ]
