"""Rate limiting do SegPortal (slowapi): protege login e endpoints de escrita."""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Desativável em testes/dev com SEGPORTAL_RATE_LIMIT_ENABLED=0.
_enabled = os.getenv("SEGPORTAL_RATE_LIMIT_ENABLED", "1") != "0"

limiter = Limiter(key_func=get_remote_address, enabled=_enabled, storage_uri="memory://")

LOGIN_LIMIT = "5/minute"      # força bruta no login
API_WRITE_LIMIT = "30/minute"  # uploads, montagens, etc.
GENERAL_LIMIT = "200/minute"   # leituras gerais
