import { Bar, BarChart, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import type { SpreadBucket } from "@/lib/analytics"

interface SpreadAnalyticsProps {
  buckets: SpreadBucket[]
}

const chartConfig = {
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

export function SpreadAnalytics({ buckets }: SpreadAnalyticsProps) {
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
        <ChartContainer config={chartConfig} className="min-h-[300px] w-full">
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
                      chartConfig[name as keyof typeof chartConfig]?.label ??
                      name
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
