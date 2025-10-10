from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("memory", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "access_level",
                    models.CharField(
                        choices=[("read", "Read"), ("write", "Write"), ("admin", "Admin")],
                        default="read",
                        max_length=16,
                    ),
                ),
                (
                    "allowed_roles",
                    models.JSONField(blank=True, default=list, help_text="List of roles allowed to use this entry."),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "memory_entry",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="access_policies",
                        to="memory.memoryentry",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "verbose_name_plural": "Access policies",
            },
        ),
        migrations.AddField(
            model_name="accesspolicy",
            name="allowed_users",
            field=models.ManyToManyField(blank=True, related_name="memory_access_policies", to=settings.AUTH_USER_MODEL),
        ),
    ]
