from asgiref.sync import sync_to_async
from django.db import connection
from django.http import HttpResponse
from django.template import engines
from testapp import models


def occupation_users():
    return [occupation.user.name for occupation in models.Occupation.objects.all()]


def lazy_loop(request):
    return HttpResponse(occupation_users())


async def async_lazy_loop(request):
    return HttpResponse(await sync_to_async(occupation_users)())


async def async_get_loop(request):
    names = []
    async for pk in models.User.objects.order_by("pk").values_list("pk", flat=True):
        user = await models.User.objects.aget(pk=pk)
        names.append(user.name)
    return HttpResponse(names)


async def async_two_users(request):
    alice = await models.User.objects.aget(name="alice")
    bob = await models.User.objects.aget(name="bob")
    return HttpResponse([alice.name, bob.name])


async def async_unused_select(request):
    return HttpResponse(len([user async for user in models.User.objects.select_related("occupation")]))


def lazy_loop_caught_by_template(request):
    template = engines["django"].from_string(
        '{% for occupation in occupations %}{% if occupation.user.name != "" %}{{ occupation.pk }}{% endif %}{% endfor %}',
    )
    return HttpResponse(template.render({"occupations": models.Occupation.objects.order_by("pk")}))


def unused_select(request):
    return HttpResponse(len(models.User.objects.select_related("occupation")))


def unused_select_then_error(request):
    list(models.User.objects.select_related("occupation"))
    raise ValueError("view failed")


def raw_sql_loop(request):
    names = []
    for pk in models.User.objects.values_list("pk", flat=True):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM testapp_user WHERE id = %s", [pk])
            names.append(cursor.fetchone()[0])
    return HttpResponse(names)


def prefetched_hobbies(request):
    users = models.User.objects.prefetch_related("hobbies")
    return HttpResponse(len([hobby for user in users for hobby in user.hobbies.all()]))
