from django.urls import path

from myapp import views

urlpatterns = [
    path("books/bad/", views.book_list_bad),
    path("books/good/", views.book_list_good),
]
