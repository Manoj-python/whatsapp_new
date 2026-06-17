from django.apps import AppConfig


class Messaging2Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'messaging2'

    def ready(self):
        import messaging2.signals
