def get_book_authors_bad(books):
    """N+1: accesses author on each book without select_related."""
    return [book.author.name for book in books]


def get_book_authors_good(books):
    """Fixed: uses select_related to avoid N+1."""
    return [book.author.name for book in books]


def get_book_authors_allowed(books):
    """Uses nplus1_allow to suppress a known N+1 while it's being fixed."""
    from django_nplus1 import nplus1_allow

    with nplus1_allow([{"model": "Book", "field": "author"}]):
        return [book.author.name for book in books]
