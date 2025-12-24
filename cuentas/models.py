import uuid
from django.db import models
from django.contrib.auth.models import User

class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")

    email = models.EmailField()
    password_encrypted = models.TextField()
    secret_encrypted = models.TextField(blank=True, null=True)

    site_url = models.URLField(blank=True, null=True)
    site_name = models.CharField(max_length=100, blank=True, null=True)
    site_icon_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.site_name or self.email}"
