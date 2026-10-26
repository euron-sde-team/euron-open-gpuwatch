// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { GaugeIcon } from "lucide-react";
import { afterEach, describe, expect, it } from "vitest";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { Meter, MetricValue } from "@/components/metric-value";
import { TooltipProvider } from "@/components/ui/tooltip";

afterEach(cleanup);

describe("KpiTile", () => {
  it("shows the value and marks more missed budgets as bad", () => {
    render(<KpiTile label="Budgets missed" icon={GaugeIcon} value="135" current={135} previous={100} goodWhen="down" comparison="vs prior 30d" />);
    expect(screen.getByText("135")).toBeInTheDocument();
    const chip = screen.getByText("+35%");
    expect(chip.className).toMatch(/warning/);
  });

  it("marks rising utilization as good", () => {
    render(<KpiTile label="Utilization" icon={GaugeIcon} value="27.1%" current={27.1} previous={24.2} goodWhen="up" comparison="vs prior 30d" />);
    expect(screen.getByText("+12%").className).toMatch(/savings/);
  });

  it("says New when there is no previous period", () => {
    render(<KpiTile label="Runs" icon={GaugeIcon} value="12" current={12} previous={0} comparison="vs prior 30d" />);
    expect(screen.getByText("New")).toBeInTheDocument();
  });

  it("renders skeletons while loading", () => {
    const { container } = render(<KpiTile label="Spend" icon={GaugeIcon} value="$1" current={1} previous={1} comparison="x" loading />);
    expect(screen.queryByText("$1")).not.toBeInTheDocument();
    expect(container.querySelectorAll("[data-slot='skeleton'], .animate-pulse").length).toBeGreaterThan(0);
  });
});

describe("EmptyState", () => {
  it("always explains itself and offers an action", () => {
    render(
      <EmptyState
        icon={GaugeIcon}
        title="No GPUs yet"
        description="GPUs appear here as soon as an agent reports."
        action={<button type="button">Add a host</button>}
      />,
    );
    expect(screen.getByText("No GPUs yet")).toBeInTheDocument();
    expect(screen.getByText(/as soon as an agent reports/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a host" })).toBeInTheDocument();
  });
});


describe("MetricValue", () => {
  it("shows a missing metric as Not available, never 0", () => {
    render(
      <TooltipProvider>
        <MetricValue value={null} format={(v) => `${v}%`} />
        <MetricValue value={0} format={(v) => `${v}%`} />
      </TooltipProvider>,
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});

describe("Meter", () => {
  it("reports its value to assistive technology", () => {
    render(<Meter value={40} max={80} label="Memory used" />);
    const meter = screen.getByRole("meter", { name: "Memory used" });
    expect(meter).toHaveAttribute("aria-valuenow", "50");
  });
  it("says Not available when the reading is missing", () => {
    render(<Meter value={null} label="Fan" />);
    expect(screen.getByRole("meter", { name: "Fan" })).toHaveAttribute("aria-valuetext", "Not available");
  });
});
