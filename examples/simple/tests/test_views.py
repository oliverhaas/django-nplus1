"""
Example tests demonstrating django-nplus1 detection.

Tests marked with @pytest.mark.nplus1 will fail if the code under test
triggers an N+1 query. No pytest.raises needed -- the test simply fails,
telling you to fix the view.

Run with: pytest
"""

import pytest
from myapp.models import Author, Book

from django_nplus1.exceptions import NPlus1Error


@pytest.fixture
def books(db):
    for i in range(3):
        author = Author.objects.create(name=f"Author {i}")
        Book.objects.create(title=f"Book {i}", author=author)


@pytest.mark.nplus1
@pytest.mark.django_db
class TestBookListGood:
    """These tests PASS because the view prefetches correctly."""

    def test_book_list(self, client, books):
        response = client.get("/books/good/")
        assert response.status_code == 200


@pytest.mark.nplus1
@pytest.mark.django_db
class TestBookListBad:
    """These tests FAIL because the view has an N+1 query.

    The xfail marker documents that this is a known broken view.
    Remove xfail after fixing the view with select_related.
    """

    @pytest.mark.xfail(raises=NPlus1Error, reason="view has N+1 on Book.author")
    def test_book_list(self, client, books):
        response = client.get("/books/bad/")
        assert response.status_code == 200
