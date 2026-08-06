/** Tree-shaken ECharts core: only the chart types and components we use. */
import { BarChart, HeatmapChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import {
  BrushComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  // charts
  LineChart,
  BarChart,
  PieChart,
  HeatmapChart,
  ScatterChart, // required by UA "CPI vs Install Volume" — without it that chart is blank
  // components
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DataZoomComponent,
  BrushComponent,
  VisualMapComponent, // required by heatmap
  MarkLineComponent, // required by the break-even ROAS line on Spend vs Revenue
  // renderer
  CanvasRenderer,
]);

export { echarts };
export type { EChartsOption } from "echarts";
