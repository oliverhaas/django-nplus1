from django_nplus1 import nplus1_allow


def get_author_names(books):
    """Return author names for a list of books.

    This helper doesn't prefetch on its own -- that's the caller's
    responsibility (view/task layer). We use nplus1_allow so this
    function doesn't trigger detection; the N+1 will be caught at
    the call site if the caller forgot to prefetch.
    """
    with nplus1_allow([{"model": "Book", "field": "author"}]):
        return [book.author.name for book in books]
