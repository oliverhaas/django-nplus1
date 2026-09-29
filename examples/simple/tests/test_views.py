"""Example tests for django-nplus1.

A test marked with @pytest.mark.nplus1 fails when the code under test triggers an N+1 query,
and the error names the relation and the line that loaded it.
"""

import pytest
from myapp.models import Author, Book
from myapp.services import BookService

from django_nplus1 import nplus1_allow
from django_nplus1.exceptions import NPlus1Error


@pytest.fixture
def books(db):
    for i in range(3):
        author = Author.objects.create(name=f"Author {i}")
        Book.objects.create(title=f"Book {i}", author=author)


@pytest.mark.nplus1
@pytest.mark.django_db
class TestBookListGood:
    """These tests PASS because the views prefetch correctly."""

    def test_book_list(self, client, books):
        response = client.get("/books/good/")
        assert response.status_code == 200

    def test_book_list_batch(self, client, books):
        response = client.get("/books/good-batch/")
        assert response.status_code == 200


@pytest.mark.nplus1
@pytest.mark.django_db
class TestBookListBad:
    """This test FAILS because the view has an N+1 query.

    The xfail marker documents that this is a known broken view.
    Remove xfail after fixing the view with select_related.
    """

    @pytest.mark.xfail(raises=NPlus1Error, reason="view has N+1 on Book.author")
    def test_book_list(self, client, books):
        response = client.get("/books/bad/")
        assert response.status_code == 200


@pytest.mark.nplus1
@pytest.mark.django_db
class TestBookService:
    """book_get_author_name reads book.author and leaves prefetching to the caller.

    A row fetched on its own is never reported. Calling the helper for each row of a list is an N+1.
    """

    def test_single_book_with_select_related(self, books):
        book = Book.objects.select_related("author").first()
        assert BookService.book_get_author_name(book=book) == "Author 0"

    def test_single_book_without_prefetch(self, books):
        book = Book.objects.first()
        assert BookService.book_get_author_name(book=book) == "Author 0"

    def test_each_book_of_a_list_with_allow(self, books):
        """nplus1_allow suppresses the N+1 so the test can check the helper's logic."""
        with nplus1_allow([{"model": "Book", "field": "author"}]):
            names = [BookService.book_get_author_name(book=book) for book in Book.objects.order_by("pk")]
        assert names == ["Author 0", "Author 1", "Author 2"]

    def test_batch_is_always_safe(self, books):
        """book_get_author_names uses prefetch_related_objects internally."""
        all_books = list(Book.objects.all())
        names = BookService.book_get_author_names(books=all_books)
        assert len(names) == 3
