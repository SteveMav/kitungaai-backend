from rest_framework import serializers


class HeartbeatSerializer(serializers.Serializer):
    firmware_version = serializers.CharField(max_length=64, required=False, allow_blank=True)
    boot_id = serializers.CharField(max_length=96, required=False, allow_blank=True)
    queue_depth = serializers.IntegerField(min_value=0, max_value=100000, required=False)
    edge_state = serializers.ChoiceField(
        choices=("READY", "TRACKING", "DEGRADED", "RESETTING"),
        required=False,
    )


class CommandAckSerializer(serializers.Serializer):
    boot_id = serializers.CharField(max_length=96, required=False, allow_blank=True)
    acknowledged_at = serializers.DateTimeField(required=False)
