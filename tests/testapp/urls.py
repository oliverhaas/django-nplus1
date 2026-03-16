from django.urls import path
from testapp import views

urlpatterns = [
    path("one_to_one/", views.one_to_one),
    path("one_to_one_first/", views.one_to_one_first),
    path("one_to_many/", views.one_to_many),
    path("many_to_many/", views.many_to_many),
    path("many_to_many_get/", views.many_to_many_get),
    path("prefetch_one_to_one/", views.prefetch_one_to_one),
    path("prefetch_one_to_one_unused/", views.prefetch_one_to_one_unused),
    path("prefetch_many_to_many/", views.prefetch_many_to_many),
    path("many_to_many_impossible/", views.many_to_many_impossible),
    path("many_to_many_impossible_one/", views.many_to_many_impossible_one),
    path("prefetch_many_to_many_render/", views.prefetch_many_to_many_render),
    path("prefetch_many_to_many_unused/", views.prefetch_many_to_many_unused),
    path("prefetch_many_to_many_single/", views.prefetch_many_to_many_single),
    path("prefetch_many_to_many_no_related/", views.prefetch_many_to_many_no_related),
    path("select_one_to_one/", views.select_one_to_one),
    path("select_one_to_one_unused/", views.select_one_to_one_unused),
    path("select_many_to_one/", views.select_many_to_one),
    path("select_many_to_one_unused/", views.select_many_to_one_unused),
    path("prefetch_nested/", views.prefetch_nested),
    path("prefetch_nested_unused/", views.prefetch_nested_unused),
    path("select_nested/", views.select_nested),
    path("select_nested_unused/", views.select_nested_unused),
]
