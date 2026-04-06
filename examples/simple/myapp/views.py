from django.http import JsonResponse

from myapp.models import Book
from myapp.services import get_author_names


def book_list_bad(request):
    """N+1: fetches all books then accesses author on each without prefetching."""
    books = list(Book.objects.all())
    # Accessing author directly here triggers N+1
    authors = [book.author.name for book in books]
    return JsonResponse({"authors": authors})


def book_list_good(request):
    """Fixed: prefetches authors at the view layer, then delegates to service."""
    books = list(Book.objects.select_related("author"))
    return JsonResponse({"authors": get_author_names(books)})
