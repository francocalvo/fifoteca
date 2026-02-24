import { Bar, BarChart, Line, LineChart, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import type { SpreadBucket, SpreadPoint } from "@/lib/analytics"

interface SpreadAnalyticsProps {
  buckets: SpreadBucket[]
  points: SpreadPoint[]
}

const barChartConfig = {
  favoriteWinPct: {
    label: "Favorite Win",
    color: "var(--color-green-500)",
  },
  drawPct: {
    label: "Draw",
    color: "var(--color-yellow-500)",
  },
  underdogWinPct: {
    label: "Underdog Win",
    color: "var(--color-red-500)",
  },
} satisfies ChartConfig

const lineChartConfig = {
  myWinPct: {
    label: "My Win Rate",
    color: "var(--color-blue-500)",
  },
} satisfies ChartConfig

function SpreadBarChart({ buckets }: { buckets: SpreadBucket[] }) {
  const chartData = buckets.map((b) => ({
    label: `${b.label}\n(N=${b.sampleSize})`,
    favoriteWinPct: b.favoriteWinPct,
    drawPct: b.drawPct,
    underdogWinPct: b.underdogWinPct,
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Spread Analytics</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={barChartConfig}
          className="min-h-[300px] w-full"
        >
          <BarChart data={chartData}>
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value, name) => {
                    const label =
                      barChartConfig[name as keyof typeof barChartConfig]
                        ?.label ?? name
                    return `${label}: ${value}%`
                  }}
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar
              dataKey="favoriteWinPct"
              stackId="a"
              fill="var(--color-favoriteWinPct)"
              radius={[0, 0, 0, 0]}
            />
            <Bar
              dataKey="drawPct"
              stackId="a"
              fill="var(--color-drawPct)"
              radius={[0, 0, 0, 0]}
            />
            <Bar
              dataKey="underdogWinPct"
              stackId="a"
              fill="var(--color-underdogWinPct)"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

function SpreadWinRateChart({ points }: { points: SpreadPoint[] }) {
  const chartData = points.map((p) => ({
    spread: p.spread,
    myWinPct: p.myWinPct,
    sampleSize: p.sampleSize,
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">My Win Rate by Spread</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={lineChartConfig}
          className="min-h-[300px] w-full"
        >
          <LineChart data={chartData}>
            <XAxis
              dataKey="spread"
              type="number"
              domain={[0, 30]}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value, name, item) => {
                    const label =
                      lineChartConfig[name as keyof typeof lineChartConfig]
                        ?.label ?? name
                    return `${label}: ${value}% (N=${item.payload.sampleSize})`
                  }}
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Line
              dataKey="myWinPct"
              type="monotone"
              stroke="var(--color-myWinPct)"
              strokeWidth={2}
              dot={{ r: 4, fill: "var(--color-myWinPct)" }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

export function SpreadAnalytics({ buckets, points }: SpreadAnalyticsProps) {
  return (
    <div className="space-y-4">
      <SpreadBarChart buckets={buckets} />
      <SpreadWinRateChart points={points} />
    </div>
  )
}
