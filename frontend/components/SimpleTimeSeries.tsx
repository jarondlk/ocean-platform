import type { TimeSeriesPoint } from "@/types";

type SimpleTimeSeriesProps = {
  points: TimeSeriesPoint[];
  xColumn: string;
  yColumn: string;
};

export function SimpleTimeSeries({ points, xColumn, yColumn }: SimpleTimeSeriesProps) {
  if (!points.length) {
    return <p className="empty-state">No plottable points.</p>;
  }

  const width = 760;
  const height = 260;
  const pad = { top: 18, right: 18, bottom: 38, left: 58 };
  const prepared = points.map((point, index) => {
    const parsed = Date.parse(point.x);
    return {
      ...point,
      xValue: Number.isNaN(parsed) ? index : parsed,
    };
  });
  const minX = Math.min(...prepared.map((point) => point.xValue));
  const maxX = Math.max(...prepared.map((point) => point.xValue));
  const minYRaw = Math.min(...prepared.map((point) => point.y));
  const maxYRaw = Math.max(...prepared.map((point) => point.y));
  const yPadding = maxYRaw === minYRaw ? 1 : (maxYRaw - minYRaw) * 0.08;
  const minY = minYRaw - yPadding;
  const maxY = maxYRaw + yPadding;

  function xScale(value: number) {
    if (maxX === minX) return pad.left;
    return pad.left + ((value - minX) / (maxX - minX)) * (width - pad.left - pad.right);
  }

  function yScale(value: number) {
    if (maxY === minY) return height - pad.bottom;
    return height - pad.bottom - ((value - minY) / (maxY - minY)) * (height - pad.top - pad.bottom);
  }

  const line = prepared
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xScale(point.xValue)} ${yScale(point.y)}`)
    .join(" ");
  const first = prepared[0];
  const last = prepared[prepared.length - 1];

  return (
    <div className="chart-wrap">
      <svg className="simple-chart" viewBox={`0 0 ${width} ${height}`} role="img">
        <title>{`${yColumn} by ${xColumn}`}</title>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>
          {formatAxis(maxYRaw)}
        </text>
        <text x={8} y={height - pad.bottom}>
          {formatAxis(minYRaw)}
        </text>
        <text x={pad.left} y={height - 12}>
          {formatX(first.x)}
        </text>
        <text x={width - pad.right} y={height - 12} textAnchor="end">
          {formatX(last.x)}
        </text>
        <path d={line} />
        {prepared.length <= 180
          ? prepared.map((point, index) => (
              <circle key={`${point.x}-${index}`} cx={xScale(point.xValue)} cy={yScale(point.y)} r={2.5}>
                <title>{`${point.x}: ${formatAxis(point.y)}${point.sample_id ? ` (${point.sample_id})` : ""}`}</title>
              </circle>
            ))
          : null}
      </svg>
    </div>
  );
}

function formatAxis(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function formatX(value: string): string {
  return value.length > 10 ? value.slice(0, 10) : value;
}
