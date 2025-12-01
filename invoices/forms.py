from django import forms

class InvoiceForm(forms.Form):
    company_name = forms.CharField(label="Company Name", max_length=100, initial="Konoz United Surabaya")
    customer_name = forms.CharField(label="Kepada", max_length=100)
    invoice_number = forms.CharField("invoice_number")
    issued_date = forms.DateField(label="Issued Date", widget=forms.DateInput(attrs={"type":"date"}))
    due_date = forms.DateField(label="Due Date", widget=forms.DateInput(attrs={"type":"date"}))
