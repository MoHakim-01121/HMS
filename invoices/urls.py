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
    path('test/', views.test, name='test'),
]
