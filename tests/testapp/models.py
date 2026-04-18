from django.db import models


class User(models.Model):
    name = models.CharField(max_length=100, default="")
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


class Region(models.Model):
    class Meta:
        app_label = "testapp"


class Store(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="stores")

    class Meta:
        app_label = "testapp"


class Company(models.Model):
    main_store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="main_companies",
    )
    backup_store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="backup_companies",
    )

    class Meta:
        app_label = "testapp"
