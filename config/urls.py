from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

def redirect_root(request):
    return redirect('/invoices/')

urlpatterns = [
    path('', redirect_root),
    path('admin/', admin.site.urls),
    path('invoices/', include('invoices.urls')),
]
