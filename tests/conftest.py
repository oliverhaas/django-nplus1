from unittest import mock

import pytest
from django.conf import settings
from testapp.models import Address, Allergy, Hobby, Occupation, Pet, User

from django_nplus1 import signals
from django_nplus1.detect import LazyListener
from django_nplus1.signals import setup_context, teardown_context


@pytest.fixture
def objects(db):
    user = User.objects.create()
    user2 = User.objects.create()
    pet = Pet.objects.create(user=user)
    Pet.objects.create(user=user2)
    allergy = Allergy.objects.create()
    allergy.pets.add(pet)
    Occupation.objects.create(user=user)
    Occupation.objects.create(user=user2)
    Address.objects.create(user=user)
    hobby = Hobby.objects.create()
    user.hobbies.add(hobby)


@pytest.fixture
def calls():
    token = setup_context()
    calls = []

    def subscriber(args=None, kwargs=None, context=None, ret=None, parser=None):
        calls.append(parser(args, kwargs, context))

    signals.connect(signals.LAZY_LOAD, subscriber)
    yield calls
    signals.disconnect(signals.LAZY_LOAD, subscriber)
    teardown_context(token)


@pytest.fixture
def lazy_listener():
    token = setup_context()
    mock_parent = mock.Mock()
    listener = LazyListener(mock_parent)
    listener.setup()
    try:
        yield listener
    finally:
        listener.teardown()
        teardown_context(token)


@pytest.fixture
def logger(monkeypatch):
    mock_logger = mock.Mock()
    monkeypatch.setattr(settings, "NPLUS1_LOGGER", mock_logger)
    return mock_logger
