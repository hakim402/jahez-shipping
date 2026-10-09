"""Translate Django's implicit field captions, preserving their original English metadata."""
from django.utils.translation import gettext_lazy


def localize_generated_labels(models):
    for model in models:
        for field in model._meta.fields:
            if isinstance(field.verbose_name,str) and field.verbose_name==field.name.replace('_',' '):
                field.verbose_name=gettext_lazy(field.verbose_name)
