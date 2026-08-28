from django.apps import AppConfig


class ExperimentsConfig(AppConfig):
    name = 'experiments'
    label = 'experiments'
    # Django >= 6 defaults new projects to BigAutoField; pin the historical
    # AutoField so existing installations are not asked for an id migration.
    default_auto_field = 'django.db.models.AutoField'

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out
        from experiments.signal_handlers import transfer_enrollments_to_user, handle_user_logged_out

        user_logged_in.connect(transfer_enrollments_to_user, dispatch_uid="experiments_user_logged_in")
        user_logged_out.connect(handle_user_logged_out, dispatch_uid="experiments_user_logged_out")
