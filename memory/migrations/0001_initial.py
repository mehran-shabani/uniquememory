from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MemoryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField()),
                (
                    "sensitivity",
                    models.CharField(
                        choices=[
                            ("public", "Public"),
                            ("confidential", "Confidential"),
                            ("secret", "Secret"),
                        ],
                        default="public",
                        max_length=32,
                    ),
                ),
                (
                    "entry_type",
                    models.CharField(
                        choices=[
                            ("fact", "Fact"),
                            ("event", "Event"),
                            ("note", "Note"),
                        ],
                        default="note",
                        max_length=32,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-updated_at", "title"],
            },
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(fields=["sensitivity"], name="memory_memo_sensiti_4f9d62_idx"),
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(fields=["entry_type"], name="memory_memo_entry_t_dcf4c1_idx"),
        ),
    ]
