from decimal import Decimal

from django.db.models import Prefetch

from .models import BasketLine, BasketSession, UncataloguedBasketLine


def session_with_lines(session_id):
    return (
        BasketSession.objects.select_related("device", "selected_terminal")
        .prefetch_related(
            Prefetch("lines", queryset=BasketLine.objects.select_related("product").order_by("created_at", "id")),
            Prefetch("uncatalogued_lines", queryset=UncataloguedBasketLine.objects.order_by("created_at", "id")),
        )
        .filter(pk=session_id)
        .first()
    )


def serialize_session(session):
    lines = []
    total = Decimal("0")
    item_count = 0
    uncatalogued_item_count = 0
    entries = [
        (line.created_at, "catalogued", line)
        for line in session.lines.all()
    ] + [
        (line.created_at, "uncatalogued", line)
        for line in session.uncatalogued_lines.all()
    ]
    for _created_at, kind, line in sorted(entries, key=lambda item: item[0]):
        item_count += line.quantity
        if kind == "catalogued":
            subtotal = line.unit_price_snapshot * line.quantity
            total += subtotal
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
                    "catalogued": True,
                }
            )
        else:
            uncatalogued_item_count += line.quantity
            lines.append(
                {
                    "id": f"uncatalogued-{line.id}",
                    "product": {
                        "id": None,
                        "sku": "NON-RÉPERTORIÉ",
                        "name": line.display_name,
                    },
                    "quantity": line.quantity,
                    "unit_price": "0",
                    "subtotal": "0",
                    "catalogued": False,
                    "detected_label": line.detected_label,
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
        "uncatalogued_item_count": uncatalogued_item_count,
        "total": str(total),
        "opened_at": session.opened_at,
        "updated_at": session.updated_at,
    }
