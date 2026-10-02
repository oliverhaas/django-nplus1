from django.urls import path
from testapp import views

urlpatterns = [
    path("lazy_loop/", views.lazy_loop),
    path("async_lazy_loop/", views.async_lazy_loop),
    path("async_get_loop/", views.async_get_loop),
    path("async_two_users/", views.async_two_users),
    path("async_unused_select/", views.async_unused_select),
    path("lazy_loop_caught_by_template/", views.lazy_loop_caught_by_template),
    path("unused_select/", views.unused_select),
    path("unused_select_then_error/", views.unused_select_then_error),
    path("raw_sql_loop/", views.raw_sql_loop),
    path("prefetched_hobbies/", views.prefetched_hobbies),
]
