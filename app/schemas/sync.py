from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields


class SyncRunRead(Schema):
    id = fields.UUID(dump_only=True)
    kind = fields.String(dump_only=True)
    status = fields.String(dump_only=True)
    created_at = UtcDateTimeField(dump_only=True)
    started_at = UtcDateTimeField(dump_only=True, allow_none=True)
    completed_at = UtcDateTimeField(dump_only=True, allow_none=True)
    details = fields.Dict(dump_only=True)
    error = fields.String(dump_only=True, allow_none=True)
