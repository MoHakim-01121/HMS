"""
Invoice views for handling form display and PDF generation
"""
import os
from datetime import datetime

from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from django.template import Template, Context
from weasyprint import HTML

from .utils import parse_date, convert_to_sar, format_currency


def invoice_form(request):
    """
    Display the invoice form page
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered invoice form template
    """
    return render(request, "invoices/invoice_form.html")


def generate_invoice(request):
    """
    Generate PDF invoice from form data
    
    Args:
        request: HTTP POST request with form data
        
    Returns:
        HttpResponse: PDF file response
    """
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    # Extract basic invoice data
    invoice_data = {
        'number': request.POST.get("invoice_number"),
        'company_name': request.POST.get("company_name"),
        'customer_name': request.POST.get("customer_name"),
        'issued_date': None,
        'due_date': None,
    }
    
    # Parse dates
    issued_date_raw = request.POST.get("issued_date")
    due_date_raw = request.POST.get("due_date")
    
    try:
        invoice_data['issued_date'] = datetime.strptime(issued_date_raw, "%Y-%m-%d") if issued_date_raw else None
    except ValueError:
        invoice_data['issued_date'] = None
        
    try:
        invoice_data['due_date'] = datetime.strptime(due_date_raw, "%Y-%m-%d") if due_date_raw else None
    except ValueError:
        invoice_data['due_date'] = None

    # Process reservations
    reservations, total_reservation_sar = process_reservations(request)
    
    # Process payments
    payments, total_paid_sar, payments_by_reservation = process_payments(request)
    
    # Calculate remaining per reservation
    reservations = calculate_remaining_per_reservation(reservations, payments_by_reservation)
    
    # Calculate totals
    total_remaining_sar = total_reservation_sar - total_paid_sar

    # Prepare context for PDF template
    context = {
        "company_name": invoice_data['company_name'],
        "company_city": "",
        "customer_name": invoice_data['customer_name'],
        "issued_date": invoice_data['issued_date'],
        "due_date": invoice_data['due_date'],
        "invoice_number": invoice_data['number'],
        "reservations": reservations,
        "payments": payments,
        "total_reservation_sar": f"{total_reservation_sar:,}",
        "total_remaining_sar": f"{total_remaining_sar:,}",
        "total_paid_sar": f"{total_paid_sar:,}",
        "remaining": f"{total_reservation_sar - total_paid_sar:,}",
        "remaining_int": total_reservation_sar - total_paid_sar,
        "logo_path": get_logo_path()
    }
    
    # Generate PDF
    return generate_pdf_response(context, invoice_data['number'])


def process_reservations(request):
    """
    Process reservation data from POST request
    
    Args:
        request: HTTP request object with POST data
        
    Returns:
        tuple: (list of reservations, total amount in SAR)
    """
    reservation_numbers = request.POST.getlist("reservation_number")
    hotels = request.POST.getlist("hotel")
    checkins = request.POST.getlist("check_in")
    checkouts = request.POST.getlist("check_out")
    reservation_totals = request.POST.getlist("reservation_total")

    reservations = []
    total_reservation_sar = 0

    for num, hotel, ci, co, total in zip(
        reservation_numbers, hotels, checkins, checkouts, reservation_totals
    ):
        amt = float(total.strip()) if total and total.strip() else 0
        amt_int = int(round(amt))
        
        # Parse dates
        try:
            check_in_date = datetime.strptime(ci.strip(), "%Y-%m-%d") if ci and ci.strip() else None
        except ValueError:
            check_in_date = None
            
        try:
            check_out_date = datetime.strptime(co.strip(), "%Y-%m-%d") if co and co.strip() else None
        except ValueError:
            check_out_date = None
        
        res_number = num.strip() if num and num.strip() else "-"
        
        reservations.append({
            "number": res_number,
            "hotel": hotel.strip() if hotel and hotel.strip() else "-",
            "check_in": check_in_date,
            "check_out": check_out_date,
            "total": f"{amt_int:,}",
            "total_int": amt_int
        })
        total_reservation_sar += amt_int
    
    return reservations, total_reservation_sar


