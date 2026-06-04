from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from hw.views.user_views import CompanyLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', CompanyLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/?logged_out=1'), name='logout'),
    path('', include('hw.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
