from django.http import JsonResponse

from myapp.models import Book
from myapp.services import BookService


def book_list_bad(request):
    """N+1: fetches all books then accesses author on each without prefetching."""
    books = list(Book.objects.all())
    authors = [BookService.book_get_author_name(book=book) for book in books]
    return JsonResponse({"authors": authors})


def book_list_good(request):
    """Fixed: prefetches authors at the view layer."""
    books = list(Book.objects.select_related("author"))
    authors = [BookService.book_get_author_name(book=book) for book in books]
    return JsonResponse({"authors": authors})


def book_list_good_batch(request):
    """Fixed: uses batch service method which prefetches internally."""
    books = list(Book.objects.all())
    return JsonResponse({"authors": BookService.book_get_author_names(books=books)})
