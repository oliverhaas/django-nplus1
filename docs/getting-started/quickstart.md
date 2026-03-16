# Quick Start

## Basic Usage

After [installation](installation.md), the middleware will automatically detect N+1 queries during request handling and log warnings.

### Example N+1 Query

```python
# This triggers a warning:
users = list(User.objects.all())
for user in users:
    print(user.profile)  # N+1! Each access triggers a separate query
```

### Fix with select_related

```python
# No warning:
users = list(User.objects.select_related("profile").all())
for user in users:
    print(user.profile)  # Already loaded
```

## Raise Exceptions in Tests

```python
# settings/test.py
NPLUS1_RAISE = True  # Raise NPlusOneError instead of logging
```

## Using the pytest Plugin

```python
# Automatic detection with marker
@pytest.mark.nplus1
def test_my_view(client):
    client.get("/my-view/")  # Fails if N+1 detected

# Manual detection with fixture
def test_manual(nplus1):
    users = list(User.objects.all())
    users[0].profile  # Raises NPlusOneError
```

## Using the Profiler

```python
from django_nplus1 import Profiler

with Profiler():
    users = list(User.objects.all())
    users[0].profile  # Raises NPlusOneError
```
