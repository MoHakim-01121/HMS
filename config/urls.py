from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from invoices.views.user_views import CompanyLoginView

urlpatterns = [
    path('login/', CompanyLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/?logged_out=1'), name='logout'),
    path('', include('invoices.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
