from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_form, name='invoice_form'),
    path('generate/', views.generate_invoice, name='generate_invoice'),
]
