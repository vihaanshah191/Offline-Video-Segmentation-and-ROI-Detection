import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ObjectCount } from "@/types";

const PROHIBITED_COLOR = "hsl(0 84% 60%)";
const ALLOWED_COLOR = "hsl(199 89% 52%)";

export function ObjectChart({ objectCounts }: { objectCounts: ObjectCount[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Detected objects</CardTitle>
      </CardHeader>
      <CardContent>
        {objectCounts.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No objects detected. Enable object detection when analyzing to populate this chart.
          </p>
        ) : (
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={objectCounts} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}>
                <XAxis dataKey="label" stroke="hsl(215 20% 65%)" fontSize={11} />
                <YAxis allowDecimals={false} stroke="hsl(215 20% 65%)" fontSize={11} />
                <Tooltip
                  cursor={{ fill: "hsl(217 33% 18% / 0.4)" }}
                  contentStyle={{
                    background: "hsl(222 44% 9%)",
                    border: "1px solid hsl(217 33% 18%)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {objectCounts.map((o) => (
                    <Cell key={o.label} fill={o.prohibited ? PROHIBITED_COLOR : ALLOWED_COLOR} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
