import { createContext, forwardRef, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { router, usePage } from "@inertiajs/react";
import { Dialog, DialogCloseButton, DialogContent, DialogTitle } from "./ui/dialog.jsx";
import ConfirmDialog from "./confirm-dialog.jsx";
import { resolvePage } from "../../utils/resolvePage.js";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";

// Consumed by page-back.jsx/form-actions.jsx/form-panel.jsx so the SAME
// Form.jsx page component can render either as a real full page (direct URL
// visit — ctx is null/inModal:false, everything behaves exactly as before)
// or as dialog content (ctx.inModal:true — back link hidden, Cancel closes
// the dialog instead of navigating, no double-card chrome).
//
// Pinned to a global rather than created per module evaluation, because this
// module does not always get evaluated once. resolvePage eagerly globs every
// page, and those pages import this file back — so an HMR update (or any
// second copy of the module in the graph) can leave the provider holding one
// context object while the consumers below read another. React then answers
// every useContext with the default, null, and the app silently degrades:
// useFormModal hands back the NOOP so "+ Create New" does nothing, and a form
// that did open renders as if it were a full page — back link, kicker, 32px
// title, its own card — inside the dialog, under the fallback "Form" heading.
// One shared object across every copy removes that whole failure mode.
const CONTEXT_KEY = "__hmsFormModalContext";
export const FormModalContext =
  globalThis[CONTEXT_KEY] || (globalThis[CONTEXT_KEY] = createContext(null));

// How long openForm waits for the payload before falling back to the skeleton.
// One frame, deliberately: an already-cached payload (hover-prefetch, or the
// same form opened twice) settles on the microtask queue and so beats this
// timer every time, letting the dialog mount once already carrying its real
// content — one entrance animation, at the final size, no placeholder at all.
// Anything that has to touch the network loses the race and gets the skeleton
// immediately, which is the point: waiting for the payload before opening cost
// ~150ms of dead air after the click (measured), and dead air after a click is
// its own kind of unsmooth. The skeleton keeps the response instant, and the
// height transition in tailwind.css turns the hand-off into an eased grow
// rather than the 455px snap it used to be.
const SKELETON_DELAY = 16;

// ── The form dialog's chrome ────────────────────────────────────────────────
// A header bar that stays put, a body that scrolls, and the form's action row
// stuck to the bottom of that body. `layout="a"` is the approved CL/Invoice
// form (form-a.jsx): 760px wide, a borderless header, tighter body padding.
// Exported for the dialogs that build this chrome themselves.
export function ModalContent({ layout, className, ...props }) {
  return (
    <DialogContent showCloseButton={false} {...props} className={cn(
      "flex max-h-[min(86vh,820px)] flex-col gap-0 overflow-hidden rounded-[24px] p-0 max-[600px]:max-h-[92vh] max-[600px]:rounded-[20px]",
      // Centre in what the shell leaves, not in the window: a dialog centred on
      // the viewport sits half a sidebar to the left of the content it belongs
      // to on desktop. --content-left is published by AppLayout (it follows
      // the rail when the sidebar collapses); --topbar-h is the shell's own
      // content offset. Both are desktop-only, so phones keep the plain
      // viewport-centred dialog they already had.
      "min-[601px]:left-[calc(50%_+_var(--content-left,0px)/2)] min-[601px]:top-[calc(50%_+_var(--topbar-h,0px)/2)]",
      className,
      layout === "a" && "max-w-[760px] rounded-[20px] sm:max-w-[760px]",
    )} />
  );
}

export const ModalHead = forwardRef(({ layout, className, ...props }, ref) => (
  <div ref={ref} {...props} className={cn(
    layout === "a"
      ? "flex shrink-0 items-center justify-between gap-4 pt-4 pr-4 pb-0 pl-6 max-[640px]:pr-3 max-[640px]:pl-4"
      : "flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4 max-[600px]:p-4",
    className,
  )} />
));
ModalHead.displayName = "ModalHead";

export const ModalTitle = ({ className, ...props }) => (
  <DialogTitle {...props} className={cn("text-[16px] leading-[1.4] font-semibold tracking-[-0.01em] text-foreground", className)} />
);

export const ModalSub = ({ children }) => <div className="mt-0.5 text-[14px] leading-[1.45] text-muted-foreground">{children}</div>;

// The body's height is written by ModalFrame and eased here; a deliberately
// gentle curve, since over ~400px a sharp ease-out reads as a jump.
export const ModalBody = forwardRef(({ layout, className, ...props }, ref) => (
  <div ref={ref} data-slot="modal-body" {...props} className={cn(
    "min-h-0 flex-[1_1_auto] overflow-y-auto [scrollbar-gutter:stable] transition-[height] duration-[260ms] ease-[cubic-bezier(0.4,0,0.2,1)]",
    layout === "a" ? "px-6 pt-4 pb-5 max-[640px]:px-4" : "px-5 py-6 max-[600px]:px-4 max-[600px]:py-5",
    className,
  )} />
));
ModalBody.displayName = "ModalBody";

// The action row at the bottom of a form: inside a dialog body it sticks to
// the bottom edge, bleeding over the body's padding so it spans the dialog.
export const actionsClass = (layout) => layout === "a"
  ? "flex items-center justify-end gap-2 in-data-[slot=modal-body]:sticky in-data-[slot=modal-body]:-bottom-5 in-data-[slot=modal-body]:mx-[-24px] in-data-[slot=modal-body]:mt-5 in-data-[slot=modal-body]:mb-[-20px] in-data-[slot=modal-body]:border-t in-data-[slot=modal-body]:border-border in-data-[slot=modal-body]:bg-card in-data-[slot=modal-body]:px-5 in-data-[slot=modal-body]:py-4 max-[640px]:flex-wrap max-[640px]:in-data-[slot=modal-body]:mx-[-16px] max-[640px]:in-data-[slot=modal-body]:px-4 max-[640px]:in-data-[slot=modal-body]:py-3"
  : "flex justify-end gap-2 in-data-[slot=modal-body]:sticky in-data-[slot=modal-body]:-bottom-6 in-data-[slot=modal-body]:mx-[-20px] in-data-[slot=modal-body]:mt-2 in-data-[slot=modal-body]:mb-[-24px] in-data-[slot=modal-body]:border-t in-data-[slot=modal-body]:border-border in-data-[slot=modal-body]:bg-card in-data-[slot=modal-body]:px-5 in-data-[slot=modal-body]:py-4 max-[600px]:in-data-[slot=modal-body]:-bottom-5 max-[600px]:in-data-[slot=modal-body]:mx-[-16px] max-[600px]:in-data-[slot=modal-body]:mb-[-20px] max-[600px]:in-data-[slot=modal-body]:px-4";

// A prefetched payload is only worth reusing for as long as it is plausibly
// still current. Anything that mutates data goes through an Inertia visit, and
// the success/error handlers below drop the whole cache on any of them, so this
// ceiling only guards against a form left un-clicked while someone else edits
// the same record in another tab.
const PREFETCH_TTL = 15000;

export function FormModalProvider({ children }) {
  const { t } = useI18n();
  const { version } = usePage();
  const [modal, setModal] = useState(null); // { status: 'loading'|'ready', Component, props, title }
  // Published by whichever FormHeader is mounted inside the dialog (see
  // form-header.jsx). The page component owns the real title/subtitle, but in
  // Homlu's layout the title belongs to the fixed header bar, above the
  // scrolling body — so the header hands it up here instead of drawing it
  // itself. Keeps all 11 Form.jsx pages untouched.
  const [header, setHeader] = useState(null);

  // url -> { at, promise }. Holds the in-flight request as well as the settled
  // one, so hovering a trigger and then clicking it reuses the same fetch
  // instead of racing a second copy of it.
  const cache = useRef(new Map());
  // Guards against a slow first open resolving after a second one started.
  const seq = useRef(0);

  // Typing in the form marks it dirty; closing a dirty form (Escape, scrim,
  // ×, Cancel) asks before throwing the input away. A save or a validation
  // round trip closes it through `drop` below, without asking.
  const dirty = useRef(false);
  const [asking, setAsking] = useState(false);
  const close = useCallback(() => {
    dirty.current = false;
    setAsking(false);
    setModal(null);
    window.dispatchEvent(new Event("hms:clean"));
  }, []);
  const requestClose = useCallback(() => (dirty.current ? setAsking(true) : close()), [close]);

  const load = useCallback((url) => {
    const hit = cache.current.get(url);
    if (hit && Date.now() - hit.at < PREFETCH_TTL) return hit.promise;
    const promise = (async () => {
      const res = await fetch(url, {
        headers: {
          "X-Inertia": "true",
          "X-Inertia-Version": version || "",
          Accept: "text/html, application/xhtml+xml",
        },
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      const Component = await resolvePage(data.component);
      if (!Component) throw new Error(`unresolved page component: ${data.component}`);
      return { Component, props: data.props, title: data.component };
    })();
    // A failed fetch must not be remembered — the click that follows a failed
    // prefetch has to be free to try again (and to fall back to a real
    // navigation) rather than inherit the rejection.
    promise.catch(() => {
      if (cache.current.get(url)?.promise === promise) cache.current.delete(url);
    });
    cache.current.set(url, { at: Date.now(), promise });
    return promise;
  }, [version]);

  // Warm the payload on hover/focus of a trigger. Nothing renders as a result;
  // it only means the click that follows has the form already in hand.
  const prefetch = useCallback((url) => { load(url).catch(() => {}); }, [load]);

  const openForm = useCallback((url) => {
    const token = ++seq.current;
    dirty.current = false;
    setHeader(null); // don't show the previous form's title while this one loads
    let settled = false;
    load(url).then(
      (ready) => {
        settled = true;
        if (token === seq.current) setModal({ status: "ready", ...ready });
      },
      () => {
        settled = true;
        // Quota/network/version-mismatch fallback — a real navigation always works.
        if (token === seq.current) window.location.assign(url);
      }
    );
    setTimeout(() => {
      if (!settled && token === seq.current) setModal({ status: "loading" });
    }, SKELETON_DELAY);
  }, [load]);

  // Any Inertia visit that completes while the modal is open means the real
  // background page has moved on — either the submit succeeded and
  // redirected (list/detail now shows fresh data: router "success"), or
  // validation failed and the server re-rendered the same form as a full
  // page (nothing lost, the server already echoes submitted values + errors
  // — Inertia fires "error", not "success", whenever the response's props
  // carry validation errors). Either way our detached dialog copy is stale,
  // so drop it rather than leave it open on top of a page that no longer
  // matches what triggered it.
  useEffect(() => {
    const drop = () => {
      // Same staleness argument applies to anything already prefetched: the
      // visit that just landed may well be the redirect after a save.
      cache.current.clear();
      seq.current++;
      dirty.current = false;
      setAsking(false);
      setModal((m) => (m ? null : m));
    };
    const offSuccess = router.on("success", drop);
    const offError = router.on("error", drop);
    return () => { offSuccess(); offError(); };
  }, []);

  // `openForm` is called as a plain function at ~20 sites; `prefetch` rides
  // along as a property so those call sites keep working untouched and can opt
  // into warming on hover with one extra prop.
  const trigger = useMemo(() => {
    const fn = (url) => openForm(url);
    fn.prefetch = prefetch;
    return fn;
  }, [openForm, prefetch]);

  // Radix keeps the content mounted through the closing animation. Rendering
  // straight off `modal` therefore blanked the dialog out (to nothing before,
  // to the skeleton now) for the whole 200ms it spent fading away; holding on
  // to the last one lets it close showing the form the user was just looking at.
  const lastShown = useRef(null);
  if (modal) lastShown.current = modal;
  const shown = modal || lastShown.current;

  return (
    <FormModalContext.Provider value={{ openForm: trigger, inModal: false }}>
      {children}
      <Dialog open={!!modal} onOpenChange={(open) => { if (!open) requestClose(); }}>
        {/* The scrim (black/50 + backdrop-blur-xs) comes from DialogOverlay and
            is deliberately not overridden here: this modal was briefly the only
            overlay in HMS without blur, chasing Homlu's measured flat scrim,
            which read as inconsistent next to the ⌘K palette and every other
            dialog. See dialog.jsx. */}
        <ModalContent className="sm:max-w-3xl" layout={header?.layout}
          onInputCapture={() => { dirty.current = true; }}>
          <ModalFrame
            title={header?.title || (shown?.status === "loading" ? t("Loading…") : t("Form"))}
            sub={header?.sub}
            layout={header?.layout}
            status={shown?.status}
            body={shown?.status === "ready" && shown.Component ? (
              <FormModalContext.Provider value={{ openForm: trigger, inModal: true, close: requestClose, setHeader }}>
                <shown.Component {...shown.props} />
              </FormModalContext.Provider>
            ) : <FormSkeleton />}
          />
        </ModalContent>
      </Dialog>
      <DiscardDialog open={asking} onKeep={() => setAsking(false)} onDiscard={close} />
    </FormModalContext.Provider>
  );
}

// "Discard changes?": keep editing is the safe default.
function DiscardDialog({ open, onKeep, onDiscard }) {
  const { t } = useI18n();
  return (
    <ConfirmDialog open={open} icon="alert" title="Discard changes?"
      message={t("What you typed in this form has not been saved.")}
      confirmLabel="Discard" cancelLabel="Keep editing"
      onConfirm={onDiscard} onClose={onKeep} />
  );
}

// The same dialog frame, for a form page that was NOT opened through
// openForm — a direct URL visit (/cl/new/), the location.assign fallback
// above, or the server re-rendering the page with validation errors.
//
// Those paths used to fall back to the page-shaped layout: back link, kicker,
// 32px title, and the form inside its own card. That is a second, differently
// chromed copy of a form the app otherwise only ever shows as this dialog —
// same fields, same actions, two skins. Wrapping the page here instead means
// the form has exactly one presentation, whichever way it is reached.
//
// The children run under inModal:true, so FormHeader hands its title up to the
// frame (rather than drawing it again inside), PageBack drops out and
// FormPanel stops painting a card inside the dialog's own surface — the same
// three adaptations they already make for the provider's dialog.
export function StandaloneFormModal({ closeHref = "/", children }) {
  const { t } = useI18n();
  const parent = useContext(FormModalContext);
  const [header, setHeader] = useState(null);
  const [open, setOpen] = useState(true);
  const dirty = useRef(false);
  const [asking, setAsking] = useState(false);

  // Nothing is behind this dialog to fall back to (the page IS the form), so
  // dismissing it — Escape, scrim click, Cancel — has to navigate.
  const close = useCallback(() => {
    dirty.current = false;
    setAsking(false);
    setOpen(false);
    window.dispatchEvent(new Event("hms:clean"));
    router.visit(closeHref);
  }, [closeHref]);
  const requestClose = useCallback(() => (dirty.current ? setAsking(true) : close()), [close]);

  const value = useMemo(
    () => ({ openForm: parent?.openForm || NOOP, inModal: true, close: requestClose, setHeader }),
    [parent, requestClose]
  );

  return (
    <>
    <Dialog open={open} onOpenChange={(o) => { if (!o) requestClose(); }}>
      <ModalContent className="sm:max-w-3xl" layout={header?.layout}
        onInputCapture={() => { dirty.current = true; }}>
        <ModalFrame
          title={header?.title || t("Form")}
          sub={header?.sub}
          layout={header?.layout}
          status="ready"
          body={<FormModalContext.Provider value={value}>{children}</FormModalContext.Provider>}
        />
      </ModalContent>
    </Dialog>
    <DiscardDialog open={asking} onKeep={() => setAsking(false)} onDiscard={close} />
    </>
  );
}

// A form page opened by URL (refresh, shared link) has no dialog around it.
// Wrap its default export with this so it still renders as the one modal
// presentation every form uses, instead of falling back to a full page.
// `closeHref` is where dismissing goes — a string or props => string.
export function withStandaloneModal(Body, closeHref) {
  function StandaloneWhenDirect(props) {
    if (useContext(FormModalContext)?.inModal) return <Body {...props} />;
    const href = typeof closeHref === "function" ? closeHref(props) : closeHref;
    return <StandaloneFormModal closeHref={href}><Body {...props} /></StandaloneFormModal>;
  }
  StandaloneWhenDirect.displayName = `withStandaloneModal(${Body.name || "Form"})`;
  return StandaloneWhenDirect;
}

// Splitting head/body out here is what lets the height of the dialog be driven
// by its content rather than snapped to it.
//
// The dialog used to mount at whatever the loading placeholder measured (~319px
// against a 900px viewport) and then jump straight to the clamped full height
// (~774px) the moment the payload landed — a 455px discontinuity, on every
// form, that happened one frame after the entrance animation had finished. It
// read as the modal glitching rather than opening. Fixing it means the body's
// height has to be an animatable length, so it is measured off the content and
// written here; ModalBody's height transition does the rest.
//
// The observer stays live for the lifetime of the dialog rather than running
// once on swap, so the same easing covers content that changes later — adding
// a reservation or payment row on the Invoice form, or an error summary
// appearing above the fields.
function ModalFrame({ title, sub, status, body, layout }) {
  const headRef = useRef(null);
  const bodyRef = useRef(null);
  const innerRef = useRef(null);

  useLayoutEffect(() => {
    const bodyEl = bodyRef.current, innerEl = innerRef.current, headEl = headRef.current;
    if (!bodyEl || !innerEl) return undefined;
    const contentEl = bodyEl.parentElement;
    let first = true;

    const sync = () => {
      // Measure the static wrapper, never the body. The body is the element
      // carrying the transition, and any attempt to read its natural height by
      // parking it at `height:auto` and flushing layout also cancels whatever
      // transition is mid-flight — which showed up as the box snapping to the
      // new size and then easing only the last few pixels. The wrapper's own
      // height is unaffected by the animation, so it can be read at any time.
      // The inner wrapper is a flow-root so the sticky action bar's negative
      // bottom margin (which exists to cancel this padding) is counted inside
      // that height instead of collapsing out of it.
      const cs = getComputedStyle(bodyEl);
      const natural = innerEl.offsetHeight
        + parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);

      // Clamp to what the dialog can actually show, so the easing lands where
      // the box lands instead of running on past a max-height it already hit.
      const maxH = parseFloat(getComputedStyle(contentEl).maxHeight);
      const avail = Number.isFinite(maxH) ? Math.max(0, maxH - (headEl?.offsetHeight || 0)) : Infinity;
      const target = `${Math.round(Math.min(natural, avail))}px`;
      if (target === bodyEl.style.height) return;

      if (first) {
        // The first sync runs before the dialog's entrance has painted: the
        // modal should zoom in already at the right size, not grow into it.
        bodyEl.style.transition = "none";
        bodyEl.style.height = target;
        void bodyEl.offsetHeight;
        bodyEl.style.transition = "";
        first = false;
      } else {
        bodyEl.style.height = target;
      }
    };

    sync();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(sync);
    ro.observe(innerEl);
    if (headEl) ro.observe(headEl);
    return () => ro.disconnect();
  }, []);

  return (
    <>
      <ModalHead layout={layout} ref={headRef}>
        <div className="min-w-0">
          <ModalTitle>{title}</ModalTitle>
          {sub && <ModalSub>{sub}</ModalSub>}
        </div>
        <DialogCloseButton />
      </ModalHead>
      <ModalBody layout={layout} ref={bodyRef}>
        {/* Static wrapper: the body itself carries an animating height, so the
            natural height of the content has to be measurable somewhere that
            isn't being animated. */}
        {/* Content arriving into an already-open dialog fades rather than pops. */}
        <div ref={innerRef} className="flow-root data-[state=ready]:animate-content-in motion-reduce:animate-none" data-state={status}>{body}</div>
      </ModalBody>
    </>
  );
}

// Shown only when a form takes longer than SKELETON_DELAY to arrive. Shaped
// like a form rather than spelling out "Loading…" so the swap to real fields is
// a change of content, not a change of layout.
const SKEL = "rounded-[8px] bg-muted animate-skel motion-reduce:animate-none motion-reduce:opacity-55";
function FormSkeleton() {
  return (
    <div className="flex flex-col gap-[26px]" aria-hidden="true">
      {/* Sized to land near where a real form lands (every form in the app
          currently fills the dialog's max height), so the hand-off is a short
          eased correction rather than a long one. */}
      {[["38%", 4], ["30%", 4], ["34%", 2]].map(([w, fields], s) => (
        <div key={s} className="flex flex-col gap-3.5">
          <div className={cn(SKEL, "h-[13px]")} style={{ width: w }} />
          <div className="grid grid-cols-2 gap-x-4 gap-y-3.5 max-[640px]:grid-cols-1">
            {Array.from({ length: fields }, (_, i) => (
              <div key={i} className="flex flex-col gap-[7px]">
                <div className={cn(SKEL, "h-[9px]")} style={{ width: `${34 + ((i * 7) % 18)}%` }} />
                <div className={cn(SKEL, "h-10")} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const NOOP = Object.assign(() => {}, { prefetch: () => {} });

export function useFormModal() {
  return useContext(FormModalContext)?.openForm || NOOP;
}
