from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path
from apps.core import views
from apps.containers.public_views import lookup

handler400='apps.core.errors.bad_request'
handler403='apps.core.errors.permission_denied'
handler404='apps.core.errors.not_found'
handler500='apps.core.errors.server_error'

urlpatterns = [path("health/live/", views.liveness, name="health_live"), path("health/ready/", views.readiness, name="health_ready"), path("robots.txt", views.robots), path("i18n/", include("django.conf.urls.i18n")), path("", views.landing_redirect)]
urlpatterns += i18n_patterns(path("", views.home, name="home"), path("who-we-are/", views.about, name="about"),
    path("track/", lookup, name="tracking_lookup"), path("track/<str:code>/", lookup, name="tracking_result"),
    path("admin/", admin.site.urls), prefix_default_language=True)
