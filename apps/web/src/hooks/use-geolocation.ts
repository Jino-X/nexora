"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface GeoState {
  status: "idle" | "prompt" | "locating" | "granted" | "denied" | "unavailable" | "error";
  coords: { latitude: number; longitude: number; accuracy: number } | null;
  error: string | null;
}

/**
 * Browser geolocation with explicit permission. Nothing is requested until `request()` is called
 * (or `auto` is true and permission was already granted).
 */
export function useGeolocation({ auto = false }: { auto?: boolean } = {}) {
  const [state, setState] = useState<GeoState>({ status: "idle", coords: null, error: null });
  const requested = useRef(false);

  const request = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setState({ status: "unavailable", coords: null, error: "Location is not available in this browser." });
      return;
    }
    setState((s) => ({ ...s, status: "locating", error: null }));
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setState({
          status: "granted",
          coords: { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy },
          error: null,
        }),
      (err) =>
        setState({
          status: err.code === err.PERMISSION_DENIED ? "denied" : "error",
          coords: null,
          error: err.code === err.PERMISSION_DENIED ? "Location permission was denied." : err.message,
        }),
      { enableHighAccuracy: false, timeout: 12_000, maximumAge: 5 * 60_000 },
    );
  }, []);

  useEffect(() => {
    if (!auto || requested.current || typeof navigator === "undefined" || !navigator.permissions) return;
    requested.current = true;
    navigator.permissions
      .query({ name: "geolocation" as PermissionName })
      .then((perm) => {
        if (perm.state === "granted") request();
        else setState((s) => ({ ...s, status: perm.state === "denied" ? "denied" : "prompt" }));
      })
      .catch(() => undefined);
  }, [auto, request]);

  return { ...state, request };
}
