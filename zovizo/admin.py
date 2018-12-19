from django.contrib import admin

from zovizo.models import Bundle


class BundleAdmin(admin.ModelAdmin):
    list_display = ('amount', 'duration', 'is_active', )


admin.site.register(Bundle, BundleAdmin)
