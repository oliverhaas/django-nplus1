"""
Example tests demonstrating django-nplus1 detection.

The django_nplus1 pytest plugin provides @pytest.mark.nplus1 which
automatically detects N+1 queries in your tests. Any detection raises
NPlus1Error.

Run with: pytest
"""

import pytest
from myapp.models import Author, Book
from myapp.views import get_book_authors_allowed, get_book_authors_bad, get_book_authors_good

from django_nplus1.exceptions import NPlus1Error


@pytest.fixture
def books(db):
    for i in range(3):
        author = Author.objects.create(name=f"Author {i}")
        Book.objects.create(title=f"Book {i}", author=author)


@pytest.mark.nplus1
@pytest.mark.django_db
class TestBookAuthors:
    def test_nplus1_detected(self, books):
        """This test FAILS because get_book_authors_bad triggers N+1.

        With @pytest.mark.nplus1 on the class, N+1 queries automatically
        raise NPlus1Error.
        """
        with pytest.raises(NPlus1Error, match="Book.author"):
            books = list(Book.objects.all())
            get_book_authors_bad(books)

    def test_no_nplus1_with_select_related(self, books):
        """This test PASSES because select_related avoids N+1."""
        books = list(Book.objects.select_related("author"))
        get_book_authors_good(books)

    def test_nplus1_allowed(self, books):
        """This test PASSES because nplus1_allow suppresses the known N+1."""
        books = list(Book.objects.all())
        get_book_authors_allowed(books)
