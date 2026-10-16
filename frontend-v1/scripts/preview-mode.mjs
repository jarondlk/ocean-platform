// Explicit local host selection; never inferred from a browser query or store.
export function previewMode(arguments_) {
  if (arguments_.length !== 2 || arguments_[0] !== "--mode" || !["synthetic-preview", "service"].includes(arguments_[1])) {
    throw new Error("Select --mode synthetic-preview or --mode service explicitly");
  }
  return arguments_[1];
}

export function loopbackHost(value) {
  if (typeof value !== "string") return false;
  return /^(?:localhost|127\.0\.0\.1|\[::1\]):3100$/.test(value.toLowerCase());
}

export function modeEnvelope(mode) {
  if (!["synthetic-preview", "service"].includes(mode)) throw new Error("Invalid local runtime mode");
  return { version: "ocean-v1-mode-v1", mode };
}
