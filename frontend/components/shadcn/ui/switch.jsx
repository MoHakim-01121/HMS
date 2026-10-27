import { cn } from "@/lib/utils";

// On/off switch: a 38×22 track with a white knob that slides right when on.
function Switch({ checked, onCheckedChange, className, ...props }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!checked}
      data-slot="switch"
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "relative h-[22px] w-[38px] flex-none cursor-pointer rounded-full border-0 bg-input p-0 transition-[background-color] duration-150 ease-[ease] aria-checked:bg-foreground",
        "after:absolute after:top-[3px] after:left-[3px] after:size-4 after:rounded-full after:bg-white after:shadow-knob after:transition-[translate] after:duration-150 after:ease-[ease] after:content-[''] aria-checked:after:translate-x-4",
        "disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring",
        className,
      )}
      {...props}
    />
  );
}

export { Switch };
