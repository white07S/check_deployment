import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders sidebar heading", () => {
  render(<App />);
  const heading = screen.getByText(/Codex Sessions/i);
  expect(heading).toBeInTheDocument();
});
