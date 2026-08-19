from rest_framework import serializers


class MatrixScanSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    matrix_id = serializers.IntegerField(min_value=1, max_value=4095)
    frame_errors = serializers.IntegerField(min_value=0, max_value=65535)
    copy_disagreements = serializers.IntegerField(min_value=0, max_value=65535)
    cell_contrast = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=0)
    scanned_at = serializers.DateTimeField(required=False)


class ExpectedVersionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255, trim_whitespace=True)


class CorrectLineSerializer(ExpectedVersionSerializer):
    quantity = serializers.IntegerField(min_value=0, max_value=999)
    product_id = serializers.IntegerField(min_value=1, required=False)


class CompleteSaleSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    payment_method = serializers.RegexField(regex=r"^[A-Z][A-Z0-9_]{1,31}$", max_length=32)
    payment_status = serializers.ChoiceField(choices=("PENDING", "PAID"))
