from django.db import models

# Create your models here.
# models.py

from django.db import models
from django.contrib.auth.models import User

class SupportGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
