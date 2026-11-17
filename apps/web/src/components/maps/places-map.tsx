"use client";

import "leaflet/dist/leaflet.css";

import type { Place } from "@nexora/shared-types";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

/** OpenStreetMap tiles (light usage, with attribution). Use your own tile provider for production volume. */
export default function PlacesMap({
  center,
  places,
  className,
  height = 260,
}: {
  center: { latitude: number; longitude: number };
  places: Place[];
  className?: string;
  height?: number;
}) {
  return (
    <div className={className} style={{ height }}>
      <MapContainer
        center={[center.latitude, center.longitude]}
        zoom={14}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <CircleMarker
          center={[center.latitude, center.longitude]}
          radius={8}
          pathOptions={{ color: "#6d4aff", fillColor: "#6d4aff", fillOpacity: 0.9 }}
        >
          <Popup>You are here</Popup>
        </CircleMarker>
        {places.map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.latitude, p.longitude]}
            radius={6}
            pathOptions={{ color: "#0ea5e9", fillColor: "#0ea5e9", fillOpacity: 0.8 }}
          >
            <Popup>
              <strong>{p.name}</strong>
              {p.address && <div>{p.address}</div>}
              <a href={p.directions_url} target="_blank" rel="noreferrer">
                Directions
              </a>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
