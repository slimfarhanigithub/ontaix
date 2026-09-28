import { render, screen } from "@testing-library/react";

import { App } from "./App";

describe("App", () => {
  it("renders the Studio placeholder", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Ontaix Studio" })).toBeInTheDocument();
  });
});
