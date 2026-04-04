from collections import defaultdict
from unittest import mock

import pytest
from django.conf import settings

from django_nplus1 import signals
from django_nplus1.detect import LazyListener
from django_nplus1.signals import _listeners


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
    token = _listeners.set(defaultdict(list))
    calls = []

    def subscriber(args=None, kwargs=None, context=None, ret=None, parser=None):
        calls.append(parser(args, kwargs, context))

    signals.connect(signals.LAZY_LOAD, subscriber)
    yield calls
    signals.disconnect(signals.LAZY_LOAD, subscriber)
    _listeners.reset(token)


@pytest.fixture
def lazy_listener():
    token = _listeners.set(defaultdict(list))
    mock_parent = mock.Mock()
    listener = LazyListener(mock_parent)
    listener.setup()
    try:
        yield listener
    finally:
        listener.teardown()
        _listeners.reset(token)


@pytest.fixture
def logger(monkeypatch):
    mock_logger = mock.Mock()
    monkeypatch.setattr(settings, "NPLUS1_LOGGER", mock_logger)
    return mock_logger
