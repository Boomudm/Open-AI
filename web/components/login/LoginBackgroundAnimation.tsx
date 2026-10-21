"use client";

import { cn } from "@/lib/cn";
import { useEffect, useId, useRef, useState } from "react";

const BASE_W = 1004;
const BASE_H = 900;
const CENTER_Y = 450;
const STROKE = "var(--auth-curve-stroke)";
const DOT = "var(--auth-curve-dot)";

type CurveLane = {
  path: string;
  maskTop: string;
  maskBottom: string;
  strokeWidth: number;
  blur: number;
  gradientStop: number;
  drawDelay: string;
  motionDur: string;
  motionBeginTop: string;
  motionBeginBottom: string;
};

function sx(x: number, w: number) {
  return (x / BASE_W) * w;
}

function buildLanes(panelW: number): CurveLane[] {
  const w = Math.max(panelW, BASE_W);
  const c186 = sx(186, w);
  const c161 = sx(160.9, w);
  const c136 = sx(135.8, w);
  const cp = sx(75.3, w);

  return [
    {
      path: `M 0 0C 0 0 ${cp} ${CENTER_Y} ${c186} ${CENTER_Y}L ${w} ${CENTER_Y}`,
      maskTop: `M ${c186} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 0 0 0V 0H ${w}V ${CENTER_Y}H ${c186}Z`,
      maskBottom: `M ${c186} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 ${BASE_H} 0 ${BASE_H}V ${BASE_H}H ${w}V ${CENTER_Y}H ${c186}Z`,
      strokeWidth: 20,
      blur: 50,
      gradientStop: 0.5,
      drawDelay: "0s",
      motionDur: "18s",
      motionBeginTop: "0s",
      motionBeginBottom: "9s",
    },
    {
      path: `M 0 ${BASE_H}C 0 ${BASE_H} ${cp} ${CENTER_Y} ${c186} ${CENTER_Y}L ${w} ${CENTER_Y}`,
      maskTop: `M ${c186} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 0 0 0V 0H ${w}V ${CENTER_Y}H ${c186}Z`,
      maskBottom: `M ${c186} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 ${BASE_H} 0 ${BASE_H}V ${BASE_H}H ${w}V ${CENTER_Y}H ${c186}Z`,
      strokeWidth: 20,
      blur: 50,
      gradientStop: 0.5,
      drawDelay: "0s",
      motionDur: "18s",
      motionBeginTop: "0s",
      motionBeginBottom: "9s",
    },
    {
      path: `M 0 225C 0 225 ${cp} ${CENTER_Y} ${c161} ${CENTER_Y}L ${w} ${CENTER_Y}`,
      maskTop: `M ${c161} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 225 0 225V 0H ${w}V ${CENTER_Y}H ${c161}Z`,
      maskBottom: `M ${c161} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 675 0 675V ${BASE_H}H ${w}V ${CENTER_Y}H ${c161}Z`,
      strokeWidth: 15,
      blur: 20,
      gradientStop: 0.3,
      drawDelay: "0.2s",
      motionDur: "15s",
      motionBeginTop: "0s",
      motionBeginBottom: "8.2s",
    },
    {
      path: `M 0 675C 0 675 ${cp} ${CENTER_Y} ${c161} ${CENTER_Y}L ${w} ${CENTER_Y}`,
      maskTop: `M ${c161} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 225 0 225V 0H ${w}V ${CENTER_Y}H ${c161}Z`,
      maskBottom: `M ${c161} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 675 0 675V ${BASE_H}H ${w}V ${CENTER_Y}H ${c161}Z`,
      strokeWidth: 15,
      blur: 20,
      gradientStop: 0.3,
      drawDelay: "0.2s",
      motionDur: "15s",
      motionBeginTop: "0s",
      motionBeginBottom: "8.2s",
    },
    {
      path: `M 0 405C 0 405 ${cp} ${CENTER_Y} ${c136} ${CENTER_Y}L ${w} ${CENTER_Y}`,
      maskTop: `M ${c136} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 405 0 405V 0H ${w}V ${CENTER_Y}H ${c136}Z`,
      maskBottom: `M ${c136} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 495 0 495V ${BASE_H}H ${w}V ${CENTER_Y}H ${c136}Z`,
      strokeWidth: 10,
      blur: 15,
      gradientStop: 0.2,
      drawDelay: "0.4s",
      motionDur: "21s",
      motionBeginTop: "0s",
      motionBeginBottom: "10.4s",
    },
    {
      path: `M 0 495C 0 495 ${cp} ${CENTER_Y} ${c136} ${CENTER_Y}L ${w} ${CENTER_Y}`,
      maskTop: `M ${c136} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 405 0 405V 0H ${w}V ${CENTER_Y}H ${c136}Z`,
      maskBottom: `M ${c136} ${CENTER_Y}C ${cp} ${CENTER_Y} 0 495 0 495V ${BASE_H}H ${w}V ${CENTER_Y}H ${c136}Z`,
      strokeWidth: 10,
      blur: 15,
      gradientStop: 0.2,
      drawDelay: "0.4s",
      motionDur: "21s",
      motionBeginTop: "0s",
      motionBeginBottom: "10.4s",
    },
  ];
}

