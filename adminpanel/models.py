from django.db import models

# Create your models here.
# models.py

from django.db import models
from django.contrib.auth.models import User

class SupportGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Subgroup(models.Model):
    group=models.ForeignKey(SupportGroup,on_delete=models.CASCADE,db_index=True)
    name=models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Category(models.Model):
    group = models.ForeignKey(SupportGroup, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.name