def process_payments(request):
    """
    Process payment data from POST request
    
    Args:
        request: HTTP request object with POST data
        
    Returns:
        tuple: (list of payments, total paid in SAR, payments by reservation dict)
    """
    payment_reservation_nos = request.POST.getlist("payment_reservation_no")
    payment_dates = request.POST.getlist("payment_date")
    payment_methods = request.POST.getlist("payment_method")
    payment_amounts = request.POST.getlist("payment_amount")
    payment_currencies = request.POST.getlist("payment_currency")
    payment_exchanges = request.POST.getlist("payment_exchange")
    payment_notes = request.POST.getlist("payment_note")

    payments = []
    total_paid_sar = 0
    payments_by_reservation = {}  # Track payments per reservation number

    for res_no, date, method, amount, currency, exchange, note in zip(
        payment_reservation_nos, payment_dates, payment_methods,
        payment_amounts, payment_currencies, payment_exchanges, payment_notes
    ):
        amount_float = float(amount.strip()) if amount and amount.strip() else 0
        ex = float(exchange.strip()) if exchange and exchange.strip() else 1

        # Convert amount to SAR based on currency
        amount_sar = convert_to_sar(amount_float, currency.upper(), ex)
        amount_sar_int = int(round(amount_sar))
        
        # Parse payment date
        try:
            payment_date = datetime.strptime(date.strip(), "%Y-%m-%d") if date and date.strip() else None
        except ValueError:
            payment_date = None
        
        # Track payment by reservation number
        res_number = res_no.strip() if res_no and res_no.strip() else "-"
        if res_number not in payments_by_reservation:
            payments_by_reservation[res_number] = 0
        payments_by_reservation[res_number] += amount_sar_int
        
        payments.append({
            "reservation_no": res_number,
            "date": payment_date,
            "method": method.strip() if method and method.strip() else "-",
            "amount": f"{int(round(amount_float)):,}",
            "currency": currency.upper(),
            "exchange": f"{ex:,.2f}" if currency.upper() != "SAR" else "-",
            "amount_sar": f"{amount_sar_int:,}",
            "note": note.strip() if note and note.strip() else "-"
        })

        total_paid_sar += amount_sar_int
    
    return payments, total_paid_sar, payments_by_reservation


def calculate_remaining_per_reservation(reservations, payments_by_reservation):
    """
    Calculate remaining balance for each reservation
    
    Args:
        reservations (list): List of reservation dicts
        payments_by_reservation (dict): Payments grouped by reservation number
        
    Returns:
        list: Updated reservations with remaining balance
    """
    updated_reservations = []
    
    for res in reservations:
        res_num = res["number"]
        res_total = res["total_int"]
        paid_for_this = payments_by_reservation.get(res_num, 0)
        remaining_for_this = res_total - paid_for_this
        
        # Determine color class based on remaining amount
        if remaining_for_this == 0:
            remaining_class = "remaining-paid"
        elif remaining_for_this > (res_total * 0.5):
            remaining_class = "remaining-unpaid"
        else:
            remaining_class = "remaining-partial"
        
        updated_reservations.append({
            "number": res_num,
            "hotel": res["hotel"],
            "check_in": res["check_in"],
            "check_out": res["check_out"],
            "total": res["total"],
            "remaining": f"{remaining_for_this:,}",
            "remaining_class": remaining_class
        })
    
    return updated_reservations


def get_logo_path():
    """
    Get the file path to the logo image
    
    Returns:
        str: File URL path to logo
    """
    logo_path = os.path.join(settings.BASE_DIR, "media", "logo.jpeg")
    return "file://" + logo_path


def generate_pdf_response(context, invoice_number):
    """
    Generate PDF file from template and context
    
    Args:
        context (dict): Template context data
        invoice_number (str): Invoice number for filename
        
    Returns:
        HttpResponse: PDF file response
    """
    # Read template file directly
    template_path = os.path.join(
        settings.BASE_DIR, "invoices", "templates", "invoices", "invoice_pdf.html"
    )
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_string = f.read()
    
    template = Template(template_string)
    html_string = template.render(Context(context))
    
    # Debug: Save HTML for troubleshooting
    debug_path = os.path.join(settings.BASE_DIR, 'debug_invoice.html')
    with open(debug_path, 'w', encoding='utf-8') as f:
        f.write(html_string)
    
    # Generate PDF response
    response = HttpResponse(content_type="application/pdf")
    filename = f"invoice_{invoice_number}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    
    # Generate PDF using WeasyPrint
    pdf_bytes = HTML(string=html_string).write_pdf()
    response.write(pdf_bytes)
    
    return response
