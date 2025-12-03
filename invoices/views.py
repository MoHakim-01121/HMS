import os
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import get_template
from weasyprint import HTML
from datetime import datetime


def parse_date(date_str):
    if not date_str or date_str.strip() == "":
        return None
    # HTML date input: YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        pass
    # Manual input dd/mm/yyyy
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").strftime("%d/%m/%Y")
    except:
        return None


def invoice_form(request):
    return render(request, "invoices/invoice_form.html")



def generate_invoice(request):
    if request.method == "POST":

        invoice_number = request.POST.get("invoice_number")
        issued_date_raw = request.POST.get("issued_date")
        due_date_raw = request.POST.get("due_date")
        company_name = request.POST.get("company_name")
        customer_name = request.POST.get("customer_name")
        
        # Convert date strings to datetime objects
        try:
            issued_date = datetime.strptime(issued_date_raw, "%Y-%m-%d") if issued_date_raw else None
        except:
            issued_date = None
            
        try:
            due_date = datetime.strptime(due_date_raw, "%Y-%m-%d") if due_date_raw else None
        except:
            due_date = None

        # ----------------------------------------------------
        # RESERVATIONS
        # ----------------------------------------------------
        reservation_numbers = request.POST.getlist("reservation_number")
        hotels = request.POST.getlist("hotel")
        checkins = request.POST.getlist("check_in")
        checkouts = request.POST.getlist("check_out")
        reservation_totals = request.POST.getlist("reservation_total")

        reservations = []
        total_reservation_sar = 0

        print("DEBUG RESERVATIONS:")
        print(f"Numbers: {reservation_numbers}")
        print(f"Hotels: {hotels}")
        print(f"Check-ins: {checkins}")
        print(f"Check-outs: {checkouts}")
        print(f"Totals: {reservation_totals}")

        for num, hotel, ci, co, total in zip(
            reservation_numbers,
            hotels,
            checkins,
            checkouts,
            reservation_totals
        ):
            amt = float(total.strip()) if total and total.strip() else 0
            amt_int = int(round(amt))
            
            # Convert check-in/out to datetime objects
            try:
                check_in_date = datetime.strptime(ci.strip(), "%Y-%m-%d") if ci and ci.strip() else None
            except:
                check_in_date = None
                
            try:
                check_out_date = datetime.strptime(co.strip(), "%Y-%m-%d") if co and co.strip() else None
            except:
                check_out_date = None
            
            print(f"Processing: num={num}, hotel={hotel}, ci={check_in_date}, co={check_out_date}, total={amt_int}")

            reservations.append({
                "number": (num.strip() if num and num.strip() else "-"),
                "hotel": (hotel.strip() if hotel and hotel.strip() else "-"),
                "check_in": check_in_date,
                "check_out": check_out_date,
                "total": f"{amt_int:,}"
            })
            total_reservation_sar += amt_int
        
        print(f"Total Reservation SAR: {total_reservation_sar}")
        print(f"Reservations list: {reservations}")

        # ----------------------------------------------------
        # PAYMENTS
        # ----------------------------------------------------
        payment_dates = request.POST.getlist("payment_date")
        payment_methods = request.POST.getlist("payment_method")
        payment_amounts = request.POST.getlist("payment_amount")
        payment_currencies = request.POST.getlist("payment_currency")
        payment_exchanges = request.POST.getlist("payment_exchange")
        payment_notes = request.POST.getlist("payment_note")

        payments = []
        total_paid_sar = 0

        print("\nDEBUG PAYMENTS:")
        print(f"Dates: {payment_dates}")
        print(f"Methods: {payment_methods}")
        print(f"Amounts: {payment_amounts}")
        print(f"Currencies: {payment_currencies}")
        print(f"Exchanges: {payment_exchanges}")

        for date, method, amount, currency, exchange, note in zip(
            payment_dates,
            payment_methods,
            payment_amounts,
            payment_currencies,
            payment_exchanges,
            payment_notes
        ):
            amount_float = float(amount.strip()) if amount and amount.strip() else 0
            ex = float(exchange.strip()) if exchange and exchange.strip() else 1

            # Convert amount to SAR
            if currency.upper() == "SAR":
                amount_sar = amount_float
            elif currency.upper() == "IDR":
                amount_sar = amount_float / ex if ex != 0 else 0
            else:  # USD / others
                amount_sar = amount_float * ex
            
            # Convert payment date to datetime object
            try:
                payment_date = datetime.strptime(date.strip(), "%Y-%m-%d") if date and date.strip() else None
            except:
                payment_date = None
            
            print(f"Processing payment: date={payment_date}, amount={amount_float}, currency={currency}, amount_sar={int(round(amount_sar))}")

            payments.append({
                "date": payment_date,
                "method": (method.strip() if method and method.strip() else "-"),
                "amount": f"{int(round(amount_float)):,}",
                "currency": currency.upper(),
                "exchange": f"{ex:,.2f}" if currency.upper() != "SAR" else "-",
                "amount_sar": f"{int(round(amount_sar)):,}",
                "note": (note.strip() if note and note.strip() else "-")
            })

            total_paid_sar += int(round(amount_sar))
        
        print(f"Total Paid SAR: {total_paid_sar}")
        print(f"Payments list: {payments}")

        remaining = total_reservation_sar - total_paid_sar

        logo_path = os.path.join(settings.BASE_DIR, "media", "logo.jpeg")
        logo_path = "file://" + logo_path

        # Build HTML directly to avoid cache issues
        from django.template import Template, Context
        
        # Read template file directly
        template_path = os.path.join(settings.BASE_DIR, "invoices", "templates", "invoices", "invoice_pdf.html")
        with open(template_path, 'r') as f:
            template_string = f.read()
        
        template = Template(template_string)
        context = Context({
            "company_name": company_name,
            "company_city": "",
            "customer_name": customer_name,
            "issued_date": issued_date,
            "due_date": due_date,
            "invoice_number": invoice_number,

            "reservations": reservations,
            "payments": payments,

            "total_reservation_sar": f"{total_reservation_sar:,}",
            "total_paid_sar": f"{total_paid_sar:,}",
            "remaining": f"{remaining:,}",
            "remaining_int": remaining,  # For comparison in template

            "logo_path": logo_path
        })
        
        html_string = template.render(context)

        response = HttpResponse(content_type="application/pdf")
        filename = f"invoice_{invoice_number}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        # Debug: Save HTML to file
        with open("/home/hakim/Desktop/config/debug_invoice.html", "w") as f:
            f.write(html_string)
        print("\n=== HTML saved to debug_invoice.html ===\n")

        # FIX for WeasyPrint 59
        HTML(string=html_string).write_pdf(target=response)

        return response
