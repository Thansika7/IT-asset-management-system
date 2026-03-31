import json
import logging
from datetime import datetime, timezone


LOG_SERVICE = "asset-management-service"
LOG_ENVIRONMENT = "production"


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": LOG_SERVICE,
            "environment": LOG_ENVIRONMENT,
            "message": record.getMessage(),
            "userId": getattr(record, "userId", "anonymous"),
            "endpoint": getattr(record, "endpoint", ""),
            "method": getattr(record, "method", ""),
            "statusCode": getattr(record, "statusCode", 0),
            "responseTime": getattr(record, "responseTime", 0),
        }
        return json.dumps(payload)


class StructuredDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.userId = getattr(record, "userId", "anonymous")
        record.endpoint = getattr(record, "endpoint", "")
        record.method = getattr(record, "method", "")
        record.statusCode = getattr(record, "statusCode", 0)
        record.responseTime = getattr(record, "responseTime", 0)
        return True
