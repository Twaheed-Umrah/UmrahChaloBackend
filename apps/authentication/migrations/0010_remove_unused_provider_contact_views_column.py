from django.db import migrations


def remove_unused_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = 'serviceproviderprofiles'
    column_name = 'anonymous_contact_views'

    with connection.cursor() as cursor:
        table_names = set(connection.introspection.table_names(cursor))
        if table_name not in table_names:
            return
        columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    if column_name in columns:
        table = connection.ops.quote_name(table_name)
        column = connection.ops.quote_name(column_name)
        with connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE {table} DROP COLUMN {column}')


def restore_unused_column(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        table_names = set(connection.introspection.table_names(cursor))
        if 'serviceproviderprofiles' not in table_names:
            return
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, 'serviceproviderprofiles'
            )
        }
        if 'anonymous_contact_views' in columns:
            return
    table = connection.ops.quote_name('serviceproviderprofiles')
    column = connection.ops.quote_name('anonymous_contact_views')
    with connection.cursor() as cursor:
        cursor.execute(
            f'ALTER TABLE {table} ADD COLUMN {column} integer NOT NULL DEFAULT 0'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0009_loginattempt_phone_alter_loginattempt_email'),
    ]

    operations = [
        migrations.RunPython(remove_unused_column, restore_unused_column),
    ]
