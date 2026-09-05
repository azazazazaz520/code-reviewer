import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "./Layout";

describe("AppLayout", () => {
  it("桌面端固定应用外壳并让主内容区独立滚动", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>主内容</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const main = screen.getByRole("main");
    const shell = main.parentElement;
    const sidebar = document.querySelector("aside");

    expect(shell).toHaveClass("md:h-screen", "md:overflow-hidden");
    expect(sidebar).toHaveClass("h-full", "overflow-hidden");
    expect(main).toHaveClass("md:h-full", "md:min-h-0", "md:overflow-y-auto");
  });
});
