from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    phone = models.CharField(max_length=20)
    is_driver = models.BooleanField(default=False)

    # Add related_name to avoid clashes with default User model
    groups = models.ManyToManyField(
        Group,
        verbose_name=_('groups'),
        blank=True,
        related_name='custom_user_set',  # Change 'custom_user_set' to your desired related name
        help_text=_(
            'The groups this user belongs to. '
            'A user will get all permissions granted to each of their groups.'
        ),
        related_query_name='user',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_('user permissions'),
        blank=True,
        related_name='custom_user_set',  # Change 'custom_user_set' to your desired related name
        help_text='Specific permissions for this user.',
        related_query_name='user',
    )

    def __str__(self):
        return self.username

class Driver(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, primary_key=True, related_name='driver_profile')

    license_number = models.CharField(max_length=50, blank=True, null=True)
    number_plate = models.CharField(max_length=50,blank=True, null=True)
    number_plate = models.CharField(max_length=50, blank=True, null=True)  # New field
    car_name = models.CharField(max_length=100, blank=True, null=True)  # New field
    AMBULANCE_TYPE_CHOICES = [
        ('med_bls', 'Med BLS'),
        ('med_als', 'Med ALS'),
        ('med_icu', 'Med ICU'),
    ]
    ambulance_type = models.CharField(max_length=10, choices=AMBULANCE_TYPE_CHOICES, blank=True, null=True)
    rating_total = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, blank=True, null=True)
    rating_count = models.PositiveIntegerField(default=0, blank=True, null=True)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)  # This saves images to 'media/profile_images/'

    def __str__(self):
        return self.license_number

    @property
    def average_rating(self):
        # Return None if there are no ratings
        if self.rating_count == 0:
            return None
        return round(self.rating_total / self.rating_count, 2)



