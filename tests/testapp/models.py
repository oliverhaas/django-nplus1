from django.db import models


class User(models.Model):
    hobbies = models.ManyToManyField("Hobby", related_name="users")

    class Meta:
        app_label = "testapp"


class Pet(models.Model):
    user = models.ForeignKey("User", on_delete=models.CASCADE)

    class Meta:
        app_label = "testapp"


class Allergy(models.Model):
    pets = models.ManyToManyField("Pet")

    class Meta:
        app_label = "testapp"


class Occupation(models.Model):
    user = models.OneToOneField("User", on_delete=models.CASCADE, related_name="occupation")

    class Meta:
        app_label = "testapp"


class Address(models.Model):
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="addresses")

    class Meta:
        app_label = "testapp"


class Hobby(models.Model):
    class Meta:
        app_label = "testapp"
