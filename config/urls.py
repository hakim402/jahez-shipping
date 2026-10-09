from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path
from apps.core import views

from apps.tracking.views import webhook

urlpatterns = [path("webhooks/17track/", webhook, name="track17_webhook"), path("health/live/", views.liveness, name="health_live"), path("health/ready/", views.readiness, name="health_ready"), path("robots.txt", views.robots), path("i18n/", include("django.conf.urls.i18n")), path("", views.landing_redirect)]
urlpatterns += i18n_patterns(path("", views.home, name="home"), path("who-we-are/", views.about, name="about"), path("admin/", admin.site.urls), prefix_default_language=True)
