from app.config import get_settings

# Schemas
from app.schemas.push.vapid_key_read import VapidKeyReadSchema

# Views
from app.views.base import WatchlyView


class VapidKeyView(WatchlyView):
    accepted_methods = ["GET"]
    authentication_required = False

    def get(self):
        return VapidKeyReadSchema().dump({"public_key": get_settings().vapid_public_key})
