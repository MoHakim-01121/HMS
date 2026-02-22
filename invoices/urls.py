"""  
URL Configuration for Invoice App
Defines routes for invoice form and PDF generation.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('cl/', views.cl_form, name='cl_form'),
    path('cl/generate/', views.generate_cl, name='generate_cl'),
    path('invoice/', views.invoice_form, name='invoice_form'),
    path('generate/', views.generate_invoice, name='generate_invoice'),
    path('services-form/', views.invoice_visa_form, name='services_form'),
    path('generate-visa/', views.generate_invoice_visa, name='generate_invoice_visa'),
    path('generate-services/', views.generate_services, name='generate_services'),
]
