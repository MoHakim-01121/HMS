from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0017_textchoices_and_verbose_names'),
    ]

    operations = [
        # Rename all tables from invoices_* to hw_*
        migrations.AlterModelTable('UserProfile',         'hw_userprofile'),
        migrations.AlterModelTable('ActivityLog',         'hw_activitylog'),
        migrations.AlterModelTable('Client',              'hw_client'),
        migrations.AlterModelTable('ConfirmationLetter',  'hw_confirmationletter'),
        migrations.AlterModelTable('Room',                'hw_room'),
        migrations.AlterModelTable('Invoice',             'hw_invoice'),
        migrations.AlterModelTable('Reservation',         'hw_reservation'),
        migrations.AlterModelTable('ServiceItem',         'hw_serviceitem'),
        migrations.AlterModelTable('Payment',             'hw_payment'),
        migrations.AlterModelTable('Attachment',          'hw_attachment'),
        migrations.AlterModelTable('Hotel',               'hw_hotel'),

        # Update content types so admin + permissions still work
        migrations.RunSQL(
            sql="UPDATE django_content_type SET app_label = 'hw' WHERE app_label = 'invoices'",
            reverse_sql="UPDATE django_content_type SET app_label = 'invoices' WHERE app_label = 'hw'",
        ),
    ]
