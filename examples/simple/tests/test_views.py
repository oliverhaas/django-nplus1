"""
Example tests demonstrating django-nplus1 detection.

Tests marked with @pytest.mark.nplus1 will fail if the code under test
triggers an N+1 query. No pytest.raises needed -- the test simply fails,
telling you to fix the view.

Run with: pytest
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
    """Testing service methods that operate on single instances.

    book_get_author_name accesses book.author without prefetching.
    That's fine -- it's the caller's job to prefetch. In tests, we
    use nplus1_allow to suppress detection for the service layer
    and test the logic itself.
    """

    def test_single_book_with_allow(self, books):
        book = Book.objects.select_related("author").first()
        assert BookService.book_get_author_name(book=book) == "Author 0"

    def test_single_book_without_prefetch(self, books):
        """nplus1_allow in the test suppresses detection for the service call."""
        book = Book.objects.first()
        with nplus1_allow([{"model": "Book", "field": "author"}]):
            assert BookService.book_get_author_name(book=book) == "Author 0"

    def test_batch_is_always_safe(self, books):
        """book_get_author_names uses prefetch_related_objects internally."""
        all_books = list(Book.objects.all())
        names = BookService.book_get_author_names(books=all_books)
        assert len(names) == 3
