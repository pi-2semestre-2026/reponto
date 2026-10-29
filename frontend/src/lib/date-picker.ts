/** Open native date selection for a click anywhere in the input. */
export function openDatePicker(input: HTMLInputElement) {
  try { input.showPicker?.(); } catch { input.focus(); }
}
