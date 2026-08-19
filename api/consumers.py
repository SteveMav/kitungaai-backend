import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.devices.models import BasketDevice


class BasketConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def resolve_matrix_id(self, device_code):
        device = BasketDevice.objects.filter(device_code=device_code, enabled=True).first()
        return device.matrix_id if device else None

    @database_sync_to_async
    def is_allowed(self):
        user = self.scope.get("user")
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or user.groups.filter(name__in=("Administrateur", "Caissier", "Superviseur")).exists()
            )
        )

    async def connect(self):
        if not await self.is_allowed():
            await self.close(code=4403)
            return
        device_code = self.scope["url_route"]["kwargs"]["device_id"]
        matrix_id = await self.resolve_matrix_id(device_code)
        if matrix_id is None:
            await self.close(code=4404)
            return
        self.room_group_name = f"basket_{matrix_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def domain_message(self, event):
        await self.send(text_data=json.dumps(event["payload"], default=str))

    async def basket_update(self, event):
        await self.send(text_data=json.dumps({"basket": event["basket"]}, default=str))
