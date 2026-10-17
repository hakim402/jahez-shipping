"""Disposable cleaned-schema upgrade with actual retained auth/session/admin rows."""
import hashlib
import json

from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ContainerMigrationTests(TransactionTestCase):
    def test_existing_cleaned_090_upgrade_preserves_auth_session_and_only_adds_two_tables(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("containers", None)])
        baseline_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "containers"]
        old = executor.loader.project_state(baseline_targets).apps
        User = old.get_model("auth", "User")
        Group = old.get_model("auth", "Group")
        Permission = old.get_model("auth", "Permission")
        ContentType = old.get_model("contenttypes", "ContentType")
        LogEntry = old.get_model("admin", "LogEntry")
        # Remove metadata left by reversing the test database's initial new-app migration.
        ContentType.objects.filter(app_label="containers").delete()
        user = User.objects.create(username="DEMO-retained-owner", password=make_password("synthetic-only-password"), is_staff=True, is_superuser=True, date_joined=timezone.now())
        content_type, _ = ContentType.objects.get_or_create(app_label="auth", model="user")
        permission, _ = Permission.objects.get_or_create(content_type_id=content_type.pk, codename="view_user", defaults={"name": "Can view user"})
        group = Group.objects.create(name="DEMO retained group")
        group.permissions.add(permission)
        user.groups.add(group)
        user.user_permissions.add(permission)
        log = LogEntry.objects.create(user_id=user.pk, content_type_id=content_type.pk, object_id=str(user.pk), object_repr="DEMO retained admin entry", action_flag=2, change_message="Synthetic retained history")
        session = SessionStore()
        session["_auth_user_id"] = str(user.pk)
        session["proof"] = "DEMO-retained-session"
        session.save()

        def snapshot(table):
            with connection.cursor() as cursor:
                cursor.execute('SELECT * FROM "' + table + '" ORDER BY rowid')
                return hashlib.sha256(json.dumps(cursor.fetchall(), default=str).encode()).hexdigest()

        tables_before = set(connection.introspection.table_names())
        retained = {name: snapshot(name) for name in tables_before if name != "django_migrations"}
        try:
            executor = MigrationExecutor(connection)
            self.assertEqual([(m.app_label, m.name, backwards) for m, backwards in executor.migration_plan([("containers", "0001_initial")])], [("containers", "0001_initial", False)])
            executor.migrate([("containers", "0001_initial")])
            tables_after = set(connection.introspection.table_names())
            self.assertEqual(tables_after - tables_before, {"containers_container", "containers_containerevent"})
            self.assertFalse(tables_before - tables_after)
            for table, digest in retained.items():
                self.assertEqual(snapshot(table), digest, table)
            self.assertEqual(SessionStore(session_key=session.session_key)["proof"], "DEMO-retained-session")
            from django.contrib.auth.models import User as CurrentUser
            restored = CurrentUser.objects.get(pk=user.pk)
            self.assertTrue(restored.check_password("synthetic-only-password"))
            self.assertTrue(restored.groups.filter(pk=group.pk).exists())
            self.assertTrue(restored.user_permissions.filter(pk=permission.pk).exists())
            self.assertEqual(LogEntry.objects.get(pk=log.pk).content_type_id, content_type.pk)
            self.assertFalse(any(name.startswith(("shipments_", "tracking_", "ai_")) for name in tables_after))
        finally:
            latest = MigrationExecutor(connection)
            latest.migrate(latest.loader.graph.leaf_nodes())

    def test_public_fields_upgrade_preserves_existing_journeys_and_defaults_to_unreviewed_private_snapshot(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("containers", "0001_initial")])
        old = executor.loader.project_state([("containers", "0001_initial")]).apps
        Parent = old.get_model("containers", "Container")
        Event = old.get_model("containers", "ContainerEvent")
        parent = Parent.objects.create(search_reference="DEMOAB123456", is_published=True, manual_notes_en="DEMO retained private note")
        event = Event.objects.create(container=parent, origin="manual", title_en="DEMO event", dedupe_key="a"*64)
        before = Parent.objects.values().get(pk=parent.pk)
        event_before = Event.objects.values().get(pk=event.pk)
        try:
            executor = MigrationExecutor(connection)
            self.assertEqual([(m.name, backwards) for m,backwards in executor.migration_plan([("containers","0002_reviewed_public_tracking")])], [("0002_reviewed_public_tracking",False)])
            executor.migrate([("containers","0002_reviewed_public_tracking")])
            from apps.containers.models import Container, ContainerEvent
            current = Container.objects.values().get(pk=parent.pk)
            self.assertEqual({key:current[key] for key in before}, before)
            self.assertEqual(ContainerEvent.objects.values().get(pk=event.pk),event_before)
            self.assertFalse(current["auto_publish_carrier_updates"])
            self.assertEqual(current["public_snapshot"],{})
        finally:
            latest = MigrationExecutor(connection)
            latest.migrate(latest.loader.graph.leaf_nodes())
