import os
from pathlib import Path

import pytest
from testapp.models import Address, Allergy, Company, Hobby, Occupation, Pet, Region, Store, Tag, User

from django_nplus1 import corpus, nplus1_detected

pytest_plugins = ["pytester"]


@pytest.fixture
def objects(db):
    hobbies = [Hobby.objects.create(), Hobby.objects.create()]
    users = []
    for name in ("alice", "bob"):
        user = User.objects.create(name=name)
        user.hobbies.add(*hobbies)
        Occupation.objects.create(user=user)
        Address.objects.create(user=user)
        Allergy.objects.create().pets.add(Pet.objects.create(user=user))
        Tag.objects.create(label=name, content_object=user)
        users.append(user)
    return users


@pytest.fixture
def shared_fk_objects(db):
    main = Store.objects.create(region=Region.objects.create())
    backup = Store.objects.create(region=Region.objects.create())
    return Company.objects.create(main_store=main, backup_store=backup)


@pytest.fixture
def detected():
    messages = []

    def receiver(sender, message, **kwargs):
        messages.append(message)

    nplus1_detected.connect(receiver)
    yield messages
    nplus1_detected.disconnect(receiver)


@pytest.fixture
def corpus_mode():
    corpus.activate()
    yield corpus
    corpus.deactivate()
    for tracker in corpus.TRACKERS.values():
        tracker.reset()


@pytest.fixture
def django_pytester(pytester, monkeypatch):
    """pytester whose subprocess runs can import testapp and settings.base."""
    tests_dir = str(Path(__file__).parent.resolve())
    existing = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([tests_dir, existing]) if existing else tests_dir)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "settings.base")
    return pytester
