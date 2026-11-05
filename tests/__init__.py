from gengwiki import _http, client

_http.RETRY_WAIT = 0.01  # the retries still happen, the tests just do not sit through the backoff

# The real backup wiki is never asked from tests. test_backup points it at the fake.
client.BACKUP_URL = ""  # fails at once, a refused port takes 2 s on Windows
