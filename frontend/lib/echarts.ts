/** Tree-shaken ECharts core: only the chart types and components we use. */
import { BarChart, HeatmapChart, LineChart, PieChart } from "echarts/charts";
import {
  BrushComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
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
  // components
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DataZoomComponent,
  BrushComponent,
  VisualMapComponent, // required by heatmap
  // renderer
  CanvasRenderer,
]);

export { echarts };
export type { EChartsOption } from "echarts";
