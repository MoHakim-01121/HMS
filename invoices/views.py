import os
from urllib import response
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import get_template
from weasyprint import HTML

def invoice_form(request):
    return render(request, "invoices/invoice_form.html")

def generate_invoice(request):
    if request.method == "POST":
        invoice_number = request.POST.get("invoice_number")
        # Company / Customer / Dates
        company_name = request.POST.get("company_name")
        customer_name = request.POST.get("customer_name")
        issued_date = request.POST.get("issued_date")
        due_date = request.POST.get("due_date")


        # Reservations
        reservation_numbers = request.POST.getlist("reservation_number")
        reservation_totals = request.POST.getlist("reservation_total")

        reservations = []
        total_reservation_sar = 0
        for num, total in zip(reservation_numbers, reservation_totals):
            amt = float(total) if total else 0
            reservations.append({"number": num, "total": amt})
            total_reservation_sar += amt

        # Payments
        payment_dates = request.POST.getlist('payment_date')
        payment_methods = request.POST.getlist('payment_method')
        payment_amounts = request.POST.getlist('payment_amount')
        payment_currencies = request.POST.getlist('payment_currency')
        payment_exchanges = request.POST.getlist('payment_exchange')
        payment_notes = request.POST.getlist('payment_note')

        n = max(len(payment_dates), len(payment_methods), len(payment_amounts), 
                len(payment_currencies), len(payment_exchanges), len(payment_notes))

        def pad(lst, n, default=''):
            return lst + [default]*(n - len(lst))

        payment_dates = pad(payment_dates, n)
        payment_methods = pad(payment_methods, n)
        payment_amounts = pad(payment_amounts, n, '0')
        payment_currencies = pad(payment_currencies, n, 'SAR')
        payment_exchanges = pad(payment_exchanges, n, '1')
        payment_notes = pad(payment_notes, n)

        payments = []
        total_paid_sar = 0

        for date, method, amount, currency, exchange, note in zip(
            payment_dates, payment_methods, payment_amounts, payment_currencies, payment_exchanges, payment_notes
        ):
            amt = float(amount) if amount else 0
            curr = currency
            ex = float(exchange) if curr != 'SAR' else 1
            amt_sar = amt if curr == 'SAR' else amt * ex
            total_paid_sar += amt_sar

            payments.append({
                "date": date,
                "method": method,
                "amount": amt,
                "currency": curr,
                "exchange": ex if curr != 'SAR' else '',
                "amount_sar": amt_sar,
                "note": note
            })

        remaining = total_reservation_sar - total_paid_sar

        # --- Tambahkan path logo absolut ---
        logo_path = os.path.join(settings.BASE_DIR, 'media', 'logo.jpeg')
        logo_path = 'file://' + logo_path  # wajib pakai file:// agar WeasyPrint bisa baca

        # Render PDF
        template = get_template("invoices/invoice_pdf.html")
        html_string = template.render({
            "company_name": company_name,
            "customer_name": customer_name,
            "issued_date": issued_date,
            "due_date": due_date,
            "invoice_number": invoice_number,
            "reservations": reservations,
            "payments": payments,
            "total_reservation_sar": total_reservation_sar,
            "total_paid_sar": total_paid_sar,
            "remaining": remaining,
            "logo_path": logo_path  # kirim ke template
        })

        response = HttpResponse(content_type='application/pdf')
        filename = f"invoice_{invoice_number}.pdf" if invoice_number else "invoice.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'


        HTML(string=html_string).write_pdf(response)
        return response
