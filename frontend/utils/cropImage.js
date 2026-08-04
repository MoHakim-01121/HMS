// Rasterizes the crop rectangle react-easy-crop reports (pixel coords into
// the source image) onto a canvas sized to match, then reads it back out as
// a JPEG blob. No rotate/flip: avatar-uploader.jsx never exposes those
// controls, so the bounding-box math they'd require would be dead weight.
function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.addEventListener("load", () => resolve(img));
    img.addEventListener("error", reject);
    img.crossOrigin = "anonymous";
    img.src = src;
  });
}

export async function getCroppedImg(src, cropPx) {
  const image = await loadImage(src);
  const canvas = document.createElement("canvas");
  canvas.width = cropPx.width;
  canvas.height = cropPx.height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(image, cropPx.x, cropPx.y, cropPx.width, cropPx.height, 0, 0, cropPx.width, cropPx.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Failed to crop image"))), "image/jpeg", 0.92);
  });
}
