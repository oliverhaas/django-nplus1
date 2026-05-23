from django.db.models import prefetch_related_objects

from myapp.models import Book


class BookService:
    @staticmethod
    def book_get_author_name(*, book: Book) -> str:
        """Return the author name for a single book.

        This helper operates on a single instance and does not prefetch.
        Callers working with batches should prefetch before calling this
        in a loop, or use book_get_author_names() instead.
        """
        return book.author.name

    @staticmethod
    def book_get_author_names(*, books: list[Book]) -> list[str]:
        """Return author names for a batch of books.

        Fills in any missing author relations via prefetch_related_objects
        before the loop, so the caller doesn't need to prefetch.
        """
        prefetch_related_objects(books, "author")
        return [book.author.name for book in books]
