"""予約作成時の検証。履歴やキャンセル時には再適用しない。"""
import re
from datetime import time

from django.core.exceptions import ValidationError
from django.utils import timezone


DATETIME_INVALID_MESSAGE = "予約日時は日本時間でYYYY-MM-DDTHH:MM形式の正しい日時を入力してください。"


def validate_reservation_datetime_format(value, message=DATETIME_INVALID_MESSAGE):
    if not isinstance(value, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}", value
    ) is None:
        raise ValidationError(message, code="invalid")


def reservation_time_choices(restaurant):
    """設定値を変更せず、受付範囲内の00分・30分を返す。"""
    if not restaurant.can_accept_reservations:
        return []
    return [
        (value.strftime("%H:%M"), value.strftime("%H:%M"))
        for hour in range(24) for minute in (0, 30)
        if restaurant.opening_time <= (value := time(hour, minute)) <= restaurant.last_reservation_time
    ]


def validate_reservation_datetime(restaurant, reserved_at):
    if reserved_at <= timezone.now():
        raise ValidationError("予約日時は未来の日時を指定してください。")
    reserved_time = timezone.localtime(reserved_at, timezone.get_default_timezone()).time()
    if restaurant.can_accept_reservations:
        if not restaurant.opening_time <= reserved_time <= restaurant.last_reservation_time:
            opening = restaurant.opening_time.strftime("%H:%M")
            last = restaurant.last_reservation_time.strftime("%H:%M")
            raise ValidationError(f"予約時刻は{opening}以上、{last}以下を指定してください。")

    if reserved_time.minute not in (0, 30) or reserved_time.second or reserved_time.microsecond:
        raise ValidationError("予約時刻は毎時00分・30分を選択してください。", code="invalid")


def validate_reservation_party_size(restaurant, party_size):
    if party_size > restaurant.max_party_size:
        raise ValidationError(
            f"人数は{restaurant.max_party_size}人以下を指定してください。", code="max_value"
        )


def validate_restaurant_accepts_reservations(restaurant):
    if not restaurant.can_accept_reservations:
        raise ValidationError("店舗の予約設定が未完了または不正のため、現在予約を受け付けていません。")

    if not reservation_time_choices(restaurant):
        raise ValidationError("この店舗には予約可能な時刻がありません。")
