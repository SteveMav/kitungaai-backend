import uuid

from django.test import TestCase
from django.urls import reverse

from apps.devices.models import BasketDevice


class LegacyApiSecurityTests(TestCase):
    def test_legacy_detection_route_requires_device_credentials(self):
        response = self.client.post(
            reverse("pi-add-detection", args=["KITUNGA-PI-LEGACY"]),
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized_device")
        self.assertFalse(BasketDevice.objects.exists())

    def test_legacy_detection_requires_idempotency_key(self):
        device = BasketDevice(device_code="KITUNGA-PI-LEGACY", matrix_id=10)
        device.set_secret("legacy-secret-for-tests-123456")
        device.save()
        response = self.client.post(
            reverse("pi-add-detection", args=[device.device_code]),
            data={"event_id": str(uuid.uuid4()), "label": "arduino"},
            content_type="application/json",
            HTTP_AUTHORIZATION="Device legacy-secret-for-tests-123456",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_event")
