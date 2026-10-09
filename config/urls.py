from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from hw.views.media_views import protected_media
from hw.views.user_views import CompanyLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', CompanyLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/?logged_out=1'), name='logout'),
    # Uploads go through a permission check, in development and production alike.
    path('media/<path:path>', protected_media, name='protected_media'),
    path('', include('hw.urls')),
]
