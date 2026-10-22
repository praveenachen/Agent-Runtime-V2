"use client";

import { useState } from "react";

import { Icon, type IconName } from "@/components/ui/icon";

export type KpiDelta = { value: string; up: boolean; basis: string };

// The mini bars are decorative; the value, subtitle and optional delta passed in are real telemetry.
export function KpiCard({ icon, tone, label, value, subtitle, delta = null, seed }: { icon: IconName; tone: string; label: string; value: string; subtitle: string; delta?: KpiDelta | null; seed: number }) {
  return <article className={`overview-kpi tone-${tone}`}><span className="overview-kpi-icon"><Icon name={icon} /></span><div className="kpi-body"><span>{label}</span><div className="kpi-value"><strong>{value}</strong>{delta && <em className={`kpi-delta ${delta.up ? "up" : "down"}`} title={`Change ${delta.basis}`}>{delta.up ? "↑" : "↓"} {delta.value}</em>}</div><small>{subtitle}</small></div><MicroBars seed={seed} /></article>;
}

export function MicroBars({ seed }: { seed: number }) {
  const count = 24; const values = Array.from({ length: count }, (_, index) => 0.28 + 0.34 * Math.abs(Math.sin(index * 0.9 + seed)) + 0.3 * Math.abs(Math.sin(index * 0.37 + seed * 1.7)) + (index / count) * 0.12);
  const max = Math.max(...values);
  return <svg className="micro-bars" aria-hidden="true" viewBox="0 0 96 44" preserveAspectRatio="none">{values.map((value, index) => { const height = Math.max(4, (value / max) * 40); return <rect key={index} x={index * 4 + 0.5} y={44 - height} width="2.2" height={height} rx="1" />; })}</svg>;
}

export function CopyButton({ value, label = "Run ID" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return <button aria-label={copied ? `${label} copied` : `Copy ${label}`} className={copied ? "copy-button copied" : "copy-button"} onClick={async () => { try { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1400); } catch { /* clipboard unavailable */ } }} title={copied ? "Copied" : `Copy ${label}`} type="button"><Icon name={copied ? "check" : "copy"} /></button>;
}

export function workflowVisual(seedText: string): { tone: string; icon: IconName } {
  const hash = [...seedText].reduce((sum, character) => (sum * 31 + character.charCodeAt(0)) >>> 0, 7);
  const tones = ["purple", "blue", "green", "amber"]; const icons: IconName[] = ["workflow", "spark", "code", "database"];
  return { tone: tones[hash % tones.length], icon: icons[(hash >>> 3) % icons.length] };
}

export function humanize(value: string): string { return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
export function compactId(value: string): string { return value.length > 18 ? `${value.slice(0, 15)}…` : value; }
