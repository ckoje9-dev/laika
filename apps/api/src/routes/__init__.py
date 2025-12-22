"""FastAPI 라우터 묶음."""

from .projects import router as projects  # noqa: F401
from .uploads import router as uploads  # noqa: F401
from .queries import router as queries  # noqa: F401
