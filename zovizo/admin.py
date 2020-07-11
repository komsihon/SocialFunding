from django.contrib import admin

from zovizo.models import Bundle


class BundleAdmin(admin.ModelAdmin):
    list_display = ('amount', 'duration', 'is_active', 'show_on_home')
    fields = ('amount', 'currency', 'duration', 'is_active', 'show_on_home', 'is_investor_pack', )


admin.site.register(Bundle, BundleAdmin)
