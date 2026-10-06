from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import Reservation, Restaurant
from .validators import (
    DATETIME_INVALID_MESSAGE, validate_reservation_datetime_format,
    validate_reservation_datetime, validate_reservation_party_size,
    validate_restaurant_accepts_reservations,
)


class IntegerPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """JSONの整数だけを許可し、ORMによる数値の丸めを防ぐ。"""

    def to_internal_value(self, data):
        # boolはintのサブクラスなので、isinstanceではなく型を比較する。
        if type(data) is not int:
            self.fail("incorrect_type", data_type=type(data).__name__)
        return super().to_internal_value(data)


class ReservationDateTimeSerializerField(serializers.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=["%Y-%m-%dT%H:%M"],
            default_timezone=timezone.get_default_timezone(),
            **kwargs,
        )

    def to_internal_value(self, value):
        try:
            validate_reservation_datetime_format(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages, code="invalid") from error
        return super().to_internal_value(value)


class ReservationSerializer(serializers.ModelSerializer):
    restaurant = IntegerPrimaryKeyRelatedField(queryset=Restaurant.objects.all())
    reserved_at = ReservationDateTimeSerializerField(error_messages={
        "required": "予約日時を入力してください。",
        "invalid": DATETIME_INVALID_MESSAGE,
    })
    party_size = serializers.IntegerField(min_value=1, max_value=32767, error_messages={
        "required": "人数を入力してください。",
        "min_value": "人数は1人以上を指定してください。",
    })
    created_at = serializers.DateTimeField(
        read_only=True, default_timezone=timezone.get_default_timezone()
    )

    class Meta:
        model = Reservation
        fields = ["id", "restaurant", "reserved_at", "party_size", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def validate(self, attrs):
        restaurant = attrs["restaurant"]
        errors = {}
        checks = (
            ("reserved_at", validate_reservation_datetime, (restaurant, attrs["reserved_at"])),
            ("party_size", validate_reservation_party_size, (restaurant, attrs["party_size"])),
            ("non_field_errors", validate_restaurant_accepts_reservations, (restaurant,)),
        )
        for field, validator, arguments in checks:
            try:
                validator(*arguments)
            except DjangoValidationError as error:
                errors[field] = [serializers.ErrorDetail(item.message, code=item.code or "invalid")
                                 for item in error.error_list]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
