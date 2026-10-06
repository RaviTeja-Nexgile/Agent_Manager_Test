"""Background task functions (documentation §5, §8.7).

Invoked via FastAPI BackgroundTasks (and synchronously by the `.../evaluate`
endpoints). Each function manages its own DB session so it is safe to run after
the response is returned, and is structured to be Celery-swappable.
"""
from app.workers import eld_format  # noqa: F401
from app.workers.tasks import (  # noqa: F401
    evaluate_completeness,
    evaluate_quality,
    parse_eld_file,
    resolve_eld_mappings,
    scan_crashes_missing_iif,
)
