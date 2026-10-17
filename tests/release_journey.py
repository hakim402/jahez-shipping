"""One synthetic lifecycle shared by the test suite and installed-image acceptance."""
import copy
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import Client

from apps.containers.models import Container
from apps.containers.pipeline import RefreshError
from tests import test_container_admin as admin_helpers
from tests.test_container_refresh import prepared, FIXTURE


def exercise(host="testserver"):
    """All provider results come from a local fixture; never accesses owner storage."""
    cache.clear()
    owner=User.objects.create_superuser("DEMO-release-review",password=None)
    client=Client(enforce_csrf_checks=True,HTTP_HOST=host)
    client.force_login(owner)
    origin="https://"+host
    def get(path):
        return client.get(path,secure=True)
    def post(path,data):
        data={**data,"csrfmiddlewaretoken":client.cookies["jahez_shipping_csrf"].value}
        return client.post(path,data,secure=True,HTTP_ORIGIN=origin)
    def payload(obj=None,**changes):
        if obj:obj.refresh_from_db()
        return admin_helpers.ContainerAdminTests.payload(None,obj,**changes)
    def source(eta):
        data=json.loads(FIXTURE.read_bytes())
        for event in data["result"]["containerList"][0]["nodeList"]:
            if event["movementCode"]=="DG":event["estimateDate"]=eta
        return prepared(json.dumps(data).encode())
    def provider(result):
        assert not connection.in_atomic_block,"Provider must run outside write transactions"
        return result
    def daily(result=None,fail=False):
        output=StringIO()
        with patch("apps.containers.refresh.run_provider",side_effect=RefreshError("timeout") if fail else lambda obj:provider(result)):
            try:call_command("refresh_containers",active=True,stdout=output,stderr=StringIO())
            except CommandError as error:
                assert fail and error.returncode==1
            else:assert not fail
        return json.loads(output.getvalue())

    add="/en/admin/containers/container/add/"
    assert get(add).status_code==200
    data=payload(manual_notes_en="PRIVATE-RELEASE-NOTE",manual_notes_ar="ملاحظة خاصة")
    assert post(add,data).status_code==302
    obj=Container.objects.get(search_reference="DEMOAB123456")
    change=f"/en/admin/containers/container/{obj.pk}/change/"
    refresh=f"/en/admin/containers/container/{obj.pk}/refresh/"
    assert not obj.is_published and not obj.auto_publish_carrier_updates
    assert get(obj.tracking_path()).status_code==404
    assert get(refresh).status_code==200
    # CSRF rejection must happen before the provider is invoked.
    with patch("apps.containers.refresh.run_provider") as external:
        assert client.post(refresh,{},secure=True).status_code==403
        external.assert_not_called()
    first=prepared()
    with patch("apps.containers.refresh.run_provider",side_effect=lambda obj:provider(first)):
        assert post(refresh,{}).status_code==302
    obj.refresh_from_db()
    assert obj.container_number=="TEST1234567" and obj.events.count()==3
    assert not obj.events.filter(is_public=True).exists()
    assert post(change,payload(obj,is_published="on",confirm_publication="on")).status_code==302
    obj.refresh_from_db();before=copy.deepcopy(obj.public_snapshot)
    for lang in ("en","ar"):
        response=get(obj.tracking_path(lang))
        assert response.status_code==200 and "no-store" in response["Cache-Control"]
        assert b"PRIVATE-RELEASE-NOTE" not in response.content and b"DEMOAB123456" not in response.content
    # Default-off: daily changes stay private until a deliberate human review.
    changed=source("2026-02-05")
    assert daily(changed)["changed"]==1
    obj.refresh_from_db();assert obj.public_snapshot==before
    assert post(change,payload(obj,auto_publish_carrier_updates="on",confirm_publication="on")).status_code==302
    obj.refresh_from_db();ids=list(obj.events.values_list("pk",flat=True))
    assert daily(changed)["unchanged"]==1
    obj.refresh_from_db();assert list(obj.events.values_list("pk",flat=True))==ids
    assert daily(source("2026-02-07"))["changed"]==1
    obj.refresh_from_db()
    assert obj.public_snapshot["facts"]["arrival_estimated"]["raw"]=="2026-02-07"
    assert list(obj.events.values_list("pk",flat=True))==ids
    approved=copy.deepcopy(obj.public_snapshot);success=obj.last_refresh_success_at
    assert daily(fail=True)["failed"]==1
    obj.refresh_from_db()
    assert obj.public_snapshot==approved and obj.last_refresh_success_at==success
    assert obj.last_failure_code=="timeout" and obj.refresh_claim is None
    # One human confirmation publishes a public manual update and override, never private notes.
    data=payload(obj,auto_publish_carrier_updates="on",confirm_publication="on",manual_status_override="on_hold")
    data=admin_helpers.ContainerAdminTests.add_event_data(None,data,**{
        "events-0-title_en":"DEMO reviewed office update","events-0-title_ar":"تحديث مكتب تجريبي معتمد",
        "events-0-is_public":"on"})
    assert post(change,data).status_code==302
    obj.refresh_from_db()
    assert obj.public_snapshot["facts"]["status"]=="on_hold"
    assert b"DEMO reviewed office update" in get(obj.tracking_path()).content
    assert b"PRIVATE-RELEASE-NOTE" not in get(obj.tracking_path()).content
    # Preserve the manual inline while archiving; no deletion and no further provider calls.
    manual=obj.events.get(origin="manual")
    data=admin_helpers.ContainerAdminTests.add_event_data(None,payload(obj,is_archived="on",auto_publish_carrier_updates="on"),manual,
        **{"events-0-title_en":manual.title_en,"events-0-title_ar":manual.title_ar,"events-0-is_public":"on"})
    assert post(change,data).status_code==302
    obj.refresh_from_db();assert obj.archived_at and obj.events.count()==4
    assert get(obj.tracking_path()).status_code==404
    with patch("apps.containers.refresh.run_provider") as external:
        output=StringIO();call_command("refresh_containers",active=True,stdout=output)
        assert json.loads(output.getvalue())["selected"]==0
        external.assert_not_called()
    return {"container_id":obj.pk,"events":obj.events.count(),"archived":True,
            "default_off_held":True,"opt_in_changed_public_eta":True,"repeat_deduplicated":True,
            "failed_check_preserved_public":True,"provider_outside_transactions":True,
            "manual_review_and_archive":True,"csrf_enforced":True}
