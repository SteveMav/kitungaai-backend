from rest_framework import serializers

from .models import DetectionEvent


class DetectionEventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    session_id = serializers.UUIDField(required=False, allow_null=True)
    boot_id = serializers.CharField(max_length=96)
    sequence = serializers.IntegerField(min_value=0, max_value=9223372036854775807)
    captured_at = serializers.DateTimeField()
    action = serializers.ChoiceField(choices=DetectionEvent.Action.choices)
    detected_label = serializers.RegexField(
        regex=r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$",
        max_length=128,
    )
    confidence = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=20, default=1)
    model_version = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    legacy = serializers.BooleanField(required=False, default=False)
