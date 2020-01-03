from django.contrib import admin

from zovizo.models import Bundle


class BundleAdmin(admin.ModelAdmin):
    list_display = ('amount', 'duration', 'is_active', 'show_on_home')
    fields = ('amount', 'duration', 'is_active', 'show_on_home', )


admin.site.register(Bundle, BundleAdmin)
