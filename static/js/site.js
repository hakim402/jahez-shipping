/* Public form enhancement. No fetch, analytics, storage, or provider requests. */
document.addEventListener('alpine:init', () => {
  Alpine.data('trackingForm', () => ({
    busy: false,
    invalid: false,
    init() {
      this.invalid = this.$el.dataset.invalid === 'true';
    },
    submit(event) {
      const valid = /^[A-Za-z0-9-]{8,80}$/.test(this.$refs.reference.value.trim());
      this.invalid = !valid;
      if (!valid) {
        event.preventDefault();
        this.$refs.reference.focus();
        return;
      }
      this.busy = true;
    },
  }));
});
document.addEventListener('DOMContentLoaded', () => {
  const result = document.querySelector('[data-focus-on-load="true"]');
  if (result) result.focus({ preventScroll: false });
});
