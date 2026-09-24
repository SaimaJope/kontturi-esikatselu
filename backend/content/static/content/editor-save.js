/* Wagtail's Draftail widget writes its hidden input after a 250 ms debounce.
 * Flush current editor state before a fast save/publish can serialize the form.
 * Use Draftail's serializer so formatting and entity references are preserved.
 */
(() => {
  "use strict";

  function flushRichText(form, event) {
    if (!form || form.id !== "page-edit-form") return;

    try {
      const pending = [];
      for (const input of form.querySelectorAll("input[data-draftail-input]")) {
        if (input.disabled || !input.isConnected || !input.draftailEditor) continue;
        const serialize = window.Draftail?.serialiseEditorStateToRaw;
        if (typeof serialize !== "function" || typeof input.draftailEditor.getEditorState !== "function") {
          throw new Error("Draftail's current-state serializer is unavailable.");
        }
        const state = serialize(input.draftailEditor.getEditorState());
        pending.push({ input, state, value: JSON.stringify(state) });
      }
      // Only update fields after every editor was serialized successfully.
      for (const { input, state, value } of pending) {
        input.rawContentState = state;
        input.value = value;
      }
    } catch (error) {
      event.preventDefault();
      event.stopImmediatePropagation();
      console.error("Rich-text synchronization failed; saving was cancelled.", error);
      window.alert("Tekstin tallennus ei onnistunut. Sisältösi on edelleen editorissa. Kopioi teksti talteen ja ota yhteyttä ylläpitäjään ennen sivun päivittämistä.");
    }
  }

  // Capture before Wagtail's action handlers build FormData. This also covers
  // action buttons outside the form that reference it via the form attribute.
  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button, input") : null;
    if (button && (button.type === "submit" || button.type === "image")) {
      flushRichText(button.form, event);
    }
  }, true);

  // Covers keyboard submission and requestSubmit() without a preceding click.
  document.addEventListener("submit", (event) => {
    flushRichText(event.target, event);
  }, true);
})();
