def test(request):
    return HttpResponse("OK")
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


def home(request):
    """
    Display the home page with options for CL and Invoice
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered home page template
    """
    return render(request, "invoices/home.html")


def cl_form(request):
    """
    Display the confirmation letter form page
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse: Rendered CL form template
    """
    return render(request, "invoices/cl_form.html")


def generate_cl(request):
    """
    Generate PDF confirmation letter from form data
    
    Args:
        request: HTTP POST request with form data
        
    Returns:
        HttpResponse: PDF file response
    """
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    # Extract basic CL data
    company = request.POST.get("company", "konoz")
    cl_data = {
        'company': company,
        'hotel_name': request.POST.get("hotel_name"),
        'guest_name': request.POST.get("guest_name"),
        'guest_phone': request.POST.get("guest_phone"),
        # num_guests will be calculated below
        'num_guests': 0,
        'check_in': None,
        'check_out': None,
        'note': request.POST.get("note", ""),
        'confirmation_number': request.POST.get("confirmation_number"),
        'reservation_status': request.POST.get("reservation_status", "DEFINITE"),
    }
    
    # Parse dates
    check_in_raw = request.POST.get("check_in")
    check_out_raw = request.POST.get("check_out")
    
    try:
        cl_data['check_in'] = datetime.strptime(check_in_raw, "%Y-%m-%d") if check_in_raw else None
    except ValueError:
        cl_data['check_in'] = None

    try:
        cl_data['check_out'] = datetime.strptime(check_out_raw, "%Y-%m-%d") if check_out_raw else None
    except ValueError:
        cl_data['check_out'] = None

    # Validasi: check-out tidak boleh sebelum check-in
    if cl_data['check_in'] and cl_data['check_out']:
        if cl_data['check_out'] < cl_data['check_in']:
            return HttpResponse("<h2 style='color:red'>Tanggal check-out tidak boleh sebelum check-in.</h2>", status=400)

    # Calculate number of nights
    num_nights = 0
    if cl_data['check_in'] and cl_data['check_out']:
        num_nights = (cl_data['check_out'] - cl_data['check_in']).days
    cl_data['num_nights'] = num_nights
    nights_factor = num_nights if num_nights > 0 else 1
    
    # Process multiple room types
    room_types = request.POST.getlist("room_type")
    room_meals = request.POST.getlist("room_meals")
    num_rooms = request.POST.getlist("num_rooms")
    room_prices = request.POST.getlist("room_price")
    
    rooms = []
    total_rooms = 0
    total_price = 0.0
    # Calculate number of guests based on room types
    room_type_capacity = {
        'Double': 2,
        'Triple': 3,
        'Quad': 4,
        'Quint': 5,
    }
    num_guests = 0
    for i, rt in enumerate(room_types):
        try:
            qty = int(num_rooms[i])
        except (IndexError, ValueError):
            qty = 1
        cap = room_type_capacity.get(rt, 1)
        num_guests += qty * cap
    cl_data['num_guests'] = num_guests
    for i in range(len(room_types)):
        if room_types[i]:
            room_count = int(num_rooms[i]) if i < len(num_rooms) and num_rooms[i] else 1
            room_price = float(room_prices[i]) if i < len(room_prices) and room_prices[i] else 0.0
            meals = room_meals[i] if i < len(room_meals) and room_meals[i] else ""
            # Subtotal reflects the full stay (rooms x rate x nights)
            subtotal = room_count * room_price * nights_factor
            rooms.append({
                'type': room_types[i],
                'meals': meals,
                'quantity': room_count,
                'price': room_price,
                'subtotal': subtotal
            })
            total_rooms += room_count
            total_price += subtotal
    
    cl_data['rooms'] = rooms
    cl_data['total_rooms'] = total_rooms
    cl_data['total_price'] = total_price

    # Add logo path based on company
    if company == "ijabah":
        logo_filename = "ijabahlogo.png"
    else:
        logo_filename = "logo.jpeg"
    logo_path = os.path.join(settings.BASE_DIR, "media", logo_filename)
    cl_data['logo_path'] = "file://" + logo_path

    # Prepare context for PDF template
    context = cl_data

    # Select template based on company
    if company == "ijabah":
        template_path = os.path.join(settings.BASE_DIR, "invoices/templates/invoices/cl_pdf_ijabah.html")
    else:
        template_path = os.path.join(settings.BASE_DIR, "invoices/templates/invoices/cl_pdf_konoz.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html_template = f.read()

    # Render HTML with context
    template = Template(html_template)
    html_content = template.render(Context(context))

    # Generate PDF
    pdf = HTML(string=html_content, base_url=str(settings.BASE_DIR)).write_pdf()

    # Tentukan nama file berdasarkan confirmation_number
    confirmation_number = cl_data.get("confirmation_number") or "NORESERVASI"
    filename = f"CL{confirmation_number}.pdf"
    # Return PDF response (inline for preview, not download)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


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
    company = request.POST.get("company", "konoz")
    if company == "konoz":
        company_name = "Konoz United Surabaya"
    else:
        company_name = "iJabah Group"
    company_tagline = "Travel & Hospitality Services"

    invoice_data = {
        'number': request.POST.get("invoice_number"),
        'company': company,
        'company_name': company_name,
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
        "company_tagline": company_tagline,
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
        "logo_path": get_logo_path(company)
    }
    
    # Generate PDF
    return generate_pdf_response(context, invoice_data['number'], company)


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


def get_logo_path(company="konoz"):
    """
    Get the file path to the logo image
    
    Args:
        company (str): Company name ('konoz' or 'ijabah')
        
    Returns:
        str: File URL path to logo
    """
    if company == "ijabah":
        logo_filename = "ijabahlogo.png"
    else:
        logo_filename = "logo.jpeg"
    logo_path = os.path.join(settings.BASE_DIR, "media", logo_filename)
    return "file://" + logo_path


def generate_pdf_response(context, invoice_number, company="konoz"):
    """
    Generate PDF file from template and context
    
    Args:
        context (dict): Template context data
        invoice_number (str): Invoice number for filename
        company (str): Company name to select template
        
    Returns:
        HttpResponse: PDF file response
    """
    # Select template based on company
    if company == "ijabah":
        template_filename = "invoice_pdf_ijabah.html"
    else:
        template_filename = "invoice_pdf.html"
    
    # Read template file directly
    template_path = os.path.join(
        settings.BASE_DIR, "invoices", "templates", "invoices", template_filename
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
    filename = f"INV_{invoice_number}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    
    # Generate PDF using WeasyPrint
    pdf_bytes = HTML(string=html_string).write_pdf()
    response.write(pdf_bytes)
    
    return response