function isTopLane(path: string) {
  return path.includes("M 0 0") || path.includes("M 0 225") || path.includes("M 0 405");
}

function DrawPath({
  d,
  delay,
  strokeWidth = 1,
  gradientId,
  filterId,
  maskId,
}: {
  d: string;
  delay: string;
  strokeWidth?: number;
  gradientId?: string;
  filterId?: string;
  maskId?: string;
}) {
  const anim = (
    <animate
      attributeName="stroke-dashoffset"
      from="1"
      to="0"
      dur="3s"
      begin={delay}
      fill="freeze"
      calcMode="spline"
      keyTimes="0;1"
      keySplines="0.25 0.1 0.25 1"
    />
  );

  const pathProps = {
    d,
    pathLength: 1,
    strokeDasharray: 1,
    strokeDashoffset: 1,
  };

  if (!gradientId) {
    return (
      <path {...pathProps} stroke={STROKE}>
        {anim}
      </path>
    );
  }

  const glow = (
    <path {...pathProps} stroke={`url(#${gradientId})`} strokeWidth={strokeWidth}>
      {anim}
    </path>
  );

  if (!filterId || !maskId) return glow;

  return (
    <g mask={`url(#${maskId})`}>
      <g filter={`url(#${filterId})`}>{glow}</g>
    </g>
  );
}

function MotionGlow({
  path,
  begin,
  dur,
  gradientId,
}: {
  path: string;
  begin: string;
  dur: string;
  gradientId: string;
}) {
  return (
    <g>
      <animateMotion
        begin={begin}
        dur={dur}
        repeatCount="indefinite"
        path={path}
        calcMode="spline"
        keyPoints="0;1"
        keyTimes="0;1"
        keySplines="0.42 0 0.58 1"
      />
      <animate
        attributeName="opacity"
        begin={begin}
        dur={dur}
        repeatCount="indefinite"
        calcMode="spline"
        keyTimes="0;0.05;0.75;1"
        values="0;0.3;0.3;0"
        keySplines="0 0 0.58 1;0 0 1 1;0.42 0 1 1"
      />
      <circle r={64} fill={`url(#${gradientId})`} />
    </g>
  );
}

function MotionDot({ path, begin, dur }: { path: string; begin: string; dur: string }) {
  return (
    <g opacity={0}>
      <animateMotion
        begin={begin}
        dur={dur}
        repeatCount="indefinite"
        path={path}
        calcMode="spline"
        keyPoints="0;1"
        keyTimes="0;1"
        keySplines="0.42 0 0.58 1"
      />
      <animate attributeName="opacity" from="0" to="1" dur="0.3s" begin={begin} fill="freeze" />
      <circle r={6} fill={DOT} />
    </g>
  );
}

