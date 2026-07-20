import json
from channels.generic.websocket import AsyncWebsocketConsumer

class BasketConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.room_group_name = f"basket_{self.device_id}"

        # Rejoint le groupe spécifique à ce panier
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Quitte le groupe
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Reçoit l'événement envoyé depuis la vue Django et l'envoie au Frontend
    async def send_basket_update(self, event):
        await self.send(text_data=json.dumps({
            "status": "updated",
            "basket": event["basket"]
        }))