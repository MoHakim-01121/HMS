// Mirror of room_type_name() in hw/models/hotel.py — keep the two in step.
// `occupancyLabels` maps a guest count to its word ({ "4": "Quad" }) and comes
// from the server, so both sides read the same vocabulary.
export function suggestRoomTypeName(capacity, view, occupancyLabels, viewChoices) {
  const n = Number(capacity) || 0;
  if (n < 1) return "";
  const parts = [occupancyLabels[String(n)] || `${n} Pax`];
  if (view && view !== "other") {
    const choice = viewChoices.find((c) => c.value === view);
    if (choice) parts.push(choice.label);
  }
  return parts.join(" ");
}
