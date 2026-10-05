def _billing_client(invoice):
    """Client yang ditagih invoice ini. Satu invoice satu client, dan setiap
    reservasi di dalamnya milik client itu (dijaga skema), jadi tidak ada lagi
    yang perlu ditebak dari CL-nya."""
    return invoice.client


def _billing_props(invoice):
    """Shared Inertia props for the billing-message generator. The client's WA
    number (when known) feeds the wa.me deep link in the draft modal."""
    client = _billing_client(invoice)
    return {
        'wa_send': {
            'client_name': client.name if client else None,
            'client_wa': client.wa if client else '',
            'has_wa': bool(client and client.wa),
            'has_group': bool(client and client.wa_group),
        },
    }
