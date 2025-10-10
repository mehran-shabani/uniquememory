from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "action",
                    models.CharField(
                        choices=[("create", "Create"), ("update", "Update"), ("delete", "Delete")],
                        max_length=12,
                    ),
                ),
                ("app_label", models.CharField(max_length=128)),
                ("model_name", models.CharField(max_length=128)),
                ("object_id", models.CharField(max_length=255)),
                (
                    "snapshot",
                    models.JSONField(
                        blank=True,
                        help_text="Serialized representation of the object state.",
                        null=True,
                    ),
                ),
                (
                    "changes",
                    models.JSONField(
                        blank=True,
                        help_text="Key/value changes captured during the operation.",
                        null=True,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["app_label", "model_name"], name="audit_audit_app_lab_9872a2_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["timestamp"], name="audit_audit_timesta_e86f3e_idx"),
        ),
    ]
