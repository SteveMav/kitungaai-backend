from decimal import Decimal

from django.db.models import Prefetch

from .models import BasketLine, BasketSession


def session_with_lines(session_id):
    return (
        BasketSession.objects.select_related("device", "selected_terminal")
        .prefetch_related(
            Prefetch(
                "lines",
                queryset=BasketLine.objects.select_related("product").order_by("created_at", "id"),
            )
        )
        .filter(pk=session_id)
        .first()
    )


def serialize_session(session):
    lines = []
    total = Decimal("0")
    item_count = 0
    for line in session.lines.all():
        subtotal = line.unit_price_snapshot * line.quantity
        total += subtotal
        item_count += line.quantity
        lines.append(
            {
                "id": line.id,
                "product": {
                    "id": line.product_id,
                    "sku": line.product.sku,
                    "name": line.product.name,
                },
                "quantity": line.quantity,
                "unit_price": str(line.unit_price_snapshot),
                "subtotal": str(subtotal),
            }
        )
    return {
        "id": str(session.id),
        "device_code": session.device.device_code,
        "matrix_id": session.device.matrix_id,
        "status": session.status,
        "version": session.version,
        "selected_terminal": (
            session.selected_terminal.terminal_code if session.selected_terminal_id else None
        ),
        "lines": lines,
        "item_count": item_count,
        "total": str(total),
        "opened_at": session.opened_at,
        "updated_at": session.updated_at,
    }
