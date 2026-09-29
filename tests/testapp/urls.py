from django.urls import path
from testapp import views

urlpatterns = [
    path("lazy_loop/", views.lazy_loop),
    path("async_lazy_loop/", views.async_lazy_loop),
    path("unused_select/", views.unused_select),
    path("unused_select_then_error/", views.unused_select_then_error),
    path("raw_sql_loop/", views.raw_sql_loop),
    path("prefetched_hobbies/", views.prefetched_hobbies),
]
