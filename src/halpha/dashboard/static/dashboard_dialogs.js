    (function () {
      let activeDialog = null;

      function dialogElements() {
        return {
          backdrop: document.querySelector("#dashboard-dialog-backdrop"),
          title: document.querySelector("#dashboard-dialog-title"),
          message: document.querySelector("#dashboard-dialog-message"),
          label: document.querySelector("#dashboard-dialog-input-label"),
          input: document.querySelector("#dashboard-dialog-input"),
          hint: document.querySelector("#dashboard-dialog-hint"),
          cancel: document.querySelector("#dashboard-dialog-cancel"),
          confirm: document.querySelector("#dashboard-dialog-confirm"),
        };
      }

      function openDialog(options) {
        const nodes = dialogElements();
        if (activeDialog) {
          closeDialog(false);
        }
        return new Promise((resolve) => {
          const requiredText = options.requiredText || "";
          activeDialog = {
            resolve,
            requiredText,
            previousFocus: document.activeElement,
          };
          nodes.title.textContent = options.title || "Confirm action";
          nodes.message.textContent = options.message || "";
          nodes.hint.textContent = requiredText ? `Type ${requiredText} to enable this action.` : (options.hint || "");
          nodes.input.value = "";
          nodes.input.placeholder = requiredText;
          nodes.input.classList.toggle("hidden", !requiredText);
          nodes.label.classList.toggle("hidden", !requiredText);
          nodes.confirm.textContent = options.confirmLabel || "Confirm";
          nodes.cancel.textContent = options.cancelLabel || "Cancel";
          nodes.confirm.className = options.danger ? "danger-button" : "primary-button";
          nodes.backdrop.classList.remove("hidden");
          nodes.backdrop.setAttribute("aria-hidden", "false");
          updateConfirmState();
          window.setTimeout(() => (requiredText ? nodes.input : nodes.cancel).focus(), 0);
        });
      }

      function updateConfirmState() {
        const nodes = dialogElements();
        if (!activeDialog) return;
        const requiredText = activeDialog.requiredText || "";
        nodes.confirm.disabled = Boolean(requiredText && nodes.input.value !== requiredText);
      }

      function closeDialog(confirmed) {
        if (!activeDialog) return;
        const nodes = dialogElements();
        const dialog = activeDialog;
        const value = nodes.input.value;
        activeDialog = null;
        nodes.backdrop.classList.add("hidden");
        nodes.backdrop.setAttribute("aria-hidden", "true");
        nodes.input.value = "";
        nodes.hint.textContent = "";
        nodes.confirm.disabled = false;
        if (dialog.previousFocus && typeof dialog.previousFocus.focus === "function") {
          dialog.previousFocus.focus();
        }
        dialog.resolve({confirmed: Boolean(confirmed), value});
      }

      async function confirmAction(options) {
        const result = await openDialog(options);
        return result.confirmed;
      }

      async function typedConfirmation(options) {
        const result = await openDialog(options);
        return result.confirmed && result.value === options.requiredText;
      }

      function wire() {
        const nodes = dialogElements();
        nodes.cancel.addEventListener("click", () => closeDialog(false));
        nodes.confirm.addEventListener("click", () => closeDialog(true));
        nodes.input.addEventListener("input", updateConfirmState);
        nodes.backdrop.addEventListener("click", (event) => {
          if (event.target === nodes.backdrop) {
            closeDialog(false);
          }
        });
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape" && activeDialog) {
            closeDialog(false);
          }
        });
      }

      window.HalphaDashboardDialogs = {
        confirmAction,
        typedConfirmation,
        wire,
      };
    })();
