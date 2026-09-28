from slowapi import Limiter
from slowapi.util import get_remote_address

# Identify each client by its IP address.
limiter = Limiter(key_func=get_remote_address)
