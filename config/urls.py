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
from django.conf import settings
from django.conf.urls.static import static


def redirect_root(request):
    """Redirect root URL to invoices app"""
    return redirect('/invoices/')


urlpatterns = [
    path('', redirect_root),
    # path('admin/', admin.site.urls),  # Dinonaktifkan karena admin tidak digunakan
    path('invoices/', include('invoices.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
