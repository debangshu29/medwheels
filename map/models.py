# In map/models.py

from django.db import models
from django.contrib.auth import get_user_model
from uuid import uuid4
import uuid

from verify.models import Driver
User = get_user_model()

class DriverLocation(models.Model):
    driver = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_location')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_name = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Location of {self.driver.username}"


class Ride(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE)  # Update this line
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pickup = models.CharField(max_length=255)
    drop = models.CharField(max_length=255)
    estimated_time = models.CharField(max_length=50, blank=True, null=True)
    estimated_distance = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_confirmed = models.BooleanField(default=False)
    token = models.CharField(max_length=32, unique=True, default=uuid.uuid4().hex[:16])
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    drop_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    drop_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    fare = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ambulance_type = models.CharField(max_length=50,blank=True, null=True)
    code = models.CharField(max_length=4, unique=True, blank=True, null=True)
    is_verified = models.BooleanField(default=False, blank=True, null=True)

    def __str__(self):
        return f"Ride from {self.pickup} to {self.drop}"

    def save(self, *args, **kwargs):
        if not self.pk and not self.code:
            self.code = self._generate_unique_code()
        super().save(*args, **kwargs)

    def _generate_unique_code(self):
        """
        Generates a unique 4-digit code for the ride.
        """
        code = None
        while not code or Ride.objects.filter(code=code).exists():
            code = uuid4().hex[:4].upper()
        return code