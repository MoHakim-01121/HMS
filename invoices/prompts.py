def invoice_summary(invoice, total, paid, remaining, hotels):
    return (
        f"Tulis ringkasan 1-2 kalimat Bahasa Indonesia untuk invoice berikut. "
        f"Fokus pada deskripsi (siapa, hotel mana, berapa reservasi). "
        f"Jangan sebut jatuh tempo atau status bayar. Tanpa pembuka formal.\n\n"
        f"Invoice #{invoice.invoice_number} - {invoice.customer_name}\n"
        f"Hotel: {hotels}\n"
        f"Total: {total:,.0f} SAR - Terbayar: {paid:,.0f} SAR - Sisa: {remaining:,.0f} SAR\n"
        f"Jumlah reservasi: {invoice.reservations.count()}"
    )


def cl_summary(cl, rooms_desc):
    return (
        f"Tulis ringkasan 1-2 kalimat Bahasa Indonesia untuk confirmation letter berikut. "
        f"Langsung ke poin, informatif, tanpa pembuka formal.\n\n"
        f"CL #{cl.confirmation_number} - {cl.guest_name}\n"
        f"Hotel: {cl.hotel_name}\n"
        f"Check-in: {cl.check_in} - Check-out: {cl.check_out} - {cl.num_nights} malam\n"
        f"Kamar: {rooms_desc} - Total: {cl.total_price:,.0f} SAR\n"
        f"Status: {cl.reservation_status}"
    )


def services_summary(invoice, services_desc, total, remaining):
    return (
        f"Tulis ringkasan 1-2 kalimat Bahasa Indonesia untuk invoice services berikut. "
        f"Langsung ke poin, informatif, tanpa pembuka formal.\n\n"
        f"Invoice #{invoice.invoice_number} - {invoice.customer_name}\n"
        f"Layanan: {services_desc}\n"
        f"Total: {total:,.0f} {invoice.currency} - Sisa: {remaining:,.0f} {invoice.currency}\n"
        f"Status: {'Lunas' if remaining <= 0 else 'Belum lunas'}"
    )


def draft_invoice(invoice, hotels, total, paid, remaining, due_info):
    return (
        f"Tulis pesan tagihan WhatsApp dalam Bahasa Indonesia yang sopan dan singkat. "
        f"Gunakan format yang bersih, mudah dibaca di WA. Sertakan nomor invoice, nama customer, "
        f"jumlah yang harus dibayar, dan info jatuh tempo jika ada. Tanpa pembuka berlebihan.\n\n"
        f"Invoice #{invoice.invoice_number} - {invoice.customer_name}\n"
        f"Hotel: {hotels}\n"
        f"Total: {total:,.0f} SAR | Terbayar: {paid:,.0f} SAR | Sisa: {remaining:,.0f} SAR\n"
        f"Due date: {invoice.due_date or '-'} {due_info}\n"
        f"Perusahaan pengirim: {invoice.get_company_display()}"
    )


def draft_services(invoice, services_desc, total, paid, remaining):
    return (
        f"Tulis pesan tagihan WhatsApp dalam Bahasa Indonesia yang sopan dan singkat. "
        f"Gunakan format yang bersih, mudah dibaca di WA. Sertakan nomor invoice, nama customer, "
        f"layanan yang dipesan, dan jumlah yang harus dibayar. Tanpa pembuka berlebihan.\n\n"
        f"Invoice #{invoice.invoice_number} - {invoice.customer_name}\n"
        f"Layanan: {services_desc}\n"
        f"Total: {total:,.0f} {invoice.currency} | Terbayar: {paid:,.0f} | Sisa: {remaining:,.0f} {invoice.currency}\n"
        f"Due date: {invoice.due_date or '-'}\n"
        f"Perusahaan pengirim: {invoice.get_company_display()}"
    )
