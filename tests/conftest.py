from unittest import mock

import pytest
from django.conf import settings

from django_nplus1 import signals
from django_nplus1.detect import LazyListener


@pytest.fixture
def objects(db):
    from testapp.models import Address, Allergy, Hobby, Occupation, Pet, User

    user = User.objects.create()
    user2 = User.objects.create()
    pet = Pet.objects.create(user=user)
    Pet.objects.create(user=user2)
    allergy = Allergy.objects.create()
    allergy.pets.add(pet)
    Occupation.objects.create(user=user)
    Address.objects.create(user=user)
    hobby = Hobby.objects.create()
    user.hobbies.add(hobby)


@pytest.fixture
def calls():
    calls = []

    def subscriber(args=None, kwargs=None, context=None, ret=None, parser=None):
        calls.append(parser(args, kwargs, context))

    signals.connect(signals.LAZY_LOAD, subscriber, sender=signals.get_worker())
    yield calls
    signals.disconnect(signals.LAZY_LOAD, subscriber, sender=signals.get_worker())


@pytest.fixture
def lazy_listener():
    mock_parent = mock.Mock()
    listener = LazyListener(mock_parent)
    listener.setup()
    try:
        yield listener
    finally:
        listener.teardown()


@pytest.fixture
def logger(monkeypatch):
    mock_logger = mock.Mock()
    monkeypatch.setattr(settings, "NPLUS1_LOGGER", mock_logger)
    return mock_logger
