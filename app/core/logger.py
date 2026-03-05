import logging

import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        add_log_level,
        TimeStamper(fmt="iso"),
        JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(min_level=20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)


def get_logger(**initial_context):
    return structlog.get_logger(**initial_context)
