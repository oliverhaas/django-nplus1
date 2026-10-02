import asyncio
import threading
from pathlib import Path

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.db import connections
from testapp.models import User

from django_nplus1 import DetectionContext, Profiler

pytestmark = pytest.mark.django_db


async def read_pets_of_each_user():
    return [[pet async for pet in user.pet_set.all()] async for user in User.objects.all()]


async def read_pets_of_each_iterated_user():
    return [[pet async for pet in user.pet_set.all()] async for user in User.objects.aiterator()]


async def read_prefetched_pets_of_iterated_users():
    return [list(user.pet_set.all()) async for user in User.objects.prefetch_related("pet_set").aiterator()]


async def get_each(pks):
    return [await User.objects.aget(pk=pk) for pk in pks]


@pytest.mark.parametrize("load", [read_pets_of_each_user, read_pets_of_each_iterated_user], ids=["for", "aiterator"])
def test_per_row_load_is_detected(objects, detected, load):
    with DetectionContext():
        async_to_sync(load)()
    assert [(m.label, m.model, m.field) for m in detected] == [("n_plus_one", User, "pet_set")]


def test_prefetch_of_aiterator_rows_is_used(objects):
    with Profiler():
        async_to_sync(read_prefetched_pets_of_iterated_users)()


@pytest.mark.django_db(transaction=True)
def test_get_in_loop_in_an_event_loop_thread_is_detected(objects, detected):
    pks = [user.pk for user in objects]

    async def serve():
        try:
            with DetectionContext():
                await get_each(pks)
        finally:
            await sync_to_async(connections.close_all)()

    thread = threading.Thread(target=asyncio.run, args=(serve(),))
    thread.start()
    thread.join()
    assert [(m.label, m.caller[2]) for m in detected] == [("get_in_loop", "get_each")]


@pytest.mark.parametrize("use_async_client", [False, True], ids=["sync-client", "async-client"])
def test_async_view_gets_on_different_lines_pass(objects, client, async_client, settings, use_async_client):
    settings.NPLUS1_RAISE = True
    get = async_to_sync(async_client.get) if use_async_client else client.get
    response = get("/async_two_users/")
    assert response.status_code == 200
    assert response.content == b"alicebob"


def test_async_view_get_in_loop_points_at_the_view(objects, async_client, settings):
    settings.NPLUS1_WARN = True
    with pytest.warns(UserWarning, match=r"User\.get\(\)") as record:
        async_to_sync(async_client.get)("/async_get_loop/")
    assert [Path(w.filename).name for w in record if "get()" in str(w.message)] == ["views.py"]
