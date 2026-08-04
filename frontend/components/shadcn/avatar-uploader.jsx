import { useState } from "react";
import Cropper from "react-easy-crop";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "./ui/dialog.jsx";
import { Button } from "./ui/button.jsx";
import { Input } from "./ui/input.jsx";
import { getCroppedImg } from "../../utils/cropImage.js";

// Crop-before-upload flow, adapted from 21st.dev "Account Settings" /
// "Avatar Uploader" (@sshahaider, demo 7843): pick a file, drag/zoom a square
// crop over it, then hand the cropped JPEG to `onUpload`. Trimmed down from
// the reference's version — no rotate/flip controls, no responsive
// Dialog/Drawer switch (this app's other modals are Dialog on every size).
export default function AvatarUploader({ children, onUpload, aspect = 1 }) {
  const [open, setOpen] = useState(false);
  const [photo, setPhoto] = useState(null); // { url, file }
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState(null);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setPhoto(null);
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setArea(null);
  };

  const pick = (e) => {
    const file = e.target.files?.[0];
    if (file) setPhoto({ url: URL.createObjectURL(file), file });
  };

  const save = async () => {
    if (!photo || !area) return;
    setBusy(true);
    try {
      const blob = await getCroppedImg(photo.url, area);
      const file = new File([blob], photo.file.name, { type: "image/jpeg" });
      await onUpload(file);
      setOpen(false);
      reset();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-md" style={{ padding: 24 }}>
        <DialogHeader>
          <DialogTitle>Update photo</DialogTitle>
        </DialogHeader>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Input type="file" accept="image/*" onChange={pick} disabled={busy} />
          {photo ? (
            <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-secondary">
              <Cropper
                image={photo.url}
                crop={crop}
                zoom={zoom}
                aspect={aspect}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={(_, croppedAreaPixels) => setArea(croppedAreaPixels)}
              />
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" onClick={save} disabled={!photo || busy}>
            {busy ? "Uploading…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
