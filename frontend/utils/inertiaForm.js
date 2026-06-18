// Submit an Inertia useForm as multipart so Django request.POST/FILES populate
// (Inertia sends JSON by default, which Django does not parse). Collection
// fields named in `json` are stringified into a single JSON field each.
export function postForm(form, url, { json = [] } = {}) {
  form.transform((data) => {
    const out = { ...data };
    for (const key of json) out[key] = JSON.stringify(data[key] ?? []);
    return out;
  });
  return form.post(url, { forceFormData: true });
}
