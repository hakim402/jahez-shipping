# Admin guide / دليل الإدارة

The public frontend is approved and unchanged by this admin update.

## English

### Daily work

1. Open **Customers** and add the customer's name and contact details. These stay private.
2. Open **Shipments → Add**. Choose the customer, transport method and current status. Use Manual tracking unless you have a supported carrier reference.
3. Save, then add products and timeline updates in the shipment form. Each row has a link to its own edit page. Documents, carrier references and the full timeline are available from the saved shipment.
4. Enter the public route and product/update text in English and Arabic. Leave an unknown arrival estimate blank. Date help shows the business timezone.
5. Review each product/update before publishing it. Then enable **Publish safe tracking summary**. Share the private JAHEZ reference with the intended customer only.

The status field controls the shipment's overall stage. Adding a timeline event does not silently change it. **Status control**, **Record history**, file metadata and other advanced details are expandable. All four dashboard cards open matching filtered lists, excluding archived shipments from the active counts and results.

### Remove a record

Use **Archive shipment** for a shipment you no longer need in daily work. Archiving hides customer tracking while preserving records. Restore makes it editable again and keeps publication off.

For permanent removal, open an eligible record's edit page and choose **Delete**. Enter a reason, tick the confirmation, then choose **Delete permanently**. The page expires after 30 minutes and refuses deletion if the record changed. Only that record is removed; bulk deletion and automatic cascades are unavailable.

| Record | Deletion rule |
|---|---|
| Customer | Allowed only when no shipment is linked |
| Shipment | Archive first; all protected linked records must be absent |
| Product | Allowed with deletion permission; public products also require publication permission |
| Manual timeline update | Allowed when it is not a protected AI source; public updates also require publication permission |
| Carrier reference | Allowed only before registration starts and when no event/job is linked |
| Private document | Allowed only when no AI draft uses it; the private file is removed after database commit |
| Carrier history, audit history, integration jobs/receipts and AI history | Retained; no delete action |

Audit history is retained even when an eligible archived shipment is deleted. File cleanup failures stay in a private retry queue and are retried by the scheduled Shipping worker. Deleting a document is not complete file erasure until cleanup succeeds; independent backups may still retain it under their own retention policy.

Owners/superusers have deletion access. The standard Operations and Read Only groups are not automatically granted deletion permissions. An owner may explicitly grant the relevant Django `delete_*` permission to designated staff; server-side view, deletion and publication checks still apply. This update did not assign new permissions to existing users.

### Navigation

- **Daily work:** Dashboard, Shipments, Customers, Private documents.
- **Tools:** Operational assistant, AI Workspace, Integration health.
- **Administration:** collapsed by default; audit and technical history, users and groups.

Products and timeline/reference editing are reached from a shipment rather than repeated in the sidebar. AI drafts appear in the AI Workspace; the full list remains available through its own standard admin URL. Language and theme controls remain in the user menu. Technical history stays available to authorized staff.

## العربية

### العمل اليومي

1. افتح **العملاء** وأضف الاسم وبيانات الاتصال. تبقى هذه البيانات خاصة.
2. افتح **الشحنات ← إضافة**. اختر العميل وطريقة النقل والحالة الحالية. استخدم التتبع اليدوي ما لم يتوفر مرجع تدعمه شركة النقل.
3. احفظ الشحنة ثم أضف المنتجات وتحديثات التتبع. يتيح رابط كل صف فتح صفحة تعديله. يمكن الوصول إلى المستندات ومراجع شركات النقل والتحديثات الكاملة من الشحنة المحفوظة.
4. أدخل المسار العام ونصوص المنتجات والتحديثات بالإنجليزية والعربية. اترك موعد الوصول فارغاً إذا لم يُعرف. تظهر المنطقة الزمنية في مساعدة التاريخ.
5. راجع المنتج أو التحديث قبل نشره، ثم فعّل **نشر ملخص التتبع المعتمد**. شارك مرجع جاهز الخاص مع العميل المقصود فقط.

تحدد خانة الحالة المرحلة العامة للشحنة. إضافة تحديث للتتبع لا تغيّر الحالة تلقائياً. يمكن توسيع الأقسام المتقدمة عند الحاجة. تفتح بطاقات لوحة الإدارة قوائم الشحنات المناسبة.

### حذف سجل

استخدم **أرشفة الشحنة** لإخفائها من التتبع العام مع الاحتفاظ بسجلاتها. تتيح الاستعادة التعديل مجدداً دون نشر تلقائي.

للحذف النهائي، افتح صفحة تعديل سجل قابل للحذف، واختر **حذف**، ثم أدخل السبب وحدد مربع التأكيد واضغط **حذف نهائي**. تنتهي صلاحية الصفحة بعد 30 دقيقة. إذا تغير السجل، يجب مراجعته مجدداً. لا يُحذف أي سجل مرتبط تلقائياً ولا يتوفر حذف جماعي.

- لا يمكن حذف عميل مرتبط بشحنة.
- يجب أرشفة الشحنة وإزالة السجلات المرتبطة القابلة للحذف أولاً.
- يمكن حذف المنتجات والتحديثات اليدوية حسب الصلاحيات؛ حذف ما هو منشور يتطلب صلاحية النشر أيضاً.
- لا يمكن حذف مرجع شركة نقل بدأ تسجيله، أو سجل مرتبط بمهمة أو تحديث.
- لا يمكن حذف مستند أو تحديث تستخدمه مسودة ذكاء اصطناعي محفوظة.
- تبقى سجلات شركات النقل والتدقيق والتكامل والذكاء الاصطناعي محفوظة.
- يُحذف الملف الخاص بعد نجاح حذف سجل المستند. عند تعذر حذف الملف، تعيد خدمة الشحن المحاولة لاحقاً. قد تبقى نسخة في النسخ الاحتياطية حسب سياسة الاحتفاظ.

تتوفر صلاحية الحذف للمالك أو المدير الأعلى. لم تُمنح تلقائياً لمجموعتي العمليات والقراءة فقط. يستطيع المالك منح الصلاحيات المناسبة لموظفين محددين.

### التنقل

**العمل اليومي** للشحنات والعملاء والمستندات. **الأدوات** للمساعد ومسودات الذكاء الاصطناعي وحالة التكامل. **الإدارة** للسجل التقني والتدقيق والمستخدمين والمجموعات، وهي مطوية افتراضياً. توجد أدوات اللغة والمظهر في قائمة المستخدم.

## Local verification and release note — 10 October 2026

- 186 isolated Django tests passed, including 14 new admin/deletion tests. Tests use `config.settings.test` with temporary private storage and integrations disabled.
- Schema migration `shipments.0003` adds the private file-removal outbox, retains audit rows via a nullable shipment link, and updates tracking-mode captions without changing stored values.
- Applied to the local Shipping database after a private SQLite online snapshot. Customer/shipment/child/document/audit row counts were unchanged. The snapshot is database-only, not a complete private-file backup.
- Refreshed only the Shipping development worker to load cleanup retries. No production or sibling service changed. No business record was deleted through the browser; deletions were tested against isolated fixtures.
- Production candidate: `jahez-shipping:admin-review-20261010`, built locally. Offline migrations/static/private/public/security checks passed with networking disabled and no live volumes. Locked dependency check passed.
- HSTS warning `security.W004` remains deliberately deferred until actual TLS verification. Phase 9 deployment, live provider checks and server backup scheduling retain their separate evidence/approval requirements.
- Before any live upgrade: use the guided deployment/release procedure, take a complete verified matching-version backup, apply migration 0003 while writers are paused, then start the matching web/worker image. Do not roll an old image onto the new schema or copy development data to production.