function CurveSvg({ idPrefix, panelW }: { idPrefix: string; panelW: number }) {
  const lanes = buildLanes(panelW);
  const laneGroups = [lanes.slice(0, 2), lanes.slice(2, 4), lanes.slice(4, 6)];

  return (
    <svg
      viewBox={`0 0 ${panelW} ${BASE_H}`}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="absolute inset-0 h-full w-full"
      preserveAspectRatio="xMinYMid slice"
    >
      <defs>
        <radialGradient id={`${idPrefix}-gr`} gradientUnits="objectBoundingBox" cx="0.5" cy="0.5" r="0.5">
          <stop stopColor={STROKE} />
          <stop offset="1" stopColor={STROKE} stopOpacity="0" />
        </radialGradient>
        {laneGroups.map((_, gi) => {
          const lane = laneGroups[gi][0];
          return (
            <filter
              key={`f-${gi}`}
              id={`${idPrefix}-f${gi}`}
              x="-50%"
              y="-100%"
              width="200%"
              height="300%"
              colorInterpolationFilters="sRGB"
            >
              <feGaussianBlur stdDeviation={lane.blur} />
            </filter>
          );
        })}
        {laneGroups.map((_, gi) => {
          const lane = laneGroups[gi][0];
          return (
            <linearGradient
              key={`g-${gi}`}
              id={`${idPrefix}-g${gi}`}
              x1="0"
              y1="0"
              x2={String(panelW)}
              y2="0"
              gradientUnits="userSpaceOnUse"
            >
              <stop stopColor={STROKE} />
              <stop offset={lane.gradientStop} stopColor={STROKE} stopOpacity="0" />
            </linearGradient>
          );
        })}
        {lanes.map((lane, i) => (
          <mask
            key={`m-${i}`}
            id={`${idPrefix}-m${i}`}
            maskUnits="userSpaceOnUse"
            x="0"
            y="0"
            width={panelW}
            height={BASE_H}
            style={{ maskType: "alpha" }}
          >
            <path d={isTopLane(lane.path) ? lane.maskTop : lane.maskBottom} fill="#D9D9D9" />
          </mask>
        ))}
      </defs>

      {lanes.map((lane, i) => {
        const gi = i < 2 ? 0 : i < 4 ? 1 : 2;
        const top = isTopLane(lane.path);
        const motionBegin = top ? lane.motionBeginTop : lane.motionBeginBottom;
        return (
          <g key={`${lane.path}-${i}`}>
            <DrawPath d={lane.path} delay={lane.drawDelay} />
            <DrawPath
              d={lane.path}
              delay={lane.drawDelay}
              strokeWidth={lane.strokeWidth}
              gradientId={`${idPrefix}-g${gi}`}
              filterId={`${idPrefix}-f${gi}`}
              maskId={`${idPrefix}-m${i}`}
            />
            <g mask={`url(#${idPrefix}-m${i})`}>
              <MotionGlow
                path={lane.path}
                begin={motionBegin}
                dur={lane.motionDur}
                gradientId={`${idPrefix}-gr`}
              />
            </g>
            <MotionDot path={lane.path} begin={motionBegin} dur={lane.motionDur} />
          </g>
        );
      })}
    </svg>
  );
}

/** LangSmith-style converging curve animation (smith.langchain.com). */
export function LoginBackgroundAnimation({ className }: { className?: string }) {
  const uid = useId().replace(/:/g, "");
  const idPrefix = `neo-${uid}`;
  const ref = useRef<HTMLDivElement>(null);
  const [panelW, setPanelW] = useState(BASE_W);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => {
      const w = el.getBoundingClientRect().width;
      if (w > 0) setPanelW(Math.round(w));
    };

    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={cn("pointer-events-none absolute inset-0 overflow-hidden auth-ambient-glow", className)}
      aria-hidden
    >
      <CurveSvg idPrefix={idPrefix} panelW={panelW} />
    </div>
  );
}
