// A field opened with a form takes focus only where that does not throw a
// keyboard over the form: on a touch phone the person taps the field first.
export const focusOnOpen = () => typeof window === "undefined" || !window.matchMedia("(pointer: coarse)").matches;
