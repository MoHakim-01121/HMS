"""  
Main URL Configuration
Routes:
    - / : Redirects to /invoices/
    - /admin/ : Django admin panel
    - /invoices/ : Invoice application
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect


def redirect_root(request):
    """Redirect root URL to invoices app"""
    return redirect('/invoices/')


urlpatterns = [
    path('', redirect_root),
    path('admin/', admin.site.urls),
    path('invoices/', include('invoices.urls')),
]
