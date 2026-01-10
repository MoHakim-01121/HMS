"""  
URL Configuration for Invoice App
Defines routes for invoice form and PDF generation.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_form, name='invoice_form'),
    path('generate/', views.generate_invoice, name='generate_invoice'),
]